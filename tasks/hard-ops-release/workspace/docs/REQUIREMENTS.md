# relctl requirements

`relctl` installs release packages on one host. This document is the specification of `bin/relctl`. Each rule has a number (R1 to R26). All rules apply together.

Words:

- **base dir**: the directory that holds all installed releases (R10).
- **package**: a gzip-compressed tar file of one release, with a checksum file (R11, R12).
- **version**: the content of the file `VERSION` in the package (R12).
- **current version**: the version that the symlink `current` points to, or none when `current` does not exist.

## Command line and output

**R1. Usage.** `relctl [OPTIONS] COMMAND [ARGUMENTS]`

| Option | Meaning |
|---|---|
| `--config FILE` | the configuration file (R4) |
| `--base DIR` | the base dir (R8) |
| `--keep N` | the number of releases to keep (R8, R23) |
| `--lock-wait N` | the lock wait time in seconds (R8, R20) |
| `--dry-run` | change nothing (R24) |

| Command | Arguments |
|---|---|
| `install PACKAGE` | exactly one: the path of the package file |
| `rollback` | none |
| `prune` | none |
| `status` | none |

Options come before COMMAND. Each word after COMMAND is an argument, also when it begins with `-`. Thus `relctl install -nightly.tar.gz` installs the file `-nightly.tar.gz`. A relative PACKAGE path is relative to the working directory of the caller. An option that needs a value and has none, an unknown option, a missing or unknown command, and a wrong number of arguments are usage errors.

**R2. Exit codes.**

| Code | Meaning |
|---|---|
| 0 | success, also when there was nothing to do |
| 1 | another error (for example a failed file operation) |
| 2 | usage error (R1) |
| 3 | configuration error (R4 to R9) |
| 4 | the package is not valid (R11, R12) |
| 5 | version conflict (R14) |
| 6 | the health check failed, and relctl rolled back (R18) |
| 7 | there is no previous release (R22) |
| 75 | the lock is busy (R20) |
| 130 | stopped by SIGINT (R21) |
| 143 | stopped by SIGTERM (R21) |

relctl finds usage errors before configuration errors, and it reads and checks the configuration before it does other work. A usage error or a configuration error changes nothing.

**R3. Output.** Only `status` writes to stdout (R25). The other commands write nothing to stdout. Each line on stderr has the format `relctl: LEVEL: MESSAGE`, where LEVEL is `info`, `warn` or `error` and MESSAGE is not empty. When the exit code is not 0, relctl writes at least one `error` line. Output of programs that relctl starts (for example `tar` warnings) must not go to stderr in another format. The output of the health check goes to a file (R17).

## Configuration

**R4. Configuration file.** relctl uses the first of these:

1. the file of `--config FILE`
2. the file in the environment variable `RELCTL_CONFIG`, when it is set and not empty
3. `/etc/relctl/relctl.conf`

When the file of 1 or 2 does not exist or cannot be read, that is a configuration error. When the default file (3) does not exist, relctl continues with no configuration file.

**R5. Syntax.** The file has one setting on each line, in the form `key=value`.

