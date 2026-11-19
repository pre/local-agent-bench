We move the contact store from the v1 record files to the v2 SQLite database. The migration will run each night until the v1 store is switched off, so it must be correct for all files of the export jobs, and it must be safe to run again after a failure.

`contactmig/` has a first draft of `python -m contactmig migrate`. It reads only simple UTF-8 files and does not merge, check or log anything. `docs/MIGRATION.md` is the agreed specification: the v1 format, the decoding, the merge rules, the limits, the error codes, the transactions and the behavior of repeated runs.

Please complete the tool so that it follows every rule of `docs/MIGRATION.md`.

- Keep the command line of the spec (rules C1 to C5) and the schema in `contactmig/schema.sql` unchanged.
- Use the Python standard library only.
- Add unit tests for the rules to `tests/`, and keep the present tests.
