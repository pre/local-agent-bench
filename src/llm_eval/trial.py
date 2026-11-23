"""The trial procedure: workspace, agent container, diff, check container, result.json.

An observer (the memory sampler, the server log reader) has a `name`,
`start(trial_dir)` and `stop() -> dict`. The harness starts it just before the
agent container and stops it just after. result.json gets the dict under the
name of the observer ("server" and "memory").
"""

import json
import shutil
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .config import Config
from .podman import ContainerSpec, Mount
from .profile_secrets import read_profile_secrets
from .results import classify, redact_tree, secret_values, summarize_transcript, write_json
from .server import ExternalServer
from .task import Task
from .workspace import collect_diff, container_name, init_workspace, run_check

RESULT_SCHEMA = 1


class TrialObserver(Protocol):
    name: str

    def start(self, trial_dir: Path) -> None: ...

    def stop(self) -> dict: ...


@dataclass
class RunContext:
    run_id: str
    out_dir: Path
    config: Config
    root: Path  # the repository: client-config/ and tasks/ are below it
    podman: object
    server: ExternalServer
    observers: list[TrialObserver] = field(default_factory=list)
    image: dict | None = None
    claude_code_version: str | None = None
    # The secret environment of Claude Code: the key of a local server, or the
    # values of client.secrets. execute_run sets it.
    secret_env: dict[str, str] = field(default_factory=dict)


def make_run_id(config_name: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now:%Y%m%dT%H%M%SZ}-{config_name}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def agent_env(cfg: Config, base_url: str) -> dict[str, str]:
    """The environment of Claude Code in the agent container, without the secrets.
    All model tiers use the one model, so the result belongs to that model."""
    model = cfg.server.model
    env = {
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_MODEL": model,
        "CLAUDE_CODE_SUBAGENT_MODEL": model,
    }
    if cfg.server.context_tokens:
        env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = str(cfg.server.context_tokens)
    for tier in ("FABLE", "OPUS", "SONNET", "HAIKU"):
        env[f"ANTHROPIC_DEFAULT_{tier}_MODEL"] = model
    return {**env, **cfg.client.env}


def claude_command(task: Task) -> list[str]:
    return [
        "claude", "-p", task.prompt,
        "--output-format", "stream-json", "--verbose",
        "--max-turns", str(task.max_turns),
        "--dangerously-skip-permissions",
    ]


def trial_dir_of(ctx: RunContext, task: Task, rep: int) -> Path:
    return ctx.out_dir / f"{task.id}-r{rep}"


def run_trial(ctx: RunContext, task: Task, rep: int) -> dict:
    trial_dir = trial_dir_of(ctx, task, rep)
    trial_dir.mkdir(parents=True)
    work = trial_dir / "work"
    started = utc_now()
    baseline = init_workspace(task, work)
    shutil.copytree(ctx.root / ctx.config.client.config_dir, trial_dir / "claude-config")

    access = ctx.server.agent_access()
    spec = ContainerSpec(
        name=container_name("agent", task.id),
        image=ctx.config.client.image,
        command=access.command_prefix + claude_command(task),
        mounts=[Mount(work, "/work"), Mount(trial_dir / "claude-config", "/claude-config"), *access.mounts],
        env={**agent_env(ctx.config, access.base_url), **access.env},
        secret_env=ctx.secret_env,
        network=access.network,
    )
    for observer in ctx.observers:
        observer.start(trial_dir)
    try:
        agent = ctx.podman.run(spec, trial_dir / "transcript.jsonl", trial_dir / "agent.stderr", task.timeout_s)
    finally:
        observed = {observer.name: observer.stop() for observer in ctx.observers}

    image = ctx.config.client.image
    collect_diff(ctx.podman, image, work, trial_dir / "agent.diff", baseline, task.id)
    check = run_check(ctx.podman, image, task, work, trial_dir / "check", baseline)
    if check.verify is not None:
        shutil.copy(trial_dir / "check" / "verify.json", trial_dir / "verify.json")

    summary = summarize_transcript(trial_dir / "transcript.jsonl")
    passed, reason, detail = classify(agent, summary, check)
    claude_result = summary.result or {}
    result = {
        "schema": RESULT_SCHEMA,
        "run_id": ctx.run_id,
        "task": task.id,
        "rep": rep,
        "hard": task.hard,
        "config": {"name": ctx.config.name, "path": str(ctx.config.path), "sha256": ctx.config.sha256},
        "passed": passed,
        "score": check.verify["score"] if check.verify else None,
        "failure_reason": reason,
        "failure_detail": detail,
        "wall_time_s": round(agent.seconds, 1),
        "check_time_s": round(check.run.seconds, 1),
        "turns": summary.turns,
        "tool_calls": summary.tool_calls,
        "tool_errors": summary.tool_errors,
        "api_errors": summary.api_errors,
        "permission_denials": summary.permission_denials,
        "tokens": summary.tokens,
        "total_cost_usd": claude_result.get("total_cost_usd"),  # the estimate of Claude Code
        "models": list(summary.models),
        "model_usage": claude_result.get("modelUsage"),
        "agent": {
            "exit_code": agent.exit_code,
            "timed_out": agent.timed_out,
            "result_subtype": claude_result.get("subtype"),
            "terminal_reason": claude_result.get("terminal_reason"),
            "duration_ms": claude_result.get("duration_ms"),
            "duration_api_ms": claude_result.get("duration_api_ms"),
            "ttft_ms": claude_result.get("ttft_ms"),
            "network": access.network,
        },
        "verify": check.verify,
        "server": None,
        "memory": None,
        **observed,
        "claude_code_version": summary.claude_code_version or ctx.claude_code_version,
        "image": ctx.image,
        "baseline": baseline,
        "started_at": started,
        "finished_at": utc_now(),
    }
    finish_trial(ctx, trial_dir, result)
    return result