- relctl removes spaces and tabs at the start and at the end of each line.
- After that, an empty line and a line that starts with `#` are ignored.
- The key is the text before the first `=`. The value is all text after the first `=`, with its inner spaces. There are no quotes and no escapes: `"` and `\` are normal characters.
- There are no spaces around `=`. Thus `keep = 5` has the key `keep ` (with a space), and that is an unknown key.
- A line with no `=`, an unknown key, a bad value, and a key that occurs two times are configuration errors. Only `shared` can occur more than one time.

**R6. Keys.**

| Key | Value | Default |
|---|---|---|
| `base_dir` | an absolute path (it starts with `/`) | none: the base dir must come from somewhere (R8) |
| `keep` | a number from 2 to 50 | 5 |
| `lock_wait` | a number from 0 to 600 | 10 |
| `health_cmd` | the absolute path of an executable file. An empty value means no health check | no health check |
| `health_timeout` | a number from 1 to 3600 | 30 |
| `shared` | a relative path: one or more names separated by `/`. A name must not be empty, `.` or `..`. The path does not start or end with `/` | none |

**R7. Numbers.** A number has one to four digits `0` to `9` and nothing else (no sign, no spaces). Leading zeros are permitted and do not make an octal number: `010` is ten, and `08` is eight.

**R8. Precedence.** For the base dir, `keep` and `lock_wait`, relctl uses the first value that is given:

| Setting | 1. option | 2. environment (set and not empty) | 3. configuration file | 4. default |
|---|---|---|---|---|
| base dir | `--base` | `RELCTL_BASE` | `base_dir` | none: configuration error |
| keep | `--keep` | `RELCTL_KEEP` | `keep` | 5 |
| lock wait | `--lock-wait` | `RELCTL_LOCK_WAIT` | `lock_wait` | 10 |

The rules of R6 and R7 apply to a value from an option and from the environment too. A bad value that relctl uses is a configuration error. relctl does not use and does not check an environment value when an option overrides it. relctl always checks all lines of the configuration file.

**R9. No code execution.** relctl never runs the configuration file or a value in it as shell code (no `source`, no `eval`). A value such as `$(touch /tmp/x)` is text: it can only be a bad value or a literal path.

## Base dir

**R10. Layout.** The base dir contains:

| Path | Content |
|---|---|
| `releases/<version>/` | one directory for each installed release |
| `current` | a symlink. Its target is the relative path `releases/<version>` |
| `shared/` | data that all releases share (R15) |
| `.staging/` | temporary directories of `install`. When relctl stops, `.staging/` is empty or does not exist |
| `.relctl.lock` | the lock file (R20) |
| `history.tsv` | the history (R19) |
| `health.log` | the output of the health check (R17) |

relctl makes the base dir and these directories when they do not exist (but not with `--dry-run`, R24). relctl sets the umask to `027` at its start. Thus the directories that it makes have the mode `750`, and `history.tsv` and `health.log` have the mode `640`.

## Install

**R11. Checksum.** The checksum file is the package path with `.sha256` added, for example `app-1.4.0.tar.gz.sha256`. Its first word is the SHA-256 of the package in 64 hexadecimal digits, upper case or lower case. Other text after the first word is ignored. When the package or the checksum file does not exist, when the first word is not 64 hexadecimal digits, or when the SHA-256 of the package is different, the package is not valid.

**R12. Content.** The package is not valid when:

- `tar` cannot read it as a gzip-compressed tar file,
- a member name starts with `/`, or a member name has the component `..`,
- it has no regular file `VERSION` at the top level (member name `VERSION` or `./VERSION`),
- the content of `VERSION` is not one version followed by at most one newline. A version agrees with the extended regular expression `^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$`.

When the package is not valid, relctl exits with code 4 before it changes the base dir: no new release, no change of `current`, no history line, and nothing remains in `.staging/`.

**R13. Unpack.** relctl unpacks the package into a new directory below `.staging/`, then moves that directory to `releases/<version>` with one rename. The files of the package are at the top level of the release, so `VERSION` is `releases/<version>/VERSION`.

**R14. Same version.** relctl must remember the SHA-256 of each installed release (where is your choice, but `status` must not show it as a release).

- When `releases/<version>` exists with the same SHA-256 and it is the current version, `install` does nothing and exits with 0. It writes no history line.
- When `releases/<version>` exists with the same SHA-256 and it is not the current version, `install` does not unpack the package again. It activates the existing release with the steps of R16 to R19.
- When `releases/<version>` exists with a different SHA-256, `install` exits with code 5 and changes nothing.

**R15. Shared paths.** For each `shared` value P, in the release that relctl installs:

- relctl makes the directory `<base dir>/shared/P` when it does not exist.
- When the release contains P (a file or a directory), relctl removes it from the release.
- relctl makes the parent directories of P in the release when necessary.
- relctl makes `P` in the release a symlink with the absolute target `<base dir>/shared/P`.

relctl does not change the content of `shared/`.

**R16. Activation.** relctl points `current` to `releases/<version>` with an atomic rename of a new symlink (for example `ln -s` to a temporary name, then `mv -T`). When `current` existed before, it exists at all times.

**R17. Health check.** When `health_cmd` is set, relctl runs it after the activation (R16), so `current` already points to the new release. The health check runs:

- with its working directory in the release directory,
- with the environment variables `RELCTL_VERSION` (the version) and `RELCTL_RELEASE_DIR` (the absolute path `<base dir>/releases/<version>`),
- with stdin from `/dev/null`, and stdout and stderr appended to `<base dir>/health.log`,
- with a time limit of `health_timeout` seconds. When the time limit ends, relctl stops the health check process, and the health check failed.

The health check passes when it exits with 0.

**R18. Failed health check.** When the health check fails, relctl:

1. points `current` back to the target that it had before the install, or removes `current` when it did not exist before,
2. removes `releases/<version>` when this install made it (R13). A release that existed before (R14) stays,
3. appends a history line with the action `failed` (R19),
4. exits with code 6. It does not prune (R23).

**R19. History.** relctl appends one line to `history.tsv` for each `install` that ends with code 0 and changed `current`, for each failed health check, and for each `rollback`. It never changes or removes lines. A line has four fields, separated by one tab:

| Field | Value |
|---|---|
| time | UTC, format `YYYY-MM-DDTHH:MM:SSZ` |
| action | `install`, `failed` or `rollback` |
| version | the version |
| sha256 | the SHA-256 of the package in lower case (`install` and `failed`), `-` for `rollback` |

After a successful `install`, relctl prunes (R23).

## Lock and signals

**R20. Lock.** `install`, `rollback` and `prune` take an exclusive lock with flock(2) on the file `<base dir>/.relctl.lock` (the same lock that the `flock` command takes). They wait for the lock at most the lock wait time (R8). A lock wait of 0 means one attempt with no wait. When relctl cannot get the lock, it exits with code 75 and changes nothing. `status` and `--dry-run` do not take the lock. Programs that relctl starts must not keep the lock after relctl stops.

**R21. Signals.** When relctl gets SIGINT or SIGTERM during `install`, also while the health check runs:

- it stops the health check process when that process runs,
- it undoes the install: `current` points to its target from before the install (or does not exist when it did not exist before), the release that this install made is removed, and nothing remains in `.staging/`,
- it writes no history line for this install,
- it exits with code 130 (SIGINT) or 143 (SIGTERM) at most 5 seconds after the signal.

## Other commands

**R22. Rollback.** The previous release is found from `history.tsv`: read the lines from the last line to the first line, and take the version of the first line with the action `install` or `rollback` whose version is not the current version and whose directory `releases/<version>` exists. `rollback` points `current` to the previous release (R16) and appends a history line with the action `rollback`. It does not run the health check. When there is no previous release, it exits with code 7.

**R23. Prune.** Prune keeps a set of releases and removes the directories of all other releases from `releases/`. The kept set is: the current release, the previous release (R22), and then the newest other releases in the order of `sort -V`, until the set has `keep` releases. The command `prune` does this, and `install` does it after each successful install.

**R24. Dry run.** With `--dry-run`, `install`, `rollback` and `prune` do all checks (R1 to R9, R11, R12, R14, R22) and exit with the same code as without `--dry-run` for these checks, but they change nothing: they do not make the base dir or a file or a directory in it, they do not run the health check, and they do not take the lock. They tell on stderr (R3) what they would do.

**R25. Status.** `status` writes exactly three lines to stdout and changes nothing:

```
current=<the current version>
previous=<the previous release (R22)>
releases=<all installed versions in the order of sort -V, separated by one space>
```

When a value is empty, it is `-`. Example:

```
current=1.10.0
previous=1.9.0
releases=1.2.0 1.9.0 1.10.0
```

## Code

**R26. Code.** `bin/relctl` is one executable bash script. `shellcheck bin/relctl` with the default settings reports nothing. It must work when the base dir path, the configuration file path, the package path and the shared paths contain spaces and glob characters (`*`, `?`, `[`).
