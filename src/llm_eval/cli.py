"""Command line: llm-eval selfcheck, llm-eval run."""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from .config import ConfigError, DEFAULT_IMAGE, load_config
from .podman import Podman
from .selfcheck import selfcheck_task
from .server import ServerError, open_server
from .task import Task, TaskError, find_tasks
from .trial import RunContext, execute_run, make_run_id

DEFAULT_OUT = Path.home() / "daybook-evidence" / "local-llm" / "eval"


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
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--task", action="append", dest="tasks", help="task ID, can repeat (default: all)")
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--out", type=Path, help=f"run directory (default: {DEFAULT_OUT}/<run-id>)")
    p.set_defaults(func=cmd_run)
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


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    tasks = find_tasks(args.root / "tasks", args.tasks)
    podman = Podman()
    run_id = make_run_id(config.name)
    out_dir = args.out or DEFAULT_OUT / run_id
    scratch = Path(tempfile.mkdtemp(prefix="llm-eval-run-"))
    try:
        if not selfcheck_all(podman, config.client.image, tasks, scratch / "selfcheck"):
            print("llm-eval: a task does not pass the selfcheck, no trials ran", file=sys.stderr)
            return 1
        with open_server(config.server, scratch) as server:
            server.check_health()
            ctx = RunContext(run_id, out_dir, config, args.root, podman, server)
            print(f"run {run_id}: {out_dir}")
            results = execute_run(ctx, tasks, args.reps)
    except ServerError as e:
        print(f"llm-eval: {e}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    for r in results:
        verdict = "PASS" if r["passed"] else f"FAIL {r['failure_reason']}"
        print(f"{r['task']} r{r['rep']} {verdict}  wall {r['wall_time_s']} s  turns {r['turns']}  score {r['score']}")
    print(f"results: {out_dir}")
    return 0