def error_result(ctx: RunContext, task: Task, rep: int, error: Exception, started: str) -> dict:
    """The result of a trial that the harness could not complete. It has the keys of a normal result."""
    trial_dir = trial_dir_of(ctx, task, rep)
    trial_dir.mkdir(parents=True, exist_ok=True)
    (trial_dir / "harness_error.txt").write_text(traceback.format_exc())
    result = {
        "schema": RESULT_SCHEMA,
        "run_id": ctx.run_id,
        "task": task.id,
        "rep": rep,
        "hard": task.hard,
        "config": {"name": ctx.config.name, "path": str(ctx.config.path), "sha256": ctx.config.sha256},
        "passed": False,
        "score": None,
        "failure_reason": "harness_error",
        "failure_detail": f"{type(error).__name__}: {error}"[:500],
        **dict.fromkeys(["wall_time_s", "check_time_s", "turns", "tool_calls", "tool_errors", "api_errors",
                         "permission_denials", "tokens", "total_cost_usd", "models", "model_usage", "agent", "verify", "server",
                         "memory", "baseline"]),
        "claude_code_version": ctx.claude_code_version,
        "image": ctx.image,
        "started_at": started,
        "finished_at": utc_now(),
    }
    finish_trial(ctx, trial_dir, result)
    return result


def finish_trial(ctx: RunContext, trial_dir: Path, result: dict) -> None:
    """Remove the secrets from the trial files, then write result.json as the last
    file. --resume runs a trial without result.json again, thus a stop before the
    end of this function leaves no complete trial with secret values."""
    secrets = secret_values(ctx.secret_env)
    redact_tree(trial_dir, secrets)
    write_json(trial_dir / "result.json", result, secrets)


def log(ctx: RunContext, line: str) -> None:
    """Write a line to stdout and to run.log of the run directory."""
    print(line, flush=True)
    with (ctx.out_dir / "run.log").open("a") as f:
        f.write(line + "\n")


def start_run(ctx: RunContext, tasks: list[Task], reps: int, resume: bool = False) -> dict:
    """Write run.json before the probes and the trials, and return its values. A resumed
    run keeps its values, gets a resumed_at time and loses the probe gate of an earlier start."""
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    image = ctx.config.client.image
    ctx.image = ctx.podman.image_info(image)
    version = ctx.podman.output(ContainerSpec(name=container_name("version", "run"), image=image,
                                              command=["claude", "--version"]))
    ctx.claude_code_version = version.split()[0] if version else None
    run_file = ctx.out_dir / "run.json"
    if resume:
        run_info = json.loads(run_file.read_text())
        run_info.setdefault("resumed_at", []).append(utc_now())
        run_info.pop("probe_gate", None)
        # A run that the probe gate stopped before this version of the harness has no image.
        run_info.setdefault("image", ctx.image)
        run_info.setdefault("claude_code_version", ctx.claude_code_version)
    else:
        run_info = {
            "run_id": ctx.run_id,
            "config": {"name": ctx.config.name, "path": str(ctx.config.path), "sha256": ctx.config.sha256,
                       "values": ctx.config.raw},
            "image": ctx.image,
            "claude_code_version": ctx.claude_code_version,
            "tasks": [t.id for t in tasks],
            "reps": reps,
            "started_at": utc_now(),
        }
    run_info["server"] = ctx.server.describe()
    write_json(run_file, run_info)
    return run_info


def execute_run(ctx: RunContext, tasks: list[Task], reps: int, run_info: dict) -> list[dict]:
    """Run each task `reps` times, one trial after the other. Update run.json (the
    values of start_run) and write run.log.

    An exception in a trial gives a result with failure_reason "harness_error".
    The trials that have a result.json do not run again.
    """
    ctx.secret_env = {**ctx.server.secret_env(), **read_profile_secrets(ctx.config.client.secrets)}
    run_file = ctx.out_dir / "run.json"
    trials = [(task, rep) for task in tasks for rep in range(1, reps + 1)]
    log(ctx, f"{utc_now()} run {ctx.run_id}: {len(trials)} trials, server {ctx.server.cfg.url}")
    ctx.server.phase = "between trials"
    results = []
    for task, rep in trials:
        trial_dir = trial_dir_of(ctx, task, rep)
        if (trial_dir / "result.json").exists():
            results.append(json.loads((trial_dir / "result.json").read_text()))
            continue
        shutil.rmtree(trial_dir, ignore_errors=True)  # an incomplete trial of an interrupted run
        ctx.server.check_health()
        ctx.server.phase = f"trial {trial_dir.name}"
        started = utc_now()
        try:
            result = run_trial(ctx, task, rep)
        except Exception as e:
            result = error_result(ctx, task, rep, e, started)
        ctx.server.phase = "between trials"
        results.append(result)
        passed = sum(r["passed"] for r in results)
        verdict = "PASS" if result["passed"] else f"FAIL {result['failure_reason']}"
        log(ctx, f"{utc_now()} [{len(results)}/{len(trials)}] {ctx.config.name} {task.id} r{rep} {verdict} "
                 f"wall {result['wall_time_s']} s passed {passed}/{len(results)}")
        models = {model for r in results for model in r.get("models") or []}
        run_info.update(trials=len(results), passed=passed, reported_models=sorted(models))
        write_json(run_file, run_info)
    run_info["finished_at"] = utc_now()
    write_json(run_file, run_info)
    return results
