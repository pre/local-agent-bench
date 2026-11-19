"""Command line of contactmig."""

import argparse

from .migrate import run_migration


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contactmig", description="Migrate the contact store from v1 to v2.")
    sub = parser.add_subparsers(dest="command", required=True)
    migrate = sub.add_parser("migrate", help="migrate the v1 record files into the v2 database")
    migrate.add_argument("--source", required=True, help="directory of the v1 record files")
    migrate.add_argument("--db", required=True, help="the v2 SQLite database")
    migrate.add_argument("--dry-run", action="store_true", help="do all steps but write nothing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_migration(args.source, args.db, dry_run=args.dry_run)
