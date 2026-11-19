"""The trial procedure: workspace, agent container, diff, check container, result.json.

Stage 2 seam: an observer (for example a memory sampler or a /metrics reader)
has a `name`, `start(trial_dir)` and `stop() -> dict`. The harness starts it
just before the agent container and stops it just after. result.json gets the
dict under the name of the observer ("server" and "memory" are reserved).
"""

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .config import Config
from .podman import ContainerSpec, Mount
from .results import classify, redact_tree, summarize_transcript, write_json
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


def make_run_id(config_name: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now:%Y%m%dT%H%M%SZ}-{config_name}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def agent_env(cfg: Config, base_url: str) -> dict[str, str]:
    """The environment of Claude Code in the agent container, without the API key."""
    model = cfg.server.model
    env = {
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_MODEL": model,
        "CLAUDE_CODE_SUBAGENT_MODEL": model,
        "CLAUDE_CODE_MAX_CONTEXT_TOKENS": str(cfg.server.context_tokens),
    }
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


def run_trial(ctx: RunContext, task: Task, rep: int) -> dict:
    trial_dir = ctx.out_dir / f"{task.id}-r{rep}"
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
        env=agent_env(ctx.config, access.base_url),
        secret_env={"ANTHROPIC_AUTH_TOKEN": ctx.server.api_key()},
        network=access.network,
    )
    for observer in ctx.observers:
        observer.start(trial_dir)
    agent = ctx.podman.run(spec, trial_dir / "transcript.jsonl", trial_dir / "agent.stderr", task.timeout_s)
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
        "tokens": summary.tokens,
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
    write_json(trial_dir / "result.json", result)
    redact_tree(trial_dir, ctx.server.api_key())
    return result


def execute_run(ctx: RunContext, tasks: list[Task], reps: int) -> list[dict]:
    """Run each task `reps` times, one trial after the other. Write run.json."""
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    image = ctx.config.client.image
    ctx.image = ctx.podman.image_info(image)
    version = ctx.podman.output(ContainerSpec(name=container_name("version", "run"), image=image,
                                              command=["claude", "--version"]))
    ctx.claude_code_version = version.split()[0] if version else None
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
    write_json(ctx.out_dir / "run.json", run_info)

    results = []
    for task in tasks:
        for rep in range(1, reps + 1):
            results.append(run_trial(ctx, task, rep))
            run_info.update(trials=len(results), passed=sum(r["passed"] for r in results))
            write_json(ctx.out_dir / "run.json", run_info)
    run_info["finished_at"] = utc_now()
    write_json(ctx.out_dir / "run.json", run_info)
    return results
