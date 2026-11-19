from pathlib import Path

from fakes import FakePodman, check_by_marker
from llm_eval.selfcheck import selfcheck_task
from llm_eval.task import load_task
from test_task import make_task


def task(tmp_path: Path, apply_sh: str | None = None):
    d = make_task(tmp_path / "tasks", "t1")
    (d / "workspace" / "main.txt").write_text("bug\n")
    (d / "solution" / "fixed.txt").write_text("fix\n")
    if apply_sh is not None:
        (d / "solution" / "apply.sh").write_text(apply_sh)
    return load_task(d)


def test_passes_when_check_fails_on_start_and_passes_on_solution(tmp_path):
    podman = FakePodman(check=check_by_marker("fixed.txt"))

    result = selfcheck_task(podman, "img", task(tmp_path), tmp_path / "scratch")

    assert result.ok, result.problems
    assert len(podman.of_kind("check")) == 2


def test_fails_when_check_passes_on_untouched_workspace(tmp_path):
    podman = FakePodman(check=check_by_marker("main.txt"))

    result = selfcheck_task(podman, "img", task(tmp_path), tmp_path / "scratch")

    assert not result.ok
    assert any("start" in p for p in result.problems)


def test_fails_when_check_fails_on_solution(tmp_path):
    podman = FakePodman(check=check_by_marker("nothing.txt"))

    result = selfcheck_task(podman, "img", task(tmp_path), tmp_path / "scratch")

    assert not result.ok
    assert any("solution" in p for p in result.problems)


def test_fails_on_harness_error(tmp_path):
    podman = FakePodman(check=lambda s, m: (1, ""))

    result = selfcheck_task(podman, "img", task(tmp_path), tmp_path / "scratch")

    assert not result.ok
    assert any("exit code 1" in p for p in result.problems)


def test_runs_apply_sh_after_the_copy(tmp_path):
    def apply(spec, m):
        assert (m["/work"] / "fixed.txt").exists()
        (m["/work"] / "applied.txt").write_text("")
        return 0, ""

    podman = FakePodman(solution=apply, check=check_by_marker("applied.txt"))

    result = selfcheck_task(podman, "img", task(tmp_path, apply_sh="touch applied.txt\n"), tmp_path / "scratch")

    assert result.ok, result.problems


def test_fails_when_apply_sh_fails(tmp_path):
    podman = FakePodman(solution=lambda s, m: (3, ""), check=check_by_marker())

    result = selfcheck_task(podman, "img", task(tmp_path, apply_sh="exit 3\n"), tmp_path / "scratch")

    assert not result.ok
    assert any("apply.sh" in p for p in result.problems)
