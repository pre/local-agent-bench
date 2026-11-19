"""Command line of stockd. See README.md for the commands."""

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .clock import default_clock
from .config import load_config
from .errors import StockdError
from .maintenance import check_log, compact
from .recovery import recover
from .report import render_json, render_table
from .service import InventoryService
from .store import EventStore

log = logging.getLogger("stockd")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stockd", description="Event-sourced stock service")
    p.add_argument("--version", action="version", version=f"stockd {__version__}")
    p.add_argument("--data", type=Path, default=Path("data"), help="data directory (default: ./data)")
    p.add_argument("--segment-bytes", type=int, dest="segment_max_bytes",
                   help="segment size limit (default: from stockd.toml, else 65536)")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("apply", help="apply the commands of a JSON lines file, print one result line each")
    a.add_argument("file", help="the commands, '-' for stdin")

    r = sub.add_parser("report", help="print the stock")
    r.add_argument("--json", action="store_true")
    r.add_argument("--warehouse")

    sub.add_parser("snapshot", help="write a snapshot of the current state")
    sub.add_parser("compact", help="remove the segments that the newest snapshot contains")
    sub.add_parser("check-log", help="read all segments and report gaps and damaged lines")

    rp = sub.add_parser("replay", help="build the state from the events only, ignore the snapshots")
    rp.add_argument("--json", action="store_true")
    return p


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("stockd")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False


def cmd_apply(svc: InventoryService, file: str) -> int:
    stream = sys.stdin if file == "-" else open(file, encoding="utf-8")
    counts: dict[str, int] = {}
    try:
        for number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                result = {"request_id": None, "status": "rejected", "error": f"line {number}: not valid JSON"}
            else:
                result = svc.execute(obj)
            counts[result["status"]] = counts.get(result["status"], 0) + 1
            print(json.dumps(result, sort_keys=True), flush=True)
    finally:
        if stream is not sys.stdin:
            stream.close()
    log.info("apply: %s", ", ".join(f"{n} {s}" for s, n in sorted(counts.items())) or "no commands")
    return 0


def cmd_replay(config, as_json: bool) -> int:
    with EventStore(config.segments_dir, config.segment_max_bytes, default_clock()) as store:
        inventory, _, stats = recover(store, None, config.request_window)
    print(render_json(inventory) if as_json else render_table(inventory))
    return 0


def cmd_check_log(config) -> int:
    with EventStore(config.segments_dir, config.segment_max_bytes, default_clock()) as store:
        result = check_log(store)
    print(f"segments {result.segments}, events {result.events}, seq {result.first_seq}..{result.last_seq}, "
          f"version 1 events {result.v1_events}")
    for type_, count in sorted(result.by_type.items()):
        print(f"  {type_} {count}")
    for problem in result.problems:
        print(f"PROBLEM {problem}")
    return 1 if result.problems else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_level)
    try:
        config = load_config(args.data, {"segment_max_bytes": args.segment_max_bytes})
        if args.cmd == "replay":
            return cmd_replay(config, args.json)
        if args.cmd == "check-log":
            return cmd_check_log(config)
        with InventoryService(config) as svc:
            if args.cmd == "apply":
                return cmd_apply(svc, args.file)
            if args.cmd == "report":
                print(render_json(svc.inventory, args.warehouse) if args.json
                      else render_table(svc.inventory, args.warehouse))
                return 0
            if args.cmd == "snapshot":
                print(f"snapshot at seq {svc.snapshot()}")
                return 0
            if args.cmd == "compact":
                removed = compact(svc.store, svc.snapshots)
                print(f"removed {len(removed)} segment(s)")
                return 0
    except StockdError as e:
        log.error("%s", e)
        return 2
    except OSError as e:
        log.error("%s", e)
        return 2
    return 0
