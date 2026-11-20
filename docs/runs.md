# Runs and trials

## Tiers, repetitions and long runs

| Option | Tasks | Repetitions |
|---|---|---|
| `--tier quick` | Tasks with `quick = true` | 1 |
| `--tier base` | Tasks without `hard = true` | 1 |
| `--tier hard` | Tasks with `hard = true` | 1 |
| `--tier full` | All tasks | 3 |
| No `--tier` | All tasks | 1 |

`--task` (can repeat) and `--reps` replace the values of the tier.

- `--config` can repeat. The configurations run one after the other, each with its own run directory and its own server: the harness stops server A before it starts server B. A server error stops only the run of that configuration, and the exit code is then 1. `--out` is permitted with one `--config` only.
- The selfcheck runs once for each agent image before the first configuration.
- An exception in a trial gives a `result.json` with `failure_reason = "harness_error"`, the error in `failure_detail` and the traceback in `harness_error.txt`. The run continues with the next trial.
- After each trial a progress line goes to stdout and to `run.log` in the run directory, for example `2026-11-19T18:20:01+00:00 [3/15] qwen38-base go-bugfix r3 FAIL verify_failed wall 878.2 s passed 1/3`.
- `run --resume <run-dir>` (or `just resume <run-dir>`) continues a run that stopped. It reads the configuration, the tasks and the repetitions from `run.json`, and stops if the configuration file changed. It does not run trials that have a `result.json` again, and it removes the directory of a trial without `result.json` before it runs that trial again. Also a `harness_error` trial has a `result.json`. To run it again, remove its directory first.
- After Ctrl-C the harness stops the server and shows the `--resume` command.

## Trial procedure

1. Copy `workspace/` to `<trial>/work` and make a git repository with one commit "chore: Start the task" (identity `eval <eval@localhost>`, fixed date, so the SHA is the same in each trial).
2. Copy `client-config/` to `<trial>/claude-config`.
3. Run the agent container: `claude -p <prompt.md> --output-format stream-json --verbose --max-turns <max_turns> --dangerously-skip-permissions`. Stop it at `timeout_s`.
4. Write the diff of the work against the start commit (new files included) in a container.
5. Run the check container: `bash /verify/verify.sh`, limit 300 s.
6. Write `result.json`. Then replace the API key and the secret values of `[client.secrets]` with `<redacted>` in all files of the trial.

Containers:

| Container | Mounts | Network | Environment |
|---|---|---|---|
| Agent | `<trial>/work:/work`, `<trial>/claude-config:/claude-config`, relay directory at `/run/llm-eval` (proxy mode), CA bundle at `/run/llm-eval-ca.crt:ro` (remote mode) | `none` (proxy mode) | `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` (local server: from the key file), the values of `[client.secrets]` (secret values are not in the podman arguments), `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_{FABLE,OPUS,SONNET,HAIKU}_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_MAX_CONTEXT_TOKENS` (when `context_tokens` is set), `HTTPS_PROXY`, `NODE_EXTRA_CA_CERTS` and `SSL_CERT_FILE` (remote mode), `[client.env]` |
| Diff | `<trial>/work:/work` | `none` | `EVAL_BASELINE` |
| Check | `<trial>/work:/work`, `tasks/<id>/verify:/verify:ro`, `<trial>/check:/out` | `none` | `EVAL_BASELINE` |

All containers use `--userns=keep-id:uid=1000,gid=1000` and `--init`. The user in the container is `eval` (UID 1000, `HOME=/home/eval`), and on the host the files belong to the user who runs the harness. Claude Code thus does not run as root.

### Result files

The default run directory is `~/daybook-evidence/local-llm/eval/<run-id>/`, where `<run-id>` is `<UTC time>-<configuration name>`.

```
<run-id>/
  run.json                 configuration values, server values, image, Claude Code version, tasks
  run.log                  one progress line for each trial
  server.log               the full log of a managed server
  probes/                  only with run --probe (see probes.md)
    protocol.json          the protocol probe
    speed.json             the speed probe
    memory.csv             the memory sampler during the probes
    memory.json            the memory summary of the probes, the keys of "memory" in result.json
  probes-<n>/              the probes of an earlier start (run --resume --probe), the same files
  <task-id>-r<rep>/
    result.json            the result of the trial
    transcript.jsonl       the stream-json output of Claude Code
    agent.stderr           stderr of the agent container
    agent.diff             the agent work against the start commit
    verify.json            the output of the check
    check/                 verify.json, check.stdout, check.stderr, logs of verify.sh
    work/                  the workspace after the check
    claude-config/         the configuration directory after the trial (session files)
    memory.csv             the memory sampler (see observers.md)
    server.log             the server log of the trial (see observers.md)
    harness_error.txt      only for a harness error: the traceback
```

`result.json` has: `hard` (the `hard` value of the task), `passed`, `score`, `failure_reason`, `failure_detail`, `wall_time_s` (agent container), `turns`, `tool_calls`, `tool_errors`, `api_errors`, `permission_denials` (the count of `permission_denied` events: Claude Code refused a command, for example a dangerous `rm`, also with `--dangerously-skip-permissions`), `tokens`, `total_cost_usd`, `model_usage` and `models` (see [Cloud reference models](cloud-models.md)), `agent` (exit code, result subtype, durations), `verify`, `server` and `memory` (see [Observers](observers.md)), `claude_code_version`, `image` (ID and digest), `config` (name, path, SHA-256) and `baseline` (start commit).

A trial passes only if Claude Code stops normally and the check passes. The failure reasons, in the order the harness examines them:

| Reason | Meaning |
|---|---|
| `timeout` | The agent container ran longer than `timeout_s` |
| `harness_error` | The check did not give a valid `verify.json`, Claude Code gave no result event, or the harness had an error. Not a model failure |
| `max_turns` | Claude Code stopped at `--max-turns` |
| `context_overflow` | An API error that says that the prompt is too long for the context |
| `api_error` | Another API error |
| `verify_failed` | The check failed |
