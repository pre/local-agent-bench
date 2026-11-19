"""Command line: llm-eval selfcheck, run, report, compare, probe."""

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import probe
from .compare import compare_runs
from .config import DEFAULT_IMAGE, MANAGED_CONTAINER, Config, ConfigError, ServerConfig, load_config
from .metrics import ServerLogObserver
from .podman import Podman
from .report import load_run, render_report
from .sampler import MemorySampler
from .selfcheck import selfcheck_task
from .server import ServerError, open_server
from .task import Task, TaskError, find_tasks
from .trial import RunContext, execute_run, make_run_id

DEFAULT_OUT = Path.home() / "daybook-evidence" / "local-llm" / "eval"
TIER_REPS = {"quick": 1, "full": 3}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, TaskError) as e:
        print(f"llm-eval: {e}", file=sys.stderr)
        return 2


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="llm-eval")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository directory (default: .)")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("selfcheck", help="check the tasks without an LLM")
    p.add_argument("tasks", nargs="*", help="task IDs (default: all)")
    p.add_argument("--image", default=DEFAULT_IMAGE)
    p.add_argument("--keep", action="store_true", help="keep the scratch directory")
    p.set_defaults(func=cmd_selfcheck)

    p = sub.add_parser("run", help="run trials")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--config", type=Path, action="append", dest="configs",
                        help="configuration file, can repeat: one run for each, one after the other")
    source.add_argument("--resume", type=Path, metavar="RUN_DIR",
                        help="continue a run: run the trials that have no result.json")
    p.add_argument("--tier", choices=TIER_REPS, help="quick: tasks with quick = true, 1 repetition. "
                   "full: all tasks, 3 repetitions (default: all tasks, 1 repetition)")
    p.add_argument("--task", action="append", dest="tasks", help="task ID, can repeat (default: from the tier)")
    p.add_argument("--reps", type=int, help="repetitions (default: from the tier)")
    p.add_argument("--out", type=Path, help=f"run directory, one --config only (default: {DEFAULT_OUT}/<run-id>)")
    p.add_argument("--replace", action="store_true",
                   help=f"remove a {MANAGED_CONTAINER} container that an earlier run of the harness left")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("report", help="write a Markdown report of run directories")
    p.add_argument("runs", nargs="+", type=Path, help="run directories")
    p.add_argument("--out", type=Path, help="Markdown file (default: stdout)")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("compare", help="compare two runs task by task")
    p.add_argument("run_a", type=Path)
    p.add_argument("run_b", type=Path)
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("probe", help="send speed and protocol probes to the server of a configuration")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--out", type=Path, help=f"directory, the files go to <out>/probes/"
                                            f" (default: {DEFAULT_OUT}/probe-<UTC time>-<config>)")
    p.add_argument("--kind", choices=["speed", "protocol", "all"], default="all")
    p.add_argument("--target", type=int, action="append", dest="targets",
                   help="prompt tokens of a speed request, can repeat (default: 1000, 23000, 60000, 120000)")
    p.add_argument("--max-context", type=int, help="do not send speed requests above this count of prompt tokens")
    p.add_argument("--decode-tokens", type=int, default=probe.DECODE_TOKENS)
    p.add_argument("--timeout", type=float, default=1800.0, help="seconds for each request (default: 1800)")
    p.set_defaults(func=cmd_probe)
    return parser.parse_args(argv)


def selfcheck_all(podman, image: str, tasks: list[Task], scratch: Path) -> bool:
    ok = True
    for task in tasks:
        result = selfcheck_task(podman, image, task, scratch / task.id)
        print(f"{task.id}: ok" if result.ok else f"{task.id}: FAIL")
        for problem in result.problems:
            print(f"  {problem}")
        ok = ok and result.ok
    return ok


def cmd_selfcheck(args: argparse.Namespace) -> int:
    tasks = find_tasks(args.root / "tasks", args.tasks)
    scratch = Path(tempfile.mkdtemp(prefix="llm-eval-selfcheck-"))
    try:
        ok = selfcheck_all(Podman(), args.image, tasks, scratch)
    finally:
        if args.keep:
            print(f"scratch: {scratch}")
        else:
            shutil.rmtree(scratch)
    return 0 if ok else 1


@dataclass(frozen=True)
class RunPlan:
    config: Config
    tasks: list[Task]
    reps: int
    out_dir: Path | None = None  # None: DEFAULT_OUT/<run-id>
    run_id: str | None = None  # None: made at the start of the run
    resume: bool = False


