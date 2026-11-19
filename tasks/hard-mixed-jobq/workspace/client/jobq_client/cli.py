"""Command line of the jobq client: python -m jobq_client."""

import argparse
import os
import sys

from .client import Client
from .errors import JobqError

DEFAULT_URL = "http://127.0.0.1:8080"


def format_job(job):
    """One line for a job: ID, state, timeout and command, separated by tabs."""
    return "\t".join([str(job.id), job.state, f"{job.timeout_seconds}s", " ".join(job.command)])


def build_parser():
    parser = argparse.ArgumentParser(prog="jobq", description="Client of the jobq service.")
    parser.add_argument("--url", default=os.environ.get("JOBQ_URL", DEFAULT_URL),
                        help="root URL of the service (default: $JOBQ_URL or %(default)s)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("submit", help="create a job and print its ID")
    p.add_argument("--timeout-seconds", type=int, required=True)
    p.add_argument("command", nargs=argparse.REMAINDER)

    p = sub.add_parser("get", help="print one job")
    p.add_argument("job_id")

    sub.add_parser("list", help="print all jobs, the oldest first")

    p = sub.add_parser("cancel", help="cancel a queued job and print it")
    p.add_argument("job_id")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    client = Client(args.url)
    try:
        if args.cmd == "submit":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            if not command:
                print("error: give the command after --", file=sys.stderr)
                return 2
            print(client.create_job(command, args.timeout_seconds).id)
        elif args.cmd == "get":
            print(format_job(client.get_job(args.job_id)))
        elif args.cmd == "list":
            for job in client.list_jobs():
                print(format_job(job))
        elif args.cmd == "cancel":
            print(format_job(client.cancel_job(args.job_id)))
    except JobqError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0
