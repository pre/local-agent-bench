"""Paired comparison of two runs on the tasks that both runs have."""

from dataclasses import dataclass

from .report import ConfigStats, Run, _num, _pass_rate, _table, sign_test, wilson

SIGNIFICANCE = 0.05


@dataclass(frozen=True)
class TaskRow:
    task: str
    a: ConfigStats
    b: ConfigStats

    @property
    def better(self) -> str:
        if not (self.a.n and self.b.n):
            return "n/a"
        key_a = (self.a.pass_rate, self.a.mean_score or 0)
        key_b = (self.b.pass_rate, self.b.mean_score or 0)
        return "A" if key_a > key_b else "B" if key_b > key_a else "equal"


def _stats(run: Run, tasks: set[str]) -> ConfigStats:
    config = run.info.get("config") or run.results[0]["config"]
    stats = ConfigStats(config["name"], config["sha256"], [t for t in run.results if t["task"] in tasks])
    stats.label = f"{stats.name} @{stats.sha256[:8]}"
    return stats


def _common_tasks(a: Run, b: Run) -> tuple[list[str], list[str], list[str]]:
    tasks_a, tasks_b = {t["task"] for t in a.results}, {t["task"] for t in b.results}
    return sorted(tasks_a & tasks_b), sorted(tasks_a - tasks_b), sorted(tasks_b - tasks_a)


def task_rows(a: Run, b: Run) -> list[TaskRow]:
    common, _, _ = _common_tasks(a, b)
    return [TaskRow(task, _stats(a, {task}), _stats(b, {task})) for task in common]


def _signed(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:+.{digits}f}"


def _difference(x: float | None, y: float | None) -> float | None:
    return None if x is None or y is None else x - y


def _task_table(rows: list[TaskRow]) -> list[str]:
    header = ["Task", "A passes", "A score", "B passes", "B score", "Pass rate difference (percentage points)",
              "Score difference", "Better"]
    body = []
    for r in rows:
        rate = _difference(r.a.pass_rate, r.b.pass_rate)
        body.append([r.task, f"{r.a.passes}/{r.a.n}", _num(r.a.mean_score, 2), f"{r.b.passes}/{r.b.n}",
                     _num(r.b.mean_score, 2), _signed(rate * 100 if rate is not None else None, 0),
                     _signed(_difference(r.a.mean_score, r.b.mean_score), 2), r.better])
    return _table(header, body)


def _totals(a: ConfigStats, b: ConfigStats, counts: dict[str, int]) -> list[str]:
    rate = _difference(a.pass_rate, b.pass_rate)
    body = [
        ["Pass rate (95 % interval)", _pass_rate(a.passes, a.n), _pass_rate(b.passes, b.n),
         _signed(rate * 100 if rate is not None else None, 0) + " percentage points"],
        ["Mean score", _num(a.mean_score, 2), _num(b.mean_score, 2), _signed(_difference(a.mean_score, b.mean_score), 2)],
        ["Median wall s", _num(a.median_wall), _num(b.median_wall), _signed(_difference(a.median_wall, b.median_wall))],
        ["Decode tok/s", _num(a.decode_tps), _num(b.decode_tps), _signed(_difference(a.decode_tps, b.decode_tps))],
        ["Harness errors", a.harness_errors, b.harness_errors, ""],
    ]
    return _table(["", "A", "B", "A minus B"], body) + [
        "", f"Tasks: A better: {counts['A']}, equal: {counts['equal']}, B better: {counts['B']}."]


def _noise(a: ConfigStats, b: ConfigStats, counts: dict[str, int]) -> list[str]:
    lo_a, hi_a = wilson(a.passes, a.n)
    lo_b, hi_b = wilson(b.passes, b.n)
    overlap = lo_a <= hi_b and lo_b <= hi_a
    wins, losses = counts["A"], counts["B"]
    p = sign_test(wins, losses)
    smallest = sign_test(wins + losses, 0)
    lines = [
        f"- Pass rate: the 95 % intervals {'overlap' if overlap else 'do not overlap'}"
        f" (A {lo_a * 100:.0f} to {hi_a * 100:.0f} %, B {lo_b * 100:.0f} to {hi_b * 100:.0f} %).",
        f"- Sign test on the tasks: A better {wins}, B better {losses}, p = {p:.3f}.",
    ]
    if smallest >= SIGNIFICANCE:
        lines.append(f"- With {wins + losses} tasks that differ, the smallest possible p value is {smallest:.2f}."
                     " This test cannot show a significant difference with this number of tasks.")
    inside = overlap or p >= SIGNIFICANCE
    verdict = ("The difference is inside the noise. Do not rank A and B with these data." if inside else
               "The difference is larger than the noise: the intervals do not overlap and p is below 0.05.")
    return lines + ["", f"**Result: {verdict}**"]


def compare_runs(run_a: Run, run_b: Run) -> str:
    common, only_a, only_b = _common_tasks(run_a, run_b)
    a, b = _stats(run_a, set(common)), _stats(run_b, set(common))
    rows = task_rows(run_a, run_b)
    counts = {key: sum(r.better == key for r in rows) for key in ("A", "B", "equal")}
    lines = ["# Comparison", "", f"- A: `{run_a.id}` ({a.label})", f"- B: `{run_b.id}` ({b.label})"]
    for side, run in (("A", run_a), ("B", run_b)):
        if run.partial:
            lines.append(f"- {side} is PARTIAL: the run is not finished or has fewer results than expected.")
    lines += ["", "## Tasks", ""] + _task_table(rows)
    not_compared = [f"{t} (only in A)" for t in only_a] + [f"{t} (only in B)" for t in only_b]
    if not_compared:
        lines += ["", f"Not compared: {', '.join(not_compared)}."]
    lines += ["", "## Totals for the common tasks", ""] + _totals(a, b, counts)
    lines += ["", "## Noise", ""] + _noise(a, b, counts)
    return "\n".join(lines) + "\n"
