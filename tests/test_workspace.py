import json
import subprocess
from pathlib import Path

from fakes import FakePodman, check_by_marker, write_verify
from llm_eval.workspace import CHECK_TIMEOUT_S, apply_solution, collect_diff, init_workspace, run_check
from test_task import make_task
from llm_eval.task import load_task


def git(work: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(work), *args], capture_output=True, text=True, check=True).stdout


def task_with_files(tmp_path: Path):
    d = make_task(tmp_path / "tasks", "t1")
    (d / "workspace" / "a.txt").write_text("start\n")
    (d / "workspace" / "sub").mkdir()
    (d / "workspace" / "sub" / "b.txt").write_text("b\n")
    return load_task(d)


def test_init_workspace_makes_one_commit(tmp_path):
    task = task_with_files(tmp_path)
    work = tmp_path / "work"

    sha = init_workspace(task, work)

    assert (work / "sub" / "b.txt").read_text() == "b\n"
    assert git(work, "rev-parse", "HEAD").strip() == sha
    assert git(work, "log", "--format=%s|%an <%ae>").strip() == "chore: Start the task|eval <eval@localhost>"
    assert git(work, "branch", "--show-current").strip() == "main"
    assert git(work, "config", "user.email").strip() == "eval@localhost"
    assert git(work, "status", "--porcelain") == ""


def test_init_workspace_sha_is_the_same_each_time(tmp_path):
    task = task_with_files(tmp_path)

    assert init_workspace(task, tmp_path / "w1") == init_workspace(task, tmp_path / "w2")


def test_run_check_reads_verify_json(tmp_path):
    task = task_with_files(tmp_path)
    work, out = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    (work / "fixed.txt").write_text("")
    podman = FakePodman(check=check_by_marker())

    result = run_check(podman, "img", task, work, out, "abc123")

    assert result.error is None
    assert result.verify["passed"] is True
    spec = podman.specs[0]
    assert spec.command == ["bash", "/verify/verify.sh"]
    assert spec.network == "none"
    assert spec.env == {"EVAL_BASELINE": "abc123"}
    assert {m.container: m.readonly for m in spec.mounts} == {"/work": False, "/verify": True, "/out": False}
    assert podman.timeouts == [CHECK_TIMEOUT_S]
    assert (out / "check.stdout").read_text() == "check output\n"
    assert (out / "check.stderr").exists()


def test_run_check_missing_file_is_an_error(tmp_path):
    task = task_with_files(tmp_path)
    podman = FakePodman(check=lambda s, m: (0, ""))

    result = run_check(podman, "img", task, tmp_path, tmp_path / "out", "abc")

    assert result.verify is None
    assert "missing" in result.error


def test_run_check_exit_code_is_an_error(tmp_path):
    task = task_with_files(tmp_path)

    def fail(spec, m):
        write_verify(m["/out"], True)
        return 2, ""

    result = run_check(FakePodman(check=fail), "img", task, tmp_path, tmp_path / "out", "abc")

    assert "exit code 2" in result.error


def test_run_check_timeout_is_an_error(tmp_path):
    task = task_with_files(tmp_path)

    result = run_check(FakePodman(check=lambda s, m: ("timeout", "")), "img", task, tmp_path, tmp_path / "out", "a")

    assert "timeout" in result.error


def test_run_check_invalid_json_is_an_error(tmp_path):
    task = task_with_files(tmp_path)
    cases = ["not json", json.dumps({"passed": True}), json.dumps({"passed": "yes", "score": 1, "checks": []}),
             json.dumps({"passed": True, "score": 2, "checks": []}),
             json.dumps({"passed": True, "score": 1, "checks": [{"name": 1, "passed": True}]})]
    for text in cases:
        def write(spec, m, text=text):
            (m["/out"] / "verify.json").write_text(text)
            return 0, ""

        result = run_check(FakePodman(check=write), "img", task, tmp_path, tmp_path / "out", "a")

        assert result.verify is None, text
        assert "invalid" in result.error, text


def test_apply_solution_copies_files_without_apply_sh(tmp_path):
    task = task_with_files(tmp_path)
    (task.solution / "a.txt").write_text("solved\n")
    work = tmp_path / "work"
    init_workspace(task, work)
    podman = FakePodman()

    error = apply_solution(podman, "img", task, work, tmp_path / "logs")

    assert error is None
    assert (work / "a.txt").read_text() == "solved\n"
    assert podman.specs == []


def test_apply_solution_runs_apply_sh_in_a_container(tmp_path):
    task = task_with_files(tmp_path)
    (task.solution / "apply.sh").write_text("git commit -am fix\n")
    work = tmp_path / "work"
    init_workspace(task, work)
    podman = FakePodman()

    error = apply_solution(podman, "img", task, work, tmp_path / "logs")

    assert error is None
    assert not (work / "apply.sh").exists()
    spec = podman.specs[0]
    assert spec.command == ["bash", "/solution/apply.sh"]
    assert spec.network == "none"
    assert {m.container: m.readonly for m in spec.mounts} == {"/work": False, "/solution": True}


def test_apply_solution_failure(tmp_path):
    task = task_with_files(tmp_path)
    (task.solution / "apply.sh").write_text("exit 1\n")
    podman = FakePodman(solution=lambda s, m: (1, ""))

    error = apply_solution(podman, "img", task, tmp_path / "w", tmp_path / "logs")

    assert "exit code 1" in error


def test_collect_diff_runs_git_in_a_container(tmp_path):
    podman = FakePodman(diff=lambda s, m: (0, "diff --git a/x b/x\n"))

    collect_diff(podman, "img", tmp_path / "work", tmp_path / "agent.diff", "base1", "t1")

    assert (tmp_path / "agent.diff").read_text() == "diff --git a/x b/x\n"
    spec = podman.specs[0]
    assert spec.network == "none"
    assert spec.env == {"EVAL_BASELINE": "base1"}
    assert "git diff --cached --binary" in spec.command[-1]
