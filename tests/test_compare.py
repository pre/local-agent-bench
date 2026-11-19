from llm_eval.compare import compare_runs, task_rows
from llm_eval.report import load_run
from runfiles import SHA_B, server, trial, write_run


def run_of(tmp_path, name, passes: dict[str, int], reps=3, sha="a" * 64, wall=100.0, decode=None, extra=()):
    trials = [trial(task, r, name=name, sha=sha, passed=r <= k, wall=wall,
                    server=server(1000, 10.0, decode[0], decode[1]) if decode else None)
              for task, k in passes.items() for r in range(1, reps + 1)]
    return load_run(write_run(tmp_path / name, trials + list(extra), reps=reps))


def test_task_rows_pair_common_tasks(tmp_path):
    a = run_of(tmp_path, "a", {"t1": 3, "t2": 1, "t3": 2, "only-a": 3})
    b = run_of(tmp_path, "b", {"t1": 1, "t2": 2, "t3": 2, "only-b": 0}, sha=SHA_B)

    rows = task_rows(a, b)

    assert [(r.task, r.better) for r in rows] == [("t1", "A"), ("t2", "B"), ("t3", "equal")]
    assert rows[0].a.passes == 3 and rows[0].b.passes == 1


def test_equal_pass_count_is_decided_by_mean_score(tmp_path):
    a = load_run(write_run(tmp_path / "a", [trial("t1", passed=False, score=0.8)]))
    b = load_run(write_run(tmp_path / "b", [trial("t1", passed=False, score=0.2, sha=SHA_B)]))

    assert task_rows(a, b)[0].better == "A"


def test_compare_inside_the_noise(tmp_path):
    a = run_of(tmp_path, "a", {"t1": 3, "t2": 1, "t3": 2, "only-a": 3}, wall=100.0, decode=(300, 10.0))
    b = run_of(tmp_path, "b", {"t1": 1, "t2": 2, "t3": 2, "only-b": 0}, wall=150.0, decode=(250, 10.0))

    text = compare_runs(a, b)

    assert "| t1 | 3/3 | 1.00 | 1/3 | 0.33 | +67 | +0.67 | A |" in text
    assert "Not compared: only-a (only in A), only-b (only in B)." in text
    assert "A better: 1, equal: 1, B better: 1" in text
    assert "| Median wall s | 100.0 | 150.0 | -50.0 |" in text
    assert "| Decode tok/s | 30.0 | 25.0 | +5.0 |" in text
    assert "the smallest possible p value is 0.50" in text
    assert "inside the noise" in text


def test_compare_larger_than_the_noise(tmp_path):
    tasks = [f"t{i}" for i in range(8)]
    a = run_of(tmp_path, "a", {t: 3 for t in tasks})
    b = run_of(tmp_path, "b", {t: 0 for t in tasks})

    text = compare_runs(a, b)

    assert "intervals do not overlap" in text
    assert "p = 0.008" in text
    assert "larger than the noise" in text


def test_compare_skips_tasks_with_only_harness_errors(tmp_path):
    a = run_of(tmp_path, "a", {"t1": 1}, reps=1, extra=[trial("t2", passed=False, reason="harness_error")])
    b = run_of(tmp_path, "b", {"t1": 1, "t2": 1}, reps=1)

    rows = task_rows(a, b)

    assert [(r.task, r.better) for r in rows] == [("t1", "equal"), ("t2", "n/a")]


def test_compare_marks_partial_runs(tmp_path):
    a = load_run(write_run(tmp_path / "a", [trial("t1")], finished=False))
    b = load_run(write_run(tmp_path / "b", [trial("t1")]))

    assert "A is PARTIAL" in compare_runs(a, b)