def plan_runs(args: argparse.Namespace) -> list[RunPlan]:
    if args.resume:
        return [resume_plan(args)]
    if args.out and len(args.configs) > 1:
        raise ConfigError("--out works only with one --config")
    if args.out and (args.out / "run.json").exists():
        raise ConfigError(f"{args.out} has a run already. Use --resume {args.out} to continue it")
    tasks = find_tasks(args.root / "tasks", args.tasks)
    if args.tier == "quick" and not args.tasks:
        tasks = [t for t in tasks if t.quick]
    reps = args.reps or TIER_REPS.get(args.tier, 1)
    return [RunPlan(load_config(path), tasks, reps, args.out) for path in args.configs]


def resume_plan(args: argparse.Namespace) -> RunPlan:
    if args.tier or args.tasks or args.reps or args.out:
        raise ConfigError("--resume takes the configuration, tasks and repetitions from run.json")
    run_file = args.resume / "run.json"
    if not run_file.is_file():
        raise ConfigError(f"{run_file} is missing")
    info = json.loads(run_file.read_text())
    config = load_config(Path(info["config"]["path"]))
    if config.sha256 != info["config"]["sha256"]:
        raise ConfigError(f"the configuration {config.path} changed after the start of the run")
    tasks = find_tasks(args.root / "tasks", info["tasks"])
    return RunPlan(config, tasks, info["reps"], args.resume, info["run_id"], resume=True)


def make_observers(server: ServerConfig, podman) -> list:
    observers = [MemorySampler()]
    if server.container:
        observers.append(ServerLogObserver(podman, server.container))
    return observers


def selfcheck_plans(podman, plans: list[RunPlan], scratch: Path) -> bool:
    """Check each task once for each agent image."""
    tasks_of_image: dict[str, dict[str, Task]] = {}
    for plan in plans:
        tasks_of_image.setdefault(plan.config.client.image, {}).update({t.id: t for t in plan.tasks})
    ok = True
    for i, (image, tasks) in enumerate(tasks_of_image.items()):
        ok = selfcheck_all(podman, image, list(tasks.values()), scratch / str(i)) and ok
    return ok


def run_plan(plan: RunPlan, podman, scratch: Path, args: argparse.Namespace) -> bool:
    """Start the server, run the trials, stop the server. Return False on a server error."""
    run_id = plan.run_id or make_run_id(plan.config.name)
    out_dir = plan.out_dir or DEFAULT_OUT / run_id
    print(f"run {run_id}: {out_dir}")
    try:
        with open_server(plan.config.server, scratch / run_id, podman=podman, root=args.root, out_dir=out_dir,
                         replace=args.replace) as server:
            server.check_health()
            observers = make_observers(plan.config.server, podman)
            ctx = RunContext(run_id, out_dir, plan.config, args.root, podman, server, observers)
            results = execute_run(ctx, plan.tasks, plan.reps, resume=plan.resume)
    except ServerError as e:
        print(f"llm-eval: {plan.config.name}: {e}", file=sys.stderr)
        return False
    except KeyboardInterrupt:
        print(f"llm-eval: interrupted. To continue: llm-eval run --resume {out_dir}", file=sys.stderr)
        raise
    passed = sum(r["passed"] for r in results)
    print(f"results: {out_dir}  passed {passed}/{len(results)}")
    return True


def cmd_run(args: argparse.Namespace) -> int:
    plans = plan_runs(args)
    podman = Podman()
    scratch = Path(tempfile.mkdtemp(prefix="llm-eval-run-"))
    try:
        if not selfcheck_plans(podman, plans, scratch / "selfcheck"):
            print("llm-eval: a task does not pass the selfcheck, no trials ran", file=sys.stderr)
            return 1
        ok = True
        for plan in plans:
            ok = run_plan(plan, podman, scratch, args) and ok
    except KeyboardInterrupt:
        return 130
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return 0 if ok else 1


def _load_runs(dirs: list[Path]) -> list:
    for d in dirs:
        if not d.is_dir():
            raise ConfigError(f"{d} is not a directory")
    return [load_run(d) for d in dirs]


def cmd_report(args: argparse.Namespace) -> int:
    text = render_report(_load_runs(args.runs))
    if args.out:
        args.out.write_text(text)
        print(f"report: {args.out}")
    else:
        print(text, end="")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    print(compare_runs(*_load_runs([args.run_a, args.run_b])), end="")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    out_dir = args.out or DEFAULT_OUT / f"probe-{make_run_id(config.name)}"
    server = config.server
    kinds = ("speed", "protocol") if args.kind == "all" else (args.kind,)
    paths = probe.probe_server(
        server.url, server.api_key_file.read_text().strip(), server.model, out_dir / "probes", kinds,
        context_tokens=server.context_tokens, max_context=args.max_context,
        targets=args.targets or probe.DEFAULT_TARGETS, decode_tokens=args.decode_tokens, timeout_s=args.timeout,
        config={"name": config.name, "sha256": config.sha256})
    for path in paths.values():
        print(f"probe: {path}")
    return 0
