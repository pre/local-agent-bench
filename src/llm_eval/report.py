"""Read the result files of runs and write a Markdown report.

A configuration is a name plus the SHA-256 of its values. Trials with the
failure reason harness_error are not model failures: they are not in the pass
rate and the score, the report counts them separately.
"""

import json
import math
import statistics
from collections import Counter
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

HARNESS_ERROR = "harness_error"
Z95 = 1.96


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """The Wilson score interval of k passes in n trials."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def sign_test(wins: int, losses: int) -> float:
    """The two-sided p value of the exact sign test. Ties are not counted."""
    n = wins + losses
    tail = sum(math.comb(n, i) for i in range(min(wins, losses) + 1)) / 2**n
    return min(1.0, 2 * tail)


@dataclass
class Run:
    dir: Path
    info: dict  # run.json, empty when the file is missing
    results: list[dict]
    probes: dict[str, dict]

    @property
    def id(self) -> str:
        return self.info.get("run_id", self.dir.name)

    @property
    def expected(self) -> int | None:
        if "tasks" not in self.info:
            return None
        return len(self.info["tasks"]) * self.info.get("reps", 1)

    @property
    def partial(self) -> bool:
        """True when run.json exists and the run is not finished or has missing results."""
        return bool(self.info) and (not self.info.get("finished_at") or len(self.results) < (self.expected or 0))


def load_run(run_dir: Path) -> Run:
    run_dir = Path(run_dir)
    info_file = run_dir / "run.json"
    info = json.loads(info_file.read_text()) if info_file.exists() else {}
    results = [json.loads(p.read_text()) for p in sorted(run_dir.glob("*/result.json"))]
    for result in results:
        result.setdefault("run_id", run_dir.name)
    probes = {p.stem: json.loads(p.read_text()) for p in sorted((run_dir / "probes").glob("*.json"))}
    return Run(run_dir, info, results, probes)


def _observed(trials: list[dict], observer: str) -> list[dict]:
    return [t[observer] for t in trials if t.get(observer)]


def _rate(values: list[dict], amount: str, per: str) -> float | None:
    pairs = [(v[amount], v[per]) for v in values if v.get(amount) is not None and v.get(per) is not None]
    total = sum(p for _, p in pairs)
    return sum(a for a, _ in pairs) / total if total else None


def _extreme(values: list[dict], key: str, pick) -> int | None:
    found = [v[key] for v in values if v.get(key) is not None]
    return pick(found) if found else None


@dataclass
class ConfigStats:
    name: str
    sha256: str
    trials: list[dict] = field(default_factory=list)
    label: str = ""

    @cached_property
    def counted(self) -> list[dict]:
        return [t for t in self.trials if t["failure_reason"] != HARNESS_ERROR]

    @property
    def n(self) -> int:
        return len(self.counted)

    @property
    def passes(self) -> int:
        return sum(t["passed"] for t in self.counted)

    @property
    def harness_errors(self) -> int:
        return len(self.trials) - self.n

    @property
    def pass_rate(self) -> float | None:
        return self.passes / self.n if self.n else None

    @property
    def interval(self) -> tuple[float, float]:
        return wilson(self.passes, self.n)

    @property
    def mean_score(self) -> float | None:
        scores = [t["score"] for t in self.counted if t["score"] is not None]
        return statistics.mean(scores) if scores else None

    @property
    def median_wall(self) -> float | None:
        return statistics.median(t["wall_time_s"] for t in self.counted) if self.counted else None

    @property
    def total_wall(self) -> float:
        return sum(t["wall_time_s"] or 0 for t in self.trials)

    @property
    def failures(self) -> Counter:
        return Counter(t["failure_reason"] for t in self.counted if not t["passed"])

    @property
    def prompt_tps(self) -> float | None:
        return _rate(_observed(self.trials, "server"), "prompt_tokens", "prompt_seconds")

    @property
    def decode_tps(self) -> float | None:
        return _rate(_observed(self.trials, "server"), "decode_tokens", "decode_seconds")

    @property
    def draft_acceptance(self) -> float | None:
        return _rate(_observed(self.trials, "server"), "draft_accepted", "draft_generated")

    @property
    def gtt_peak_mib(self) -> int | None:
        return _extreme(_observed(self.trials, "memory"), "gtt_used_peak_mib", max)

    @property
    def mem_available_min_mib(self) -> int | None:
        return _extreme(_observed(self.trials, "memory"), "mem_available_min_mib", min)

    @property
    def swap_free_min_mib(self) -> int | None:
        return _extreme(_observed(self.trials, "memory"), "swap_free_min_mib", min)


def config_stats(runs: list[Run]) -> list[ConfigStats]:
    """One entry for each configuration (name and SHA-256), sorted by pass rate,
    then by median wall time."""
    groups: dict[tuple[str, str], ConfigStats] = {}
    for run in runs:
        for t in run.results:
            key = (t["config"]["name"], t["config"]["sha256"])
            groups.setdefault(key, ConfigStats(*key)).trials.append(t)
    names = Counter(name for name, _ in groups)
    for stats in groups.values():
        stats.label = f"{stats.name} @{stats.sha256[:8]}" if names[stats.name] > 1 else stats.name
    return sorted(groups.values(), key=lambda s: (-(s.pass_rate if s.n else -1), s.median_wall or 0, s.label))


def _num(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _gib(mib: int | None) -> str:
    return "n/a" if mib is None else f"{mib / 1024:.1f}"


def _trials(n: int) -> str:
    return f"{n} trial" if n == 1 else f"{n} trials"


def _pct(value: float) -> str:
    return f"{value * 100:.0f} %"


def _pass_rate(passes: int, n: int) -> str:
    if n == 0:
        return "0/0"
    lo, hi = wilson(passes, n)
    return f"{passes}/{n}, {_pct(passes / n)} ({lo * 100:.0f} to {hi * 100:.0f} %)"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]


def _runs_section(runs: list[Run]) -> list[str]:
    lines = ["## Runs", ""]
    for run in runs:
        found = f"{len(run.results)} of {_trials(run.expected)}" if run.expected else _trials(len(run.results))
        state = "PARTIAL, " if run.partial else ""
        if not run.info:
            lines.append(f"- `{run.id}`: no run.json, {found}")
            continue
        lines.append(f"- `{run.id}` ({run.info['config']['name']}): {state}{found}, started"
                     f" {run.info.get('started_at')}, finished {run.info.get('finished_at', 'no')}")
    if any(run.partial for run in runs):
        lines += ["", "A PARTIAL run is not finished or has fewer results than tasks times repetitions."
                  " Its values can change."]
    return lines


def _config_table(rows: list[ConfigStats]) -> list[str]:
    header = ["Configuration", "Trials", "Pass rate (95 % interval)", "Mean score", "Median wall s",
              "Total wall s", "Prompt tok/s", "Decode tok/s", "Draft acceptance", "GTT peak GiB",
              "Min MemAvailable GiB", "Min SwapFree GiB", "Failures", "Harness errors"]
    body = []
    for s in rows:
        failures = ", ".join(f"{reason} {count}" for reason, count in sorted(s.failures.items())) or "-"
        body.append([s.label, s.n, _pass_rate(s.passes, s.n), _num(s.mean_score, 2), _num(s.median_wall),
                     _num(s.total_wall), _num(s.prompt_tps), _num(s.decode_tps), _num(s.draft_acceptance, 2),
                     _gib(s.gtt_peak_mib), _gib(s.mem_available_min_mib), _gib(s.swap_free_min_mib), failures,
                     s.harness_errors])
    lines = ["## Configurations", ""] + _table(header, body)
    for name in sorted({s.name for s in rows}):
        shas = [s for s in rows if s.name == name]
        if len(shas) > 1:
            lines += ["", f"Configuration `{name}` has {len(shas)} different SHA-256 values."
                      " Each value is a separate row."]
    lines += ["", "Pass rate and mean score do not include harness errors. Median wall time is for the counted"
              " trials, total wall time is for all trials. Speed and memory values are for all trials."]
    return lines


def _matrix_cell(trials: list[dict]) -> str:
    if not trials:
        return "-"
    counted = [t for t in trials if t["failure_reason"] != HARNESS_ERROR]
    parts = [f"{sum(t['passed'] for t in counted)}/{len(counted)}"]
    scores = [t["score"] for t in counted if t["score"] is not None]
    if any(0 < s < 1 for s in scores):
        parts.append(f"score {statistics.mean(scores):.2f}")
    errors = len(trials) - len(counted)
    if errors:
        parts.append(f"{errors} harness error" + ("s" if errors > 1 else ""))
    return ", ".join(parts)


def _matrix(rows: list[ConfigStats]) -> list[str]:
    tasks = sorted({t["task"] for s in rows for t in s.trials})
    body = [[task] + [_matrix_cell([t for t in s.trials if t["task"] == task]) for s in rows] for task in tasks]
    return ["## Tasks", "", "Passes of the counted repetitions. The mean score is shown when a trial has a"
            " partial score.", ""] + _table(["Task"] + [s.label for s in rows], body)


def _failed_checks(trial: dict) -> str:
    checks = (trial.get("verify") or {}).get("checks") or []
    return ", ".join(c["name"] for c in checks if not c["passed"]) or "-"


def _failures(rows: list[ConfigStats]) -> list[str]:
    lines = ["## Failed trials"]
    header = ["Run", "Task", "Rep", "Reason", "Score", "Failed checks", "Turns", "Wall s"]
    for s in rows:
        failed = sorted((t for t in s.trials if not t["passed"]), key=lambda t: (t["run_id"], t["task"], t["rep"]))
        lines += ["", f"### {s.label}", ""]
        if not failed:
            lines.append("No failed trials.")
            continue
        lines += _table(header, [[t["run_id"], t["task"], t["rep"], t["failure_reason"], _num(t["score"], 2),
                                  _failed_checks(t), "n/a" if t["turns"] is None else t["turns"], _num(t["wall_time_s"])] for t in failed])
    return lines


def _limits(rows: list[ConfigStats]) -> list[str]:
    lines = ["## Limits", ""]
    for s in rows:
        lo, hi = s.interval
        rate = f"pass rate {_pct(s.pass_rate)}" if s.n else "no counted trials"
        lines.append(f"- {s.label}: {_trials(s.n)}, {rate}, 95 % interval {lo * 100:.0f} to {hi * 100:.0f} %,"
                     f" width {(hi - lo) * 100:.0f} percentage points.")
    smallest = min(s.n for s in rows)
    lo, hi = wilson(smallest // 2, smallest)
    lines += ["", f"With {_trials(smallest)}, the 95 % interval at a pass rate near 50 % is {(hi - lo) * 100:.0f}"
              " percentage points wide. Do not rank two configurations when their intervals overlap: the"
              " difference can be noise. Use `llm-eval compare` for a paired comparison of two runs."]
    return lines


def _speed_probe(speed: dict) -> list[str]:
    header = ["Target tokens", "Prompt tokens", "Cached", "Prompt s", "Prompt tok/s", "Decode tokens", "Decode s",
              "Decode tok/s", "TTFT s", "Draft acceptance"]
    body = []
    for r in speed["results"]:
        if r.get("error"):
            body.append([r["target_tokens"], f"error: {r['error']}"] + [""] * 8)
            continue
        body.append([r["target_tokens"], r["prompt_tokens"], r["cache_tokens"], _num(r["prompt_seconds"]),
                     _num(r["prompt_tps"]), r["decode_tokens"], _num(r["decode_seconds"]), _num(r["decode_tps"]),
                     _num(r["ttft_s"]), _num(r["draft_acceptance"], 2)])
    lines = ["### Speed", "", f"Model `{speed['model']}`, {speed.get('decode_tokens')} decode tokens for each"
             " request, thinking off.", ""] + _table(header, body)
    for skipped in speed.get("skipped", []):
        lines += ["", f"Not measured: {skipped['target_tokens']} tokens, {skipped['reason']}."]
    return lines


def _protocol_probe(protocol: dict) -> list[str]:
    cases = protocol["cases"]
    body = [[c["name"], c["http_status"] or "-", "pass" if c["passed"] else "FAIL",
             (c.get("error") or c.get("note") or "").replace("|", "/").replace("\n", " ")[:200]] for c in cases]
    passed = sum(c["passed"] for c in cases)
    return ["### Protocol", "", f"Model `{protocol['model']}`: {passed} of {len(cases)} cases pass.", ""] + \
        _table(["Case", "HTTP", "Result", "Note"], body)


def _probes(runs: list[Run]) -> list[str]:
    lines = []
    for run in runs:
        if not run.probes:
            continue
        lines += ["", f"## Probes: {run.id}"]
        if "speed" in run.probes:
            lines += [""] + _speed_probe(run.probes["speed"])
        if "protocol" in run.probes:
            lines += [""] + _protocol_probe(run.probes["protocol"])
    return lines


def render_report(runs: list[Run]) -> str:
    lines = ["# Evaluation report", ""] + _runs_section(runs)
    rows = config_stats(runs)
    if rows:
        lines += [""] + _config_table(rows) + [""] + _matrix(rows) + [""] + _failures(rows) + [""] + _limits(rows)
    else:
        lines += ["", "No trial results."]
    lines += _probes(runs)
    return "\n".join(lines) + "\n"
