import json
import os
import signal
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

from llm_eval.podman import ContainerSpec, Mount, Podman, run_args


def spec(**kw) -> ContainerSpec:
    values = dict(
        name="c1",
        image="img:1",
        command=["bash", "-c", "echo hi"],
        mounts=[Mount(Path("/h/work"), "/work"), Mount(Path("/h/verify"), "/verify", readonly=True)],
        env={"A": "1"},
    )
    values.update(kw)
    return ContainerSpec(**values)


def test_run_args_has_isolation_mounts_and_command():
    args = run_args(spec())

    assert args[:2] == ["run", "--rm"]
    assert ["--name", "c1"] == args[2:4]
    assert "--userns=keep-id:uid=1000,gid=1000" in args
    assert "--network=none" in args
    assert "--init" in args
    assert args[args.index("--workdir") + 1] == "/work"
    assert "/h/work:/work" in args
    assert "/h/verify:/verify:ro" in args
    assert "A=1" in args
    assert args[-4:] == ["img:1", "bash", "-c", "echo hi"]


def test_secret_env_names_only():
    args = run_args(spec(secret_env={"TOKEN": "s3cret"}))

    assert "TOKEN" in args
    assert not any("s3cret" in a for a in args)


def test_network_value():
    assert "--network=container:srv" in run_args(spec(network="container:srv"))


def write_fake_podman(tmp_path: Path, body: str) -> Path:
    exe = tmp_path / "podman"
    exe.write_text("#!/bin/bash\n" + body)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


def test_run_writes_stdout_stderr_and_passes_secret(tmp_path):
    exe = write_fake_podman(tmp_path, 'echo "out $TOKEN"; echo "args $*" >&2; exit 3\n')
    out, err = tmp_path / "o", tmp_path / "e"

    result = Podman(str(exe)).run(spec(secret_env={"TOKEN": "s3cret"}), out, err, timeout_s=10)

    assert result.exit_code == 3
    assert result.timed_out is False
    assert out.read_text() == "out s3cret\n"
    assert "args run --rm" in err.read_text()
    assert "TOKEN" not in os.environ


def test_run_timeout_stops_container(tmp_path):
    log, pid = tmp_path / "log", tmp_path / "pid"
    exe = write_fake_podman(
        tmp_path,
        f'echo "$*" >> {log}\n'
        f'if [ "$1" = run ]; then echo $$ > {pid}; exec sleep 30; fi\n'
        f'kill "$(< {pid})"\n',
    )

    result = Podman(str(exe)).run(spec(), tmp_path / "o", tmp_path / "e", timeout_s=0.5)

    assert result.timed_out is True
    assert "stop -t 10 c1" in log.read_text()


def test_image_info(tmp_path):
    exe = write_fake_podman(
        tmp_path, 'echo \'[{"Id": "abc", "Digest": "sha256:d", "RepoDigests": [], "Labels": {"x": "1"}}]\'\n'
    )

    info = Podman(str(exe)).image_info("img:1")

    assert info == {"name": "img:1", "id": "abc", "digest": "sha256:d", "labels": {"x": "1"}}


def test_output(tmp_path):
    exe = write_fake_podman(tmp_path, 'echo "2.1.328 (Claude Code)"\n')

    assert Podman(str(exe)).output(spec(command=["claude", "--version"])) == "2.1.328 (Claude Code)"


def test_call_returns_exit_code_and_both_outputs(tmp_path):
    exe = write_fake_podman(tmp_path, 'echo "out $*"; echo err >&2; exit 4\n')

    code, text = Podman(str(exe)).call(["logs", "c1"])

    assert code == 4
    assert "out logs c1" in text and "err" in text


def test_interrupted_run_removes_the_container(tmp_path, monkeypatch):
    exe = tmp_path / "podman"
    exe.write_text(f'#!/bin/sh\nexec {sys.executable} {Path(__file__).parent / "fake_podman.py"} "$@"\n')
    exe.chmod(0o755)
    monkeypatch.setenv("FAKE_PODMAN_DIR", str(tmp_path))
    containers = tmp_path / "containers"
    agent = spec(name="llm-eval-agent-t1-abc")

    def interrupt_when_the_agent_runs():
        while not (containers / f"{agent.name}.json").exists():
            time.sleep(0.01)
        os.kill(os.getpid(), signal.SIGINT)

    threading.Thread(target=interrupt_when_the_agent_runs, daemon=True).start()
    with pytest.raises(KeyboardInterrupt):
        Podman(str(exe)).run(agent, tmp_path / "o", tmp_path / "e", timeout_s=60)

    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    removed = ["rm", "-f", "-t", "10", "--ignore", agent.name]
    assert any(c["event"] == "end" and c["argv"] == removed and c["code"] == 0 for c in calls)
    assert not (containers / f"{agent.name}.json").exists()


def test_call_runs_podman_in_a_new_process_group(tmp_path, monkeypatch):
    exe = write_fake_podman(tmp_path, "ps -o pgid= -p $$\n")

    code, text = Podman(str(exe)).call(["ps"])

    assert int(text) != os.getpgid(0)
