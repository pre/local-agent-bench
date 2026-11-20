"""download/download.sh on local files: a fake aria2c and a fake apk, no network, no podman."""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "download" / "download.sh"
FILES = {"a.gguf": b"alpha", "sub/b.gguf": b"beta"}

# Copies each URL of the input file from $SOURCE/<path> to <dir>/<out> and removes
# the control file <out>.aria2, as aria2 does for a complete file. A file
# <path>.once is used one time in place of <path>.
FAKE_ARIA2C = r"""#!/bin/sh
for arg; do
  case $arg in --input-file=*) input=${arg#*=};; --dir=*) dir=${arg#*=};; esac
done
while read -r line; do
  case $line in
    https://*) src=$SOURCE/${line#*/resolve/*/};;
    out=*)
      out=$dir/${line#out=}
      echo "${line#out=}" >> "$SOURCE/requests"
      mkdir -p "$(dirname "$out")"
      if [ -f "$src.once" ]; then mv "$src.once" "$out"; else cp "$src" "$out"; fi
      rm -f "$out.aria2";;
  esac
done < "$input"
"""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


class Env:
    def __init__(self, root: Path, shell: list[str]):
        self.shell = shell
        self.models = root / "models"
        self.source = root / "source"
        self.bin = root / "bin"
        self.tsv = root / "models.tsv"
        for d in (self.models / "m", self.source / "sub", self.bin):
            d.mkdir(parents=True)
        lines = ["# model\trepository\trevision\tlast_modified\tpath\tbytes\tsha256"]
        for path, data in FILES.items():
            lines.append(f"m\torg/repo\trev1\t2026-11-19\t{path}\t{len(data)}\t{sha(data)}")
            (self.source / path).write_bytes(data)
        self.tsv.write_text("\n".join(lines) + "\n")
        executable(self.bin / "aria2c", FAKE_ARIA2C)
        executable(self.bin / "apk", '#!/bin/sh\ntouch "$SOURCE/apk-called"\n')

    def run(self, *args: str, **extra: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}", "TSV": str(self.tsv),
               "MODELS": str(self.models), "SOURCE": str(self.source), **extra}
        return subprocess.run([*self.shell, str(SCRIPT), *args], env=env, capture_output=True, text=True)

    def put(self, name: str, data: bytes) -> Path:
        path = self.models / "m" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def requests(self) -> list[str]:
        path = self.source / "requests"
        return path.read_text().split() if path.exists() else []

    def names(self) -> set[str]:
        return {str(p.relative_to(self.models / "m")) for p in (self.models / "m").rglob("*") if p.is_file()}


SHELLS = [pytest.param(["sh"], id="sh"),
          pytest.param(["busybox", "sh"], id="busybox",
                       marks=pytest.mark.skipif(not shutil.which("busybox"), reason="no busybox"))]


@pytest.fixture(params=SHELLS)
def env(request, tmp_path) -> Env:
    return Env(tmp_path, request.param)


def test_verify_accepts_the_files_of_the_list_and_downloads_nothing(env):
    for path, data in FILES.items():
        env.put(path, data)

    result = env.run("--verify", "m")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "VERIFIED m" in result.stdout
    assert env.requests() == []
    assert not (env.source / "apk-called").exists()


def test_verify_refuses_a_file_that_does_not_match(env):
    env.put("a.gguf", b"alpha")
    env.put("sub/b.gguf", b"bad")

    result = env.run("--verify", "m")

    assert result.returncode == 1
    assert "FAILED m" in result.stdout
    assert "VERIFIED" not in result.stdout


@pytest.mark.parametrize("other", [None, "sub/b.gguf.part"])
def test_verify_refuses_a_missing_file(env, other):
    env.put("a.gguf", b"alpha")
    if other:
        env.put(other, b"beta")

    result = env.run("--verify", "m")

    assert result.returncode == 1
    assert "FAILED m" in result.stdout


def test_verify_refuses_a_model_that_is_not_in_the_list(env):
    result = env.run("--verify", "other")

    assert result.returncode == 1
    assert "FAILED other: not in" in result.stdout


