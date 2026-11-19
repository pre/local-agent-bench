# Migration of the contact store from v1 to v2

Status: agreed. This document is the specification of `python -m contactmig migrate`.
Each rule has an ID (for example `E3`). When an example and a rule do not agree, the rule is correct.

The v1 store is a directory of record files. The v2 store is one SQLite database with the schema in `contactmig/schema.sql`.
The migration runs many times during the move: first on a copy, then each night until the v1 store is switched off.
Thus it must be safe to run again and again, and one bad file must not stop the other files.

## 1. Command

- **C1** `python -m contactmig migrate --source DIR --db FILE [--dry-run]`. `DIR` is the v1 directory. `FILE` is the v2 database.
- **C2** If `FILE` does not exist, the tool creates it and applies `contactmig/schema.sql`. The tool does not change the schema, and the tables have no other columns.
- **C3** Exit status:

  | Status | Meaning |
  |---|---|
  | 0 | No file failed in this run |
  | 1 | At least one file failed in this run (an `error` row was written in this run, see T2 and T3) |
  | 2 | Usage error, or `DIR` is not a directory. The tool does not create or change `FILE` |
  | 75 | The test seam stopped the run (S1) |

- **C4** The last line on stdout is the summary: `migrated=<a> unchanged=<b> failed=<c>`. `a` is the count of files that were migrated in this run, `b` the count of files skipped by T1, `c` the count of files that failed in this run. Other lines can come before it.
- **C5** `--dry-run` does all steps, prints the same output and gives the same exit status as a real run on the same input and database. It writes nothing: when `FILE` does not exist, the tool does not create it, and when `FILE` exists, its bytes stay the same.

## 2. Input files

- **F1** The tool reads the regular files directly in `DIR` whose name ends with `.rec` (lower case) and does not start with `.`. It ignores all other entries, also subdirectories and their content.
- **F2** The tool processes the files one after the other, in the order of Python `sorted()` of the file names (Unicode code point order). Records in a file are processed in file order.
- **F3** The tables store the file name only (for example `b.rec`), not the directory.

## 3. Decoding

The tool decodes each file from bytes to text before it splits the lines.

- **E1** If the file starts with the UTF-8 byte order mark (bytes `EF BB BF`), the tool removes these 3 bytes, and the encoding is UTF-8.
- **E2** The first line is a declaration if it starts with `#v1 encoding=`. The first line is the bytes after the byte order mark (if there is one) up to the first CR or LF byte. The encoding name is the rest of the line without leading and trailing spaces and tabs. The names are `utf-8`, `latin-1` and `cp1252`, in lower case. Another name is the error `unknown-encoding`. A line that starts with `#v1 encoding=` and is not the first line is a comment (L4).
- **E3** With a byte order mark and a declaration of `latin-1` or `cp1252`, the file has the error `encoding-conflict`. A byte order mark with the declaration `utf-8` is correct.
- **E4** With a declaration and no byte order mark, the tool decodes with the declared encoding.
- **E5** With no declaration and no byte order mark, the tool decodes as UTF-8. If the bytes are not valid UTF-8, it decodes the file as cp1252 and writes the warning `encoding-fallback` (record NULL).
- **E6** If the bytes are not valid in the encoding that E1, E4 or E5 selects (strict decoding of Python, also for the cp1252 fallback), the file has the error `undecodable`.

## 4. Lines and records

- **L1** Only CR LF, LF and CR end a line. Other characters (for example U+0085, U+2028 or form feed) are part of the line.
- **L2** A blank line is empty or has only spaces and tabs. A blank line ends the current record. It is never a continuation line.
- **L3** A continuation line starts with a space or a tab and is not blank. It continues the value of the last field line of the current record (see V2). A continuation line when the current record has no field line yet (for example the first line of a record) is the error `syntax`.
- **L4** A comment line starts with `#`. The tool ignores it. A comment line does not end a record. The declaration (E2) is a comment line too.
- **L5** Each other line is a field line: `key: value`. The key is the text before the first `:`, without leading and trailing spaces and tabs. It must match `[A-Za-z][A-Za-z0-9_-]*`. A field line without `:`, or with a key that does not match, is the error `syntax`.
- **L6** A record is a group of field lines (with their continuation lines and comment lines) between blank lines, or between a blank line and the start or end of the file. A file can have zero records.
- **L7** Records are numbered 1, 2, 3, ... in each file. A record starts at its first line that is not blank and not a comment. Thus a continuation line after a blank line starts a new record, and the `syntax` error of L3 belongs to that record.

