"""Selfcheck of a task without an LLM: the check must fail on the start files
and must pass with the reference solution."""

from dataclasses import dataclass, field
from pathlib import Path

from .task import Task
from .workspace import apply_solution, init_workspace, run_check


@dataclass
class SelfcheckResult:
    task_id: str
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def selfcheck_task(podman, image: str, task: Task, scratch: Path) -> SelfcheckResult:
    result = SelfcheckResult(task.id)

    work = scratch / "start" / "work"
    baseline = init_workspace(task, work)
    check = run_check(podman, image, task, work, scratch / "start" / "out", baseline)
    if check.error:
        result.problems.append(f"start: {check.error}")
    elif check.verify["passed"]:
        result.problems.append("start: the check passes on the untouched workspace")

    work = scratch / "solution" / "work"
    baseline = init_workspace(task, work)
    error = apply_solution(podman, image, task, work, scratch / "solution" / "out")
    if error:
        result.problems.append(f"solution: {error}")
        return result
    check = run_check(podman, image, task, work, scratch / "solution" / "out", baseline)
    if check.error:
        result.problems.append(f"solution: {check.error}")
    elif not check.verify["passed"]:
        failed = [c["name"] for c in check.verify["checks"] if not c["passed"]]
        result.problems.append(f"solution: the check fails ({', '.join(failed)})")
    return result