@pytest.mark.parametrize("checker", [
    "#!/bin/sh\ncat > /dev/null\n",                                      # no output, exit 0
    "#!/bin/sh\ncat > /dev/null\necho 'a.gguf: OK'\n",                   # fewer OK lines than files
    "#!/bin/sh\ncat > /dev/null\necho 'a.gguf: OK'\necho 'sub/b.gguf: OK'\nexit 1\n",  # exit status 1
])
def test_verify_fails_closed_when_the_checker_does_not_confirm_each_file(env, checker):
    for path, data in FILES.items():
        env.put(path, data)
    executable(env.bin / "sha256sum", checker)

    result = env.run("--verify", "m")

    assert result.returncode == 1
    assert "VERIFIED" not in result.stdout


def test_download_gives_the_final_name_after_the_sha256_check(env):
    result = env.run("m")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "VERIFIED m" in result.stdout
    assert env.names() == {"a.gguf", "sub/b.gguf", "expected-sha256.tsv", "source.txt", "download.log"}
    assert sorted(env.requests()) == ["a.gguf.part", "sub/b.gguf.part"]
    log = (env.models / "m" / "download.log").read_text()
    assert [line.split(" ", 1)[1] for line in log.splitlines()] == ["start m", "downloaded m", "VERIFIED m"]


def failing_aria2c(env: Env, failures: int) -> None:
    """aria2c fails `failures` times (a broken TLS connection), then works."""
    (env.source / "failures").write_text("x\n" * failures)
    executable(env.bin / "aria2c-real", FAKE_ARIA2C)
    executable(env.bin / "aria2c", '#!/bin/sh\necho call >> "$SOURCE/calls"\n'
               'if [ -s "$SOURCE/failures" ]; then sed -i 1d "$SOURCE/failures"; exit 1; fi\n'
               'exec aria2c-real "$@"\n')


def test_download_starts_aria2_again_after_a_failure(env):
    failing_aria2c(env, 2)

    result = env.run("m", RETRY_WAIT="0")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "VERIFIED m" in result.stdout
    assert len((env.source / "calls").read_text().split()) == 3
    assert "aria2 attempt 2 failed" in (env.models / "m" / "download.log").read_text()


def test_download_stops_after_the_last_attempt(env):
    failing_aria2c(env, 5)

    result = env.run("m", ATTEMPTS="2", RETRY_WAIT="0")

    assert result.returncode == 1
    assert len((env.source / "calls").read_text().split()) == 2
    assert "FAILED m: download not complete" in (env.models / "m" / "download.log").read_text()


def test_download_gets_a_bad_file_again_once(env):
    (env.source / "a.gguf.once").write_bytes(b"corrupt")

    result = env.run("m")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "VERIFIED m" in result.stdout
    assert env.requests().count("a.gguf.part") == 2
    assert "a.gguf.bad" not in env.names()


def test_download_keeps_a_file_that_fails_twice_under_a_name_that_the_server_does_not_use(env):
    (env.source / "a.gguf").write_bytes(b"corrupt")

    result = env.run("m")

    assert result.returncode == 1
    assert "FAILED m" in result.stdout
    assert env.requests().count("a.gguf.part") == 2
    assert "a.gguf" not in env.names()
    assert (env.models / "m" / "a.gguf.bad").read_bytes() == b"corrupt"


def test_download_checks_a_complete_part_file_and_continues_an_incomplete_one(env):
    env.put("a.gguf.part", b"alpha")
    env.put("sub/b.gguf.part", b"be")
    env.put("sub/b.gguf.part.aria2", b"control")

    result = env.run("m")

    assert result.returncode == 0, result.stdout + result.stderr
    assert env.requests() == ["sub/b.gguf.part"]
    assert {"a.gguf", "sub/b.gguf"} <= env.names()


def test_download_skips_a_file_with_its_final_name_but_checks_it(env):
    env.put("a.gguf", b"alpha")
    env.put("sub/b.gguf", b"bad")

    result = env.run("m")

    assert result.returncode == 1
    assert env.requests() == []
    assert "FAILED m" in result.stdout


def test_download_that_is_not_complete_renames_nothing(env):
    (env.source / "sub" / "b.gguf").unlink()

    result = env.run("m")

    assert result.returncode == 1
    assert "FAILED m: download not complete" in result.stdout
    assert "a.gguf" not in env.names()
    assert "a.gguf.part" in env.names()