## 5. Fields

- **V1** Keys compare without case: `Email`, `EMAIL` and `email` are the same key.
- **V2** The value is the text after the first `:` of the field line. For each continuation line, the tool adds one space and the continuation line without its leading spaces and tabs. Then it removes the leading and trailing spaces and tabs of the value.
- **V3** The fields are:

  | Key | Count in a record | Content |
  |---|---|---|
  | `id` | exactly 1 | The v1 ID. It must match `[A-Za-z0-9-]{1,32}`, else the error `bad-id` |
  | `name` | exactly 1 | The display name (N1, N2) |
  | `updated` | exactly 1 | Time of the last change (N4) |
  | `email` | 0 or more | One email address on each line (N3). The first `email` line of a record is its primary email |
  | `tags` | 0 or more | Comma-separated tags (N5) |

- **V4** A key of `id`, `name` or `updated` that occurs more than once in a record is the error `duplicate-field`.
- **V5** A missing `id`, `name` or `updated` field, or a field of these three with an empty value, is the error `missing-field`. A `name` that is empty after N1 is also `missing-field`.
- **V6** The tool ignores fields with other keys.

## 6. Normalization

- **N1** Name: Unicode normalization form NFC, then each run of whitespace becomes one space, and leading and trailing whitespace is removed. Whitespace is as in Python `str.split()` with no argument (thus also U+0085, U+00A0 and U+2028).
- **N2** Name limit: if the name after N1 is longer than 64 bytes in UTF-8, the tool keeps the longest start of the name that is at most 64 bytes and ends at a code point boundary, then removes trailing spaces. It writes the warning `name-truncated` for that record. This is the stored name of that record.
- **N3** Email: split the value at the last `@` into a local part and a domain. If there is no `@`, or the local part or the domain is empty, the error is `bad-email`. The domain becomes lower case (`str.lower()`), then the tool converts it with the Python `idna` codec (`domain.encode("idna").decode("ascii")`). If the codec raises an error, the error is `bad-email`. The local part does not change. The normalized address is `local + "@" + domain`.
- **N4** Updated: the value must have one of the forms `YYYY-MM-DDTHH:MM:SSZ` or `YYYY-MM-DDTHH:MM:SS+HH:MM` or `YYYY-MM-DDTHH:MM:SS-HH:MM`, with ASCII digits and a valid date and time. Else the error is `bad-timestamp`. The tool stores the time in UTC in the form `YYYY-MM-DDTHH:MM:SSZ`. Times compare as points in time.
- **N5** Tags: split the value at each `,`. Each item without leading and trailing whitespace, in lower case (`str.lower()`), is a tag. Empty items are ignored.
- **N6** The key of an email address is its normalized address in lower case (`str.lower()`). Two addresses with the same key are the same address. The match key of a record is the key of its primary email. A record without an email has no match key.

## 7. Accounts and merge

- **M1** For each record in processing order (F2): if the record has a match key and an account with the same `match_key` exists, the record merges into that account (M3 to M6). Else the tool creates a new account with the record values. The `match_key` of a new account is the match key of the record, or NULL. A record without a match key never merges, and no record merges into an account with a NULL `match_key`. Accounts match only by the primary email: an address that is not the primary email of the record, and an address of an account that is not its `match_key`, have no effect on the match.
- **M2** Account IDs are 1, 2, 3, ... in the order in which the accounts are created, also over many runs. A file that fails (T3) uses no IDs, and the next account gets the next free ID.
- **M3** Name and time: if the time of the record is the same as or later than the `updated` of the account, the account gets the name (after N2) and the time of the record. Else the account keeps its name and time. Thus, at the same time, the record that comes later in processing order wins.
- **M4** Emails: the account keeps its addresses in their order (`position` 0, 1, 2, ...). Then the tool adds each address of the record that the account does not have yet (by key, N6), in record order, at the next position. An address of the account keeps its spelling, also when the record has the same address with a different case. In one record, an address with the same key as an earlier address of that record is ignored with no warning.
- **M5** Tags: the account gets the union of its tags and the tags of the record.
- **M6** v1 IDs: the table `legacy_ids` maps each v1 ID to its account. If the v1 ID of the record is already in `legacy_ids` for another account (also for an account of an earlier file or an earlier run), the error is `duplicate-id`. If it is there for the same account, nothing changes.
- **M7** A new account from a record is the same as a merge into an empty account: M4 to M6 apply in the same way.

