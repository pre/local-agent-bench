# Cloud reference models

Two configurations run the same tasks with Claude models through the company LLM gateway. They show the distance between a local model and a cloud model. Each trial costs gateway tokens.

| File | Model ID of the gateway |
|---|---|
| `claude-sonnet-5.5-gateway.toml` | `Claude-Sonnet-5-5` |
| `claude-opus-5.5-gateway.toml` | `Claude-Opus-5-5` (base: the Sonnet file) |

```sh
just run configs/claude-sonnet-5.5-gateway.toml --task go-bugfix
```

The model IDs come from the model list of the gateway (`GET <url>/v1/models`, the list that `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY` uses). The configurations do not use the `[1m]` variant and do not set `context_tokens`. Claude Code 2.1.328 gives these two models a context window of 1000000 tokens also without `[1m]` (`model_usage.contextWindow` in `result.json`). To compare at the context window of a local model, set `context_tokens`.

```toml
[server]
mode = "remote"                         # an HTTPS endpoint. No container, no API key file
url = "https://llm-api.amd.com/Unified" # ANTHROPIC_BASE_URL, must start with https://
model = "Claude-Sonnet-5-5"             # the model ID for all Claude Code model variables
# context_tokens = 200000               # optional: CLAUDE_CODE_MAX_CONTEXT_TOKENS. Default: not set
# ca_file = "/etc/ssl/certs/ca-certificates.crt"  # the default. Read-only in the agent container
# agent_network = "proxy"               # the default, see below

[client.env]                            # values that are not secret
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"

[client.secrets]                        # secret values, read at run time
from_profile = "~/.config/claude-code/profiles/llm-gw.sh"
names = ["ANTHROPIC_API_KEY", "ANTHROPIC_CUSTOM_HEADERS"]
```

The remote mode does not have these steps of a local server: start of a container, GTT check, `/health` check, server observer. Before the run and before each trial, the harness sends a request without credentials to `url`. Each HTTP status (also 401) shows that the endpoint answers.

Model tiers: `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_{FABLE,OPUS,SONNET,HAIKU}_MODEL` and `CLAUDE_CODE_SUBAGENT_MODEL` all get `model`, so the result belongs to one model. The reasoning effort stays at the default of Claude Code.

## Secrets

`[client.secrets]` can be in each configuration. Before the first trial a `bash` process sources `from_profile` with a small environment (`HOME`, `PATH`) and writes only the values of `names` to a pipe. If the profile does not set a name, the run stops. The values:

- go to podman through its process environment (`-e NAME` without a value), not through its arguments.
- are not in `run.json`: the configuration has only the profile path and the names.
- are replaced with `<redacted>` in all files of the trial directory after the trial. For `ANTHROPIC_CUSTOM_HEADERS` the harness also replaces the value of each `Name: value` line (the subscription key). The harness replaces each occurrence, also in the work files. A value shorter than 8 characters is a placeholder and is not replaced, because its replacement changes normal text in files that contain no secret.

A local server gives `ANTHROPIC_AUTH_TOKEN` (its API key). A remote endpoint gives no key of its own, so the local key does not go to the gateway.

The agent can read its environment, for example with `env` in a Bash command. Thus the secret values can be in the transcript before the redaction.

## Network of a remote endpoint

With `agent_network = "proxy"` the agent container has no network (`--network=none`), the same as for a local server (ADR 0002):

1. The harness listens on a Unix socket (`<scratch>/relay/api.sock`). It accepts only `CONNECT <host>:<port>` to the host and port of `url`. It refuses each other request with HTTP 403, and gives HTTP 502 when the endpoint is not reachable.
2. In the container, socat listens on `127.0.0.1:8080` and sends each connection to that socket.
3. Claude Code gets `HTTPS_PROXY=http://127.0.0.1:8080`, `ANTHROPIC_BASE_URL=<url>`, and `NODE_EXTRA_CA_CERTS` and `SSL_CERT_FILE` with the CA bundle of the host at `/run/llm-eval-ca.crt` (read-only). `NO_PROXY` is not set, so each HTTPS connection goes to the proxy.

TLS goes from Claude Code to the gateway through the tunnel. The harness does not see the request. The TLS proxy of the company network (ZScaler) intercepts it on the way, thus the container needs the CA bundle of the host. The container has no DNS. The proxy gets the host name and resolves it on the host.

The agent can reach only the gateway host on its port: no other host, no DNS, no service of the host. Telemetry of Claude Code and other requests of the agent get HTTP 403. The agent can use the secret values with the gateway, for example with curl.

Another value of `agent_network` goes to `podman run --network` (for example `slirp4netns`), and Claude Code connects to `url` directly. This mode is less isolated: the agent can reach the internet.

## Model and cost in the result

`result.json` of each trial also has:

- `total_cost_usd`: the value of the Claude Code `result` event. Claude Code calculates it from its own price list, so it is an estimate. For a local server it has no meaning.
- `model_usage`: the `modelUsage` value of the `result` event (tokens and cost for each model that Claude Code requested).
- `models`: the model IDs of the API responses (`message.model` of the assistant events).

`run.json` has `reported_models`: the `models` of all trials. If the gateway gives a different model than the configuration requests, this list shows it.
