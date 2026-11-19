"""Command line of the jobq client: python -m jobq_client."""

import argparse
import os
import sys

from .client import Client
from .durations import format_duration, parse_duration
from .errors import JobqError

DEFAULT_URL = "http://127.0.0.1:7070"


def format_job(job):
    """One line for a job: ID, state, timeout and command, separated by tabs."""
    return "\t".join([job.id, job.state, format_duration(job.timeout), " ".join(job.command)])


def build_parser():
    parser = argparse.ArgumentParser(prog="jobq", description="Client of the jobq service.")
    parser.add_argument("--url", default=os.environ.get("JOBQ_URL") or DEFAULT_URL,
                        help="root URL of the service (default: $JOBQ_URL or %(default)s)")
    parser.add_argument("--token-file", default=os.environ.get("JOBQ_TOKEN_FILE"),
                        help="file with the API token (default: $JOBQ_TOKEN_FILE)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("submit", help="create a job and print its ID")
    p.add_argument("--timeout", required=True, help="Go duration, for example 1m30s")
    p.add_argument("command", nargs=argparse.REMAINDER)

    p = sub.add_parser("get", help="print one job")
    p.add_argument("job_id")

    p = sub.add_parser("list", help="print all jobs, the oldest first")
    p.add_argument("--page-size", type=int)

    p = sub.add_parser("cancel", help="cancel a queued job and print it")
    p.add_argument("job_id")
    return parser


def read_token(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError as e:
        print(f"error: token file: {e}", file=sys.stderr)
        return None


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.token_file:
        print("error: give --token-file or set JOBQ_TOKEN_FILE", file=sys.stderr)
        return 2
    token = read_token(args.token_file)
    if not token:
        if token == "":
            print("error: the token file is empty", file=sys.stderr)
        return 2
    client = Client(args.url, token)
    try:
        if args.cmd == "submit":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            if not command:
                print("error: give the command after --", file=sys.stderr)
                return 2
            try:
                timeout = parse_duration(args.timeout)
            except ValueError as e:
                print(f"error: invalid_argument: {e}", file=sys.stderr)
                return 1
            print(client.create_job(command, timeout).id)
        elif args.cmd == "get":
            print(format_job(client.get_job(args.job_id)))
        elif args.cmd == "list":
            for job in client.list_jobs(page_size=args.page_size):
                print(format_job(job))
        elif args.cmd == "cancel":
            print(format_job(client.cancel_job(args.job_id)))
    except JobqError as e:
        print(f"error: {e.code}: {e.message}", file=sys.stderr)
        return 1
    return 0
