"""Build run directories with result.json files for the report tests."""

import json
from pathlib import Path

SHA_A = "a" * 64
SHA_B = "b" * 64


def trial(task: str, rep: int = 1, passed: bool = True, reason: str | None = None, score: float | None = None,
          wall: float = 100.0, name: str = "c1", sha: str = SHA_A, server: dict | None = None,
          memory: dict | None = None, failed_checks: tuple[str, ...] = (), turns: int = 10,
          started: str = "2026-11-19T10:00:00+00:00", hard: bool | None = None) -> dict:
    if score is None and reason != "harness_error":
        score = 1.0 if passed else 0.0
    checks = [{"name": "build", "passed": True}] + [{"name": n, "passed": False} for n in failed_checks]
    extra = {} if hard is None else {"hard": hard}  # an older result has no "hard" key
    return {
        **extra, "schema": 1, "task": task, "rep": rep, "config": {"name": name, "path": f"configs/{name}.toml", "sha256": sha},
        "passed": passed, "score": score, "failure_reason": None if passed else (reason or "verify_failed"),
        "failure_detail": None, "wall_time_s": wall, "turns": turns,
        "verify": {"passed": passed, "score": score, "checks": checks} if score is not None else None,
        "server": server, "memory": memory, "started_at": started,
    }


def server(prompt_tokens: int, prompt_s: float, decode_tokens: int, decode_s: float,
           accepted: int | None = None, generated: int | None = None) -> dict:
    return {
        "requests": 1, "prompt_tokens": prompt_tokens, "prompt_seconds": prompt_s,
        "prompt_tps": prompt_tokens / prompt_s, "decode_tokens": decode_tokens, "decode_seconds": decode_s,
        "decode_tps": decode_tokens / decode_s, "draft_accepted": accepted, "draft_generated": generated,
        "draft_acceptance": accepted / generated if generated else None,
    }


def memory(gtt_peak: int, mem_min: int, swap_min: int, gtt_start: int = 1000, psi_full: float = 0.1) -> dict:
    return {"gtt_used_start_mib": gtt_start, "gtt_used_peak_mib": gtt_peak, "mem_available_min_mib": mem_min,
            "swap_free_min_mib": swap_min, "psi_some_avg10_max": 0.5, "psi_full_avg10_max": psi_full, "samples": 60}


def write_run(run_dir: Path, trials: list[dict], tasks: list[str] | None = None, reps: int = 1,
              finished: bool = True, name: str | None = None, sha: str | None = None,
              server: dict | None = None, probe_memory: dict | None = None) -> Path:
    run_dir.mkdir(parents=True)
    first = trials[0]["config"] if trials else {"name": "c1", "sha256": SHA_A}
    info = {
        "run_id": run_dir.name,
        "config": {"name": name or first["name"], "path": "configs/x.toml", "sha256": sha or first["sha256"]},
        "tasks": tasks if tasks is not None else sorted({t["task"] for t in trials}),
        "reps": reps,
        "started_at": "2026-11-19T10:00:00+00:00",
    }
    if finished:
        info["finished_at"] = "2026-11-19T11:00:00+00:00"
    if server:
        info["server"] = server
    (run_dir / "run.json").write_text(json.dumps(info))
    if probe_memory:
        (run_dir / "probes").mkdir()
        (run_dir / "probes" / "memory.json").write_text(json.dumps(probe_memory))
    for t in trials:
        d = run_dir / f"{t['task']}-r{t['rep']}"
        d.mkdir()
        (d / "result.json").write_text(json.dumps({**t, "run_id": run_dir.name}))
    return run_dir
