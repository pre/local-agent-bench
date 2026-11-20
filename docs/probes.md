# Probes

```sh
just probe configs/qwen38-external.toml                       # all probes, all speed targets
just probe configs/qwen38-external.toml --kind protocol
just probe configs/qwen38-external.toml --kind speed --target 1000 --target 23000
```

## Probes in a run

`run --probe speed|protocol|all` sends the probes to the server of each run after the server is healthy and before the first trial. The files go to `<run-dir>/probes/`, so `report <run-dir>` shows them. The speed probe of a run uses the targets 1000 and 23000 tokens. `--probe-target N` (can repeat) gives other targets.

The memory sampler runs during the probes and writes `probes/memory.csv` and `probes/memory.json`. A long prompt fills the context, thus a probe can use more GTT than the trials. The GTT peak of the report includes the probes.

With `protocol` or `all`, the protocol probe runs first, and it is a gate. These cases fail the gate:

- `plain`, `tool_call` or `tool_round_trip` fails.
- `system_in_middle` gives an HTTP status that is not 200. Claude Code sends a system message after the first user message, so a template that rejects it (the HTTP 500 of the original Qwen3.8 template) fails each trial with `api_error`. A template that drops the message gives HTTP 200: the case fails, but it does not fail the gate, because that is a matter of quality.

A case that fails the gate runs one more time, because one sample at temperature 1.0 can fail by chance. Its record in `protocol.json` is the second attempt, with the first attempt in `first_attempt`. The `probe` command does the same.

When a case fails the gate two times, the harness does not run the speed probe and the trials of that configuration. It prints the failed cases, writes the reason to `run.json` (key `probe_gate`: `failed_cases`, `reason`, `at`) and to `run.log`, stops the server and continues with the next configuration. The exit code is then 1. The report shows the reason in "Runs". The other cases do not stop a run. `run.json` already has the image and the Claude Code version, because the harness writes `run.json` before the probes.

The reason tells if trials ran: "no trials ran", or on a resumed run "no more trials ran (N of M trials have a result of an earlier start)". `--resume` removes the `probe_gate` key of an earlier start, and a new gate stop writes it again. `--resume --probe` keeps the probe files of the earlier start: it moves `probes/` to `probes-1/` (the next free number), and the new files go to `probes/`.

A probe error (for example HTTP 500 from `/tokenize`) stops only that configuration, the same as a server error. `--probe` with a remote configuration (`mode = "remote"`) stops before a server starts, with a message: the probes need a local llama-server.

## Probe command

`probe` sends requests from the host directly to the server URL of the configuration, with the key of `api_key_file`. It does not use Claude Code or a container. The results go to `<out>/probes/speed.json` and `<out>/probes/protocol.json`. The default `<out>` is `~/daybook-evidence/local-llm/eval/probe-<UTC time>-<configuration>/`. `report <out>` shows the probe results.

The probes are polite to a shared server. They send one request at a time. Before each request they read `/slots` and wait (at most 300 s) until no slot processes a request. Each request has a timeout (`--timeout`, default 1800 s). The timeout is for each read of the socket, and the server sends no data while it processes the prompt.

Other code can call `llm_eval.probe.probe_server(base_url, api_key, model, out_dir, ...)`, for example for a managed server.

## Speed probe

For each target (default 1000, 23000, 60000 and 120000 tokens) the probe sends one streaming `/v1/chat/completions` request. The prompt has about the target count of tokens and asks for a long answer. The probe stops the answer at `--decode-tokens` (default 256) and switches off thinking with `chat_template_kwargs: {"enable_thinking": false}`.

- The prompt is real prose and code: the Python language reference (`pydoc_data.topics`) and 20 modules of the Python standard library, in alternate pieces of about 6000 characters. The probe uses `/tokenize` and `/detokenize` of llama-server to cut the text to the target size.
- A random nonce is at the start of the prompt. Thus the server cannot use its prompt cache, and it processes the full prompt again. `cache_tokens` shows the count of tokens that came from the cache.
- The speed values come from the `timings` object in the last chunk of the stream (llama.cpp). `/v1/messages` does not give timings. Time to first token is measured by the client: from the request to the first chunk with text.
- A target is skipped when it is above `context_tokens` of the configuration minus the decode tokens and a margin of 1024 tokens, or above `--max-context`. After a failed request the probe sends no more requests.
- On this machine (Qwen3.8 Flash-Next UD-Q4_K_XL with MTP, 2026-11-19) the 120000 token request took 785 s: 767 s for the prompt at 157 tokens per second. The full speed probe took about 20 minutes.

