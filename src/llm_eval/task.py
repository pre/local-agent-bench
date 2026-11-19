"""Tasks: one directory in tasks/ (see "Task contract" in README.md)."""

import tomllib
from dataclasses import dataclass
from pathlib import Path


class TaskError(Exception):
    pass


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    category: str
    language: str
    quick: bool
    timeout_s: int
    max_turns: int
    dir: Path
    hard: bool = False

    @property
    def prompt(self) -> str:
        return (self.dir / "prompt.md").read_text()

    @property
    def workspace(self) -> Path:
        return self.dir / "workspace"

    @property
    def verify_dir(self) -> Path:
        return self.dir / "verify"

    @property
    def solution(self) -> Path:
        return self.dir / "solution"


REQUIRED_FILES = ("task.toml", "prompt.md", "workspace", "verify/verify.sh", "solution")
REQUIRED_KEYS = ("id", "title", "category", "language", "quick", "timeout_s", "max_turns")


def load_task(task_dir: Path) -> Task:
    for name in REQUIRED_FILES:
        if not (task_dir / name).exists():
            raise TaskError(f"{task_dir}: {name} is missing")
    with (task_dir / "task.toml").open("rb") as f:
        raw = tomllib.load(f)
    missing = [key for key in REQUIRED_KEYS if key not in raw]
    if missing:
        raise TaskError(f"{task_dir}/task.toml: missing keys: {', '.join(missing)}")
    if raw["id"] != task_dir.name:
        raise TaskError(f"{task_dir}/task.toml: id {raw['id']!r} is not the directory name")
    return Task(**{key: raw[key] for key in REQUIRED_KEYS}, dir=task_dir, hard=raw.get("hard", False))


def find_tasks(tasks_dir: Path, ids: list[str] | None = None) -> list[Task]:
    if ids:
        for task_id in ids:
            if not (tasks_dir / task_id / "task.toml").is_file():
                raise TaskError(f"no task {task_id!r} in {tasks_dir}")
        return [load_task(tasks_dir / task_id) for task_id in ids]
    return [load_task(d) for d in sorted(tasks_dir.iterdir()) if (d / "task.toml").is_file()]
