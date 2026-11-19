"""The workspace of a trial: start commit, reference solution, diff and hidden check.

Only the start commit runs git on the host, on files from the repository. All
work on files that a model or a task script changed runs in a container.
"""

import json
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from .podman import ContainerSpec, Mount, RunResult
from .task import Task

CHECK_TIMEOUT_S = 300
SOLUTION_TIMEOUT_S = 300
DIFF_TIMEOUT_S = 120

# A fixed identity and date give the same start commit SHA in each trial.
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "eval",
    "GIT_AUTHOR_EMAIL": "eval@localhost",
    "GIT_COMMITTER_NAME": "eval",
    "GIT_COMMITTER_EMAIL": "eval@localhost",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
}


@dataclass(frozen=True)
class CheckResult:
    verify: dict | None
    error: str | None
    run: RunResult


def container_name(kind: str, task_id: str) -> str:
    return f"llm-eval-{kind}-{task_id}-{uuid.uuid4().hex[:8]}"


def init_workspace(task: Task, work: Path) -> str:
    """Copy the start files to `work` and make the start commit. Return its SHA."""
    shutil.copytree(task.workspace, work, symlinks=True)
    env = {**os.environ, **GIT_ENV}

    def git(*args: str) -> str:
        proc = subprocess.run(["git", "-C", str(work), *args], env=env, capture_output=True, text=True, check=True)
        return proc.stdout.strip()

    git("init", "-q", "-b", "main")
    git("config", "user.name", "eval")
    git("config", "user.email", "eval@localhost")
    git("add", "-A")
    git("commit", "-q", "--allow-empty", "-m", "chore: Start the task")
    return git("rev-parse", "HEAD")


def apply_solution(podman, image: str, task: Task, work: Path, log_dir: Path) -> str | None:
    """Copy the reference solution over `work` and run solution/apply.sh. Return an error or None."""
    shutil.copytree(task.solution, work, dirs_exist_ok=True, symlinks=True,
                    ignore=lambda d, names: ["apply.sh"] if Path(d) == task.solution else [])
    if not (task.solution / "apply.sh").exists():
        return None
    log_dir.mkdir(parents=True, exist_ok=True)
    spec = ContainerSpec(
        name=container_name("solution", task.id),
        image=image,
        command=["bash", "/solution/apply.sh"],
        mounts=[Mount(work, "/work"), Mount(task.solution, "/solution", readonly=True)],
    )
    result = podman.run(spec, log_dir / "solution.stdout", log_dir / "solution.stderr", SOLUTION_TIMEOUT_S)
    if result.timed_out or result.exit_code != 0:
        return f"solution/apply.sh failed: exit code {result.exit_code}, timeout {result.timed_out}"
    return None


def collect_diff(podman, image: str, work: Path, diff_file: Path, baseline: str, task_id: str) -> RunResult:
    """Write the diff of the work against the start commit, new files included."""
    spec = ContainerSpec(
        name=container_name("diff", task_id),
        image=image,
        command=["bash", "-c", 'git add -A && git diff --cached --binary "$EVAL_BASELINE"'],
        mounts=[Mount(work, "/work")],
        env={"EVAL_BASELINE": baseline},
    )
    return podman.run(spec, diff_file, diff_file.parent / "diff.stderr", DIFF_TIMEOUT_S)


def run_check(podman, image: str, task: Task, work: Path, out_dir: Path, baseline: str) -> CheckResult:
    """Run verify/verify.sh in a container with no network. out_dir gets verify.json and the logs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = ContainerSpec(
        name=container_name("check", task.id),
        image=image,
        command=["bash", "/verify/verify.sh"],
        mounts=[Mount(work, "/work"), Mount(task.verify_dir, "/verify", readonly=True), Mount(out_dir, "/out")],
        env={"EVAL_BASELINE": baseline},
    )
    run = podman.run(spec, out_dir / "check.stdout", out_dir / "check.stderr", CHECK_TIMEOUT_S)
    if run.timed_out:
        return CheckResult(None, f"verify.sh timeout after {CHECK_TIMEOUT_S} s", run)
    if run.exit_code != 0:
        return CheckResult(None, f"verify.sh exit code {run.exit_code}", run)
    path = out_dir / "verify.json"
    if not path.exists():
        return CheckResult(None, "verify.json is missing", run)
    try:
        verify = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return CheckResult(None, f"verify.json is invalid: {e}", run)
    problem = verify_problem(verify)
    if problem:
        return CheckResult(None, f"verify.json is invalid: {problem}", run)
    return CheckResult(verify, None, run)


def verify_problem(verify: object) -> str | None:
    if not isinstance(verify, dict):
        return "not an object"
    if not isinstance(verify.get("passed"), bool):
        return "'passed' is not a boolean"
    score = verify.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
        return "'score' is not a number from 0 to 1"
    checks = verify.get("checks")
    if not isinstance(checks, list):
        return "'checks' is not a list"
    for check in checks:
        if not (isinstance(check, dict) and isinstance(check.get("name"), str)
                and isinstance(check.get("passed"), bool)):
            return f"bad check {check!r}"
    return None
