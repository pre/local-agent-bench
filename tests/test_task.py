from pathlib import Path

import pytest

from llm_eval.task import TaskError, find_tasks, load_task

ROOT = Path(__file__).resolve().parents[1]

TASK_TOML = """
id = "{id}"
title = "A title"
category = "bugfix"
language = "go"
quick = true
timeout_s = 600
max_turns = 30
"""


def make_task(tasks_dir: Path, task_id: str, toml: str | None = None) -> Path:
    d = tasks_dir / task_id
    (d / "workspace").mkdir(parents=True)
    (d / "verify").mkdir()
    (d / "solution").mkdir()
    (d / "task.toml").write_text(toml if toml is not None else TASK_TOML.format(id=task_id))
    (d / "prompt.md").write_text("Do the work.\n")
    (d / "verify" / "verify.sh").write_text("true\n")
    return d


def test_loads_task(tmp_path):
    task = load_task(make_task(tmp_path, "t1"))

    assert task.id == "t1"
    assert task.title == "A title"
    assert task.quick is True
    assert task.hard is False
    assert task.timeout_s == 600
    assert task.max_turns == 30
    assert task.prompt == "Do the work.\n"
    assert task.workspace == tmp_path / "t1" / "workspace"
    assert task.verify_dir == tmp_path / "t1" / "verify"
    assert task.solution == tmp_path / "t1" / "solution"


def test_loads_the_hard_flag(tmp_path):
    toml = TASK_TOML.format(id="t1").replace("quick = true", "quick = false\nhard = true")

    assert load_task(make_task(tmp_path, "t1", toml)).hard is True


def test_id_must_match_directory(tmp_path):
    d = make_task(tmp_path, "t1", TASK_TOML.format(id="other"))

    with pytest.raises(TaskError, match="other"):
        load_task(d)


def test_missing_file_is_an_error(tmp_path):
    d = make_task(tmp_path, "t1")
    (d / "verify" / "verify.sh").unlink()

    with pytest.raises(TaskError, match="verify.sh"):
        load_task(d)


def test_missing_key_is_an_error(tmp_path):
    d = make_task(tmp_path, "t1", TASK_TOML.format(id="t1").replace("max_turns = 30", ""))

    with pytest.raises(TaskError, match="max_turns"):
        load_task(d)


def test_find_tasks_returns_all_sorted(tmp_path):
    make_task(tmp_path, "b")
    make_task(tmp_path, "a")
    (tmp_path / "notes.txt").write_text("not a task")

    assert [t.id for t in find_tasks(tmp_path)] == ["a", "b"]


def test_find_tasks_selects_ids_in_given_order(tmp_path):
    make_task(tmp_path, "a")
    make_task(tmp_path, "b")

    assert [t.id for t in find_tasks(tmp_path, ["b", "a"])] == ["b", "a"]


def test_find_tasks_unknown_id(tmp_path):
    make_task(tmp_path, "a")

    with pytest.raises(TaskError, match="nope"):
        find_tasks(tmp_path, ["nope"])


def test_repository_tasks_load():
    ids = [t.id for t in find_tasks(ROOT / "tasks")]

    assert "go-bugfix" in ids


def test_repository_hard_tasks_have_the_hard_flag_and_are_not_quick():
    tasks = find_tasks(ROOT / "tasks")

    assert {t.id for t in tasks if t.hard} == {t.id for t in tasks if t.id.startswith("hard-")}
    assert [t.id for t in tasks if t.hard and t.quick] == []
