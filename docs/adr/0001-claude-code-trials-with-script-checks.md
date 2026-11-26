# A trial runs Claude Code against the server, and a script decides the result

Status: accepted.

The harness must show which model and which settings give the best results in real agent work. Thus a trial runs the full application: Claude Code (headless, `claude -p`) with its normal system prompt and tools, connected to the inference server. A hidden check without a model decides if the trial passes.

## Decision

- The agent of a trial is Claude Code itself. The harness does not send its own prompts to a model to measure quality.
- The check of a task is a script with tests (`verify/verify.sh`). No LLM is a judge.
- The Claude Code configuration directory of a trial is `client-config/`: no `CLAUDE.md`, no plugins, no MCP servers. The built-in plugins and the bundled skills of Claude Code stay, because they are part of the product.
- The probes send requests directly to the server API. They measure only the speed and the protocol of a server, not the quality of a model.

## Considered Options

- One-shot tests, where one request without tools gives one answer: they do not measure agent use. They do not show the problems of agent work, for example a chat template that rejects or drops the system message that Claude Code sends after the first user message.

## Consequences

- A trial is slow. The time limit of a hard task is 7200 s. Thus a run has few trials, and `report` and `compare` show a 95 % interval and a noise test.
- A result belongs to one Claude Code version, because a new version can change the system prompt and the tools. The image pins the version and `result.json` records it.
- The verdict does not depend on a second model. But a task must have a result that a script can examine: the harness does not measure a property that only a reader can judge, for example the style of the code.
