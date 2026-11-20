# Tasks

## Task contract

```
tasks/<task-id>/
  task.toml     id, title, category, language, quick, hard (optional), timeout_s, max_turns
  prompt.md     the text that the agent gets
  workspace/    the start files. The harness copies them to /work
  verify/       hidden from the agent
    verify.sh   the check
  solution/     the reference solution: the harness copies its files over the workspace
```

```toml
id = "go-bugfix"          # same as the directory name
title = "Correct the duration parser"
category = "bugfix"       # bugfix, feature, investigate, long-context, constraints, tests, config
language = "go"
quick = true              # true: the task is also in the quick tier
timeout_s = 1800          # wall time limit of the agent
max_turns = 60
```

A hard task (ID `hard-<name>`) has `hard = true`, `quick = false` and `timeout_s = 7200`. The default of `hard` is false. The `hard` tier has only the hard tasks, and the `base` tier has all other tasks. The time limit is high because the local model is about 11 times slower than Sonnet 5.5, which needed up to 517 s for a hard task. A unit test checks that each task with an ID that starts with `hard-` has `hard = true` and no `quick = true`.

Rules for `verify.sh`:

- It runs as `bash /verify/verify.sh` in the check container. The working directory is `/work` (writable). `/verify` is read-only. `/out` is writable. There is no network. `EVAL_BASELINE` is the SHA of the start commit. The limit is 300 s.
- It writes `/out/verify.json`: `{"passed": bool, "score": 0.0 to 1.0, "checks": [{"name": str, "passed": bool}]}`. `passed` is true only if all checks pass. `score` is the fraction of the checks that pass.
- Its exit code is 0 when it wrote the file, also when a check failed. A missing or invalid file, or an exit code that is not 0, is a harness error.
- It works for each user ID and does not need `HOME`. It sets its tool variables (`GOCACHE`, `GOPROXY=off`, `GOFLAGS`, `CARGO_TARGET_DIR`, `CARGO_HOME`) to paths below `/tmp`. It writes only to `/work`, `/out` and `/tmp`.
- It does not trust files that the agent can change. It copies its hidden tests into the workspace and replaces test files with the same name.

Other rules:

- A task works with no network: standard library only, or vendored dependencies.
- `prompt.md` does not tell the agent how the check works.
- If `solution/apply.sh` exists, the harness does not copy it. It runs it with `bash` in a container after the copy, in `/work`, for example to make a commit.

## Add a task

1. Make `tasks/<task-id>/` with the files above. Use `tasks/go-bugfix/` as an example.
2. Make the task difficult enough: the agent must read more than one file, and the prompt must not name the cause.
3. Write `verify/verify.sh`. Make one named check for each behavior, so that `score` shows partial work.
4. Run `just selfcheck <task-id>`. The check must fail on the start files and pass with the solution. `run` does not start trials when a task fails the selfcheck. `uv run llm-eval selfcheck --keep <task-id>` keeps the scratch directory with the logs of `verify.sh`.