## 8. Limits

- **X1** An account has at most 5 email addresses. When M4 adds an address and the account has 5 addresses, the tool does not add it and writes the warning `email-dropped` with the normalized address of the record as `detail`. It writes one warning for each dropped address (but not for an address that M4 ignores).
- **X2** The display name limit is N2.

## 9. Issues

The table `issues` has the warnings and errors.

- **I1** Columns: `file` (F3), `record` (the record number of L7, or NULL), `level` (`warning` or `error`), `code`, `detail` (the dropped address for `email-dropped`, else NULL).
- **I2** Warning codes: `encoding-fallback` (record NULL), `name-truncated`, `email-dropped`.
- **I3** Error codes and the `record` value:

  | Code | Record |
  |---|---|
  | `unknown-encoding`, `encoding-conflict`, `undecodable` | NULL |
  | `changed-after-migration` | NULL |
  | `syntax`, `duplicate-field`, `missing-field`, `bad-id`, `bad-timestamp`, `bad-email`, `duplicate-id` | the number of the record that has the fault |

- **I4** A file has at most one `error` row. If a file has more than one fault, the tool reports one of them.

## 10. Transactions and repeated runs

- **T1** If `migrated_files` has a row with the name of the file and the same SHA-256 (lower case hexadecimal, of the file bytes), the file is unchanged. The tool skips it and does not change the database for it.
- **T2** If `migrated_files` has a row with the name of the file and a different SHA-256, the file failed: the tool removes the `error` rows of this file name, adds the error `changed-after-migration` and does not change other rows. The warnings of the earlier migration stay.
- **T3** Else the tool migrates the file in one transaction: it removes all `issues` rows of this file name (for example an error of an earlier run), applies all records, writes the warnings, and adds the row `(name, sha256, records)` to `migrated_files`, where `records` is the count of records in the file. If the file has an error, nothing of this file stays in the database (no accounts, no changes to accounts, no warnings, no row in `migrated_files`). The tool then removes the `issues` rows of this file name and writes the one `error` row.
- **T4** The tool commits the result of each file before it starts the next file.
- **T5** A second run with the same `DIR` and the same database does not change the content of any table.
- **T6** A run over files that an earlier run migrated gives the same tables as one run over all files, when the new files come after the old files in the order of F2.

## 11. Test seam

- **S1** If the environment variable `CONTACTMIG_FAIL_AFTER_FILES` is a positive integer `n`, the tool stops with exit status 75 just after it commits the result of the `n`-th file of T2 or T3 in this run. It does not process more files and does not print the summary. A file of T1 does not count. A later run without the variable completes the migration, and the tables are then the same as after one run without a stop.

## 12. Examples

File `a.rec` (UTF-8):

```
# exported 2026-10-01
id: c-100
name: Ada   Lovelace
email: Ada@Example.COM
email: ada.l@example.org
tags: Math, history,
updated: 2026-03-01T10:00:00+02:00

id: c-101
Name: Ada L.
email: ada@example.com
updated: 2026-03-01T08:00:00Z
```

Result: one account `1`, `match_key` `ada@example.com`. The two times are the same point in time, so record 2 wins by M3: `display_name` is `Ada L.` and `updated` is `2026-03-01T08:00:00Z`. Emails: position 0 `Ada@example.com`, position 1 `ada.l@example.org` (the address of record 2 has the same key as position 0, so it adds nothing). Tags `history` and `math`. `legacy_ids`: `c-100` and `c-101` map to account 1. `migrated_files`: `('a.rec', <sha256>, 2)`.