`speed.json`:

```json
{
  "schema": 1, "kind": "speed", "base_url": "...", "model": "...",
  "config": {"name": "...", "sha256": "..."},
  "server": {"build_info": "...", "model_path": "...", "total_slots": 1, "n_ctx": 131072},
  "started_at": "...", "finished_at": "...",
  "decode_tokens": 256, "corpus": "Python 3.15: pydoc topics and 20 standard library modules",
  "results": [{
    "target_tokens": 23000, "prompt_tokens": 23013, "cache_tokens": 0,
    "prompt_seconds": 73.7, "prompt_tps": 312.3,
    "decode_tokens": 256, "decode_seconds": 10.1, "decode_tps": 25.3,
    "ttft_s": 73.8, "total_s": 83.9,
    "draft_generated": 283, "draft_accepted": 160, "draft_acceptance": 0.565,
    "reasoning_chars": 0, "finish_reason": "length", "error": null, "waited_s": 0.0
  }],
  "skipped": [{"target_tokens": 120000, "reason": "above --max-context 30000"}]
}
```

A failed request gives `{"target_tokens": N, "error": "HTTP 503: ..."}`.

## Protocol probe

The protocol probe sends a fixed list of small requests to `/v1/messages`, the endpoint that Claude Code uses. Each case records the HTTP status, the error text and the result of one assertion on the response.

| Case | Request | Assertion |
|---|---|---|
| `plain` | One user message | The text has the requested word |
| `two_system_blocks` | Two system blocks at the start | The text has the codes of the two blocks. A hyphen character such as U+2011 (non-breaking hyphen) counts as "-" |
| `system_in_middle` | A system message in the middle of the conversation | The answer is only the code of the system message (`LIME-93`, also `Code C is LIME-93.`, Markdown emphasis and quotes are permitted). A refusal that names the code fails, and its note starts with "the answer is not only the code". The original chat template of Qwen3.8 gave HTTP 500 "System message must be at the beginning". The gate stops the trials only on an HTTP error of this case |
| `tool_call` | A question that needs a tool | A `tool_use` block, the input agrees with the schema |
| `tool_round_trip` | Assistant `tool_use`, user `tool_result` | The final text uses the tool result |
| `parallel_tools` | A question that needs two tools | Two `tool_use` blocks in one turn, each input agrees with its schema |
| `nested_arguments` | A tool with nested objects and arrays | The input agrees with the schema |
| `tool_result_error` | A `tool_result` with `is_error: true` | HTTP 200 with a text or a `tool_use` block |
| `stream_tool_call` | `stream: true` with a tool | The event sequence is well formed (`message_start` first, `message_stop` last, one open block at a time, block indexes in sequence, a `message_delta` with a stop reason) and the tool input JSON agrees with the schema |
| `thinking_budget` | `thinking: {"type": "enabled", "budget_tokens": 1024}` | The reasoning is in a `thinking` block, the text has the answer and no `<think>` tags |
| `thinking_disabled` | `thinking: {"type": "disabled"}` | No `thinking` block |
| `max_tokens` | `max_tokens: 16` and a long answer | `stop_reason` is `max_tokens` |
| `client_sampling` | `temperature`, `top_p` and `top_k` from the client | `/slots` shows the client values. Another client can change `/slots` between the two requests |
| `count_tokens` | `/v1/messages/count_tokens` | `input_tokens` is a positive integer |

To add a case, add one `Case` entry to `CASES` in `src/llm_eval/probe.py`: a name, a description, the request body and a check function.

`protocol.json` has the same header as `speed.json` (`schema`, `kind`, `base_url`, `model`, `config`, `server`, `started_at`, `finished_at`) and:

```json
{
  "cases": [{
    "name": "stream_tool_call", "description": "...", "path": "/v1/messages",
    "http_status": 200, "passed": false,
    "note": "1 tool calls: get_weather; block 1 starts before block 0 stops; ...",
    "error": null, "stop_reason": "tool_use", "seconds": 4.1,
    "response": "message_start, content_block_start(thinking), content_block_delta x20, ..."
  }],
  "passed": 12, "total": 14
}
```

`response` is the first 1500 characters of the response body, or a short list of the event types of a stream. `error` is the network error, or the HTTP status and the start of the body when the status is not 200.
