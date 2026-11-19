"""Probes: direct requests from the host to the server API, without Claude Code
and without a container.

- speed: one request for each target context size. It reads the "timings" of
  the last chunk of a streaming /v1/chat/completions response (llama.cpp).
- protocol: a fixed list of small /v1/messages requests (the endpoint of
  Claude Code). Each case records the HTTP status and one assertion.

Both probes are polite to a shared server: one request at a time, a timeout for
each request, and a wait until the slots of the server are idle.
"""

import itertools
import json
import sysconfig
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
DEFAULT_TARGETS = (1000, 23000, 60000, 120000)
RUN_TARGETS = (1000, 23000)  # run --probe: a 120000 token request takes about 13 minutes
# run --probe: when one of these cases fails, the trials of the configuration do not run.
GATE_CASES = ("plain", "tool_call", "tool_round_trip")
DECODE_TOKENS = 256
CONTEXT_MARGIN = 1024
CASE_MAX_TOKENS = 4096
EXCERPT_CHARS = 1500

CODE_FILES = (
    "argparse.py", "json/decoder.py", "http/server.py", "textwrap.py", "dataclasses.py", "inspect.py",
    "subprocess.py", "pathlib/__init__.py", "tarfile.py", "zipfile/__init__.py", "email/message.py",
    "logging/__init__.py", "asyncio/tasks.py", "typing.py", "configparser.py", "difflib.py", "shutil.py",
    "tokenize.py", "ast.py", "statistics.py",
)
INSTRUCTION = (
    "\n\nAbove is a part of the Python documentation and of the Python standard library. Write a long and"
    " detailed technical review of this material. Explain the main concepts, name the functions and classes,"
    " and give examples. Write at least 1000 words."
)


class ProbeError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Reply:
    status: int | None  # None: no HTTP response (network error or timeout)
    body: dict | list | None = None
    text: str = ""
    events: list[dict] = field(default_factory=list)  # server-sent events of a streaming response
    times: list[float] = field(default_factory=list)  # seconds from the request to each event
    seconds: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == 200 and self.error is None

    def error_text(self) -> str:
        return self.error or f"HTTP {self.status}: {self.text[:300]}"


class Client:
    """HTTP requests to the server, one at a time. The key goes only into the
    Authorization header."""

    def __init__(self, base_url: str, api_key: str, timeout_s: float = 1800.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    def request(self, method: str, path: str, body: dict | None = None) -> Reply:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base_url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        start = time.monotonic()
        reply = Reply(status=None)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                reply.status = response.status
                if response.headers.get("Content-Type", "").startswith("text/event-stream"):
                    self._read_events(response, start, reply)
                else:
                    reply.text = response.read().decode(errors="replace")
        except urllib.error.HTTPError as e:
            reply.status, reply.text = e.code, e.read().decode(errors="replace")
        except (OSError, ValueError) as e:  # ValueError: an event that is not JSON
            reply.error = f"{type(e).__name__}: {e}"
        reply.seconds = time.monotonic() - start
        try:
            reply.body = json.loads(reply.text) if reply.text else None
        except json.JSONDecodeError:
            pass
        return reply

    @staticmethod
    def _read_events(response, start: float, reply: Reply) -> None:
        for raw in response:
            line = raw.decode(errors="replace").strip()
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                reply.events.append(json.loads(line[5:]))
                reply.times.append(time.monotonic() - start)

    def wait_idle(self, max_wait_s: float = 300.0, poll_s: float = 2.0) -> float:
        """Wait until no slot of the server processes a request. Return the seconds
        waited. A server without /slots counts as idle."""
        start = time.monotonic()
        while time.monotonic() - start < max_wait_s:
            reply = self.request("GET", "/slots")
            if not reply.ok or not any(slot.get("is_processing") for slot in reply.body):
                break
            time.sleep(poll_s)
        return round(time.monotonic() - start, 2)

    def tokenize(self, text: str) -> list[int]:
        reply = self.request("POST", "/tokenize", {"content": text, "add_special": False})
        if not reply.ok:
            raise ProbeError(f"/tokenize: {reply.error_text()}")
        return reply.body["tokens"]

    def detokenize(self, tokens: list[int]) -> str:
        reply = self.request("POST", "/detokenize", {"tokens": tokens})
        if not reply.ok:
            raise ProbeError(f"/detokenize: {reply.error_text()}")
        return reply.body["content"]

    def server_info(self) -> dict | None:
        reply = self.request("GET", "/props")
        if not reply.ok:
            return None
        props = reply.body
        return {"build_info": props.get("build_info"), "model_path": props.get("model_path"),
                "total_slots": props.get("total_slots"),
                "n_ctx": props.get("default_generation_settings", {}).get("n_ctx")}


# Speed probe

def _chunks(text: str, size: int = 6000) -> list[str]:
    """Pieces of about `size` characters that end at a line end."""
    chunks, start = [], 0
    while start < len(text):
        end = text.find("\n", start + size)
        end = len(text) if end < 0 else end + 1
        chunks.append(text[start:end])
        start = end
    return chunks


def corpus_text() -> str:
    """Realistic prose and code: the Python language reference (pydoc topics) and
    modules of the Python standard library, in alternate pieces."""
    from pydoc_data.topics import topics

    stdlib = Path(sysconfig.get_paths()["stdlib"])
    prose = "\n\n".join(f"## {name}\n\n{topics[name]}" for name in sorted(topics))
    code = "\n\n".join(f"# File: {name}\n\n{(stdlib / name).read_text()}" for name in CODE_FILES)
    pairs = itertools.zip_longest(_chunks(prose), _chunks(code), fillvalue="")
    return "\n\n".join(piece for pair in pairs for piece in pair)


def build_prompt(client: Client, target_tokens: int, corpus_tokens: list[int]) -> str:
    """A prompt of about `target_tokens` tokens. A random nonce at the start makes
    sure that the server cannot use its prompt cache of an earlier request."""
    nonce = f"Probe {uuid.uuid4().hex}.\n\n"
    needed = target_tokens - len(client.tokenize(nonce + INSTRUCTION))
    if needed > len(corpus_tokens):
        raise ProbeError(f"the corpus has {len(corpus_tokens)} tokens, {needed} are necessary")
    return nonce + client.detokenize(corpus_tokens[:needed]) + INSTRUCTION


def _has_text(event: dict) -> bool:
    delta = (event.get("choices") or [{}])[0].get("delta") or {}
    return bool(delta.get("content") or delta.get("reasoning_content"))


def _rate(tokens: int, seconds: float) -> float | None:
    return round(tokens / seconds, 2) if seconds else None


def measure(client: Client, model: str, prompt: str, decode_tokens: int) -> dict:
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": decode_tokens,
            "stream": True, "chat_template_kwargs": {"enable_thinking": False}}
    reply = client.request("POST", "/v1/chat/completions", body)
    if not reply.ok:
        return {"error": reply.error_text()}
    t = next((e["timings"] for e in reversed(reply.events) if "timings" in e), {})
    first = next((s for s, e in zip(reply.times, reply.events) if _has_text(e)), None)
    last_choice = next((e["choices"][0] for e in reversed(reply.events) if e.get("choices")), {})
    prompt_s, decode_s = t.get("prompt_ms", 0) / 1000, t.get("predicted_ms", 0) / 1000
    draft_n, accepted = t.get("draft_n"), t.get("draft_n_accepted")
    reasoning = "".join(((e.get("choices") or [{}])[0].get("delta") or {}).get("reasoning_content") or ""
                        for e in reply.events)
    return {
        "prompt_tokens": t.get("prompt_n"), "cache_tokens": t.get("cache_n"),
        "prompt_seconds": round(prompt_s, 3), "prompt_tps": _rate(t.get("prompt_n", 0), prompt_s),
        "decode_tokens": t.get("predicted_n"), "decode_seconds": round(decode_s, 3),
        "decode_tps": _rate(t.get("predicted_n", 0), decode_s),
        "ttft_s": round(first, 3) if first is not None else None, "total_s": round(reply.seconds, 3),
        "draft_generated": draft_n, "draft_accepted": accepted,
        "draft_acceptance": round(accepted / draft_n, 3) if draft_n else None,
        "reasoning_chars": len(reasoning), "finish_reason": last_choice.get("finish_reason"), "error": None,
    }


def speed_probe(client: Client, model: str, targets=DEFAULT_TARGETS, decode_tokens: int = DECODE_TOKENS,
                context_tokens: int | None = None, max_context: int | None = None,
                log: Callable[[str], None] = lambda line: None) -> dict:
    run, skipped = [], []
    for target in sorted(targets):
        if context_tokens is not None and target > context_tokens - decode_tokens - CONTEXT_MARGIN:
            skipped.append({"target_tokens": target, "reason": f"above the context of the configuration"
                            f" ({context_tokens} tokens) minus {decode_tokens} decode tokens and a margin"
                            f" of {CONTEXT_MARGIN}"})
        elif max_context is not None and target > max_context:
            skipped.append({"target_tokens": target, "reason": f"above --max-context {max_context}"})
        else:
            run.append(target)
    corpus = corpus_text()
    corpus_tokens = client.tokenize(corpus[: max(run, default=0) * 6]) if run else []
    results = []
    for target in run:
        if results and results[-1]["error"]:
            skipped.append({"target_tokens": target, "reason": "an earlier request failed"})
            continue
        prompt = build_prompt(client, target, corpus_tokens)
        waited = client.wait_idle()
        log(f"speed {target} tokens: sent (waited {waited} s for an idle slot)")
        result = {"target_tokens": target, **measure(client, model, prompt, decode_tokens)}
        if not result["error"]:
            result["waited_s"] = waited
        results.append(result)
        log(f"speed {target} tokens: " + (result["error"] or f"prompt {result['prompt_tps']} tok/s,"
                                          f" decode {result['decode_tps']} tok/s, ttft {result['ttft_s']} s"))
    return {"decode_tokens": decode_tokens, "corpus": f"Python {sysconfig.get_python_version()}: pydoc topics"
            f" and {len(CODE_FILES)} standard library modules", "results": results, "skipped": skipped}


# Protocol probe

def schema_errors(value, schema: dict, path: str = "input") -> list[str]:
    """The differences between a value and a small subset of JSON Schema: type,
    required, properties, items, enum."""
    types = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool}
    kind = schema.get("type")
    if kind in types and (not isinstance(value, types[kind]) or (kind in ("integer", "number")
                                                                 and isinstance(value, bool))):
        return [f"{path}: not {kind}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: {value!r} not in {schema['enum']}"]
    errors = []
    if kind == "object":
        errors += [f"{path}: {key} is missing" for key in schema.get("required", []) if key not in value]
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errors += schema_errors(value[key], sub, f"{path}.{key}")
    if kind == "array" and "items" in schema:
        for i, item in enumerate(value):
            errors += schema_errors(item, schema["items"], f"{path}[{i}]")
    return errors


def stream_problems(events: list[dict]) -> list[str]:
    """The problems of an Anthropic Messages event sequence."""
    kinds = [e.get("type") for e in events if e.get("type") != "ping"]
    problems = []
    if not kinds or kinds[0] != "message_start":
        problems.append("the first event is not message_start")
    if not kinds or kinds[-1] != "message_stop":
        problems.append("the last event is not message_stop")
    open_index, next_index = None, 0
    for e in events:
        kind, index = e.get("type"), e.get("index")
        if kind == "content_block_start":
            if open_index is not None:
                problems.append(f"block {index} starts before block {open_index} stops")
            if index != next_index:
                problems.append(f"block index {index}, expected {next_index}")
            open_index, next_index = index, next_index + 1
        elif kind == "content_block_delta" and index != open_index:
            problems.append(f"delta for block {index}, but the open block is {open_index}")
        elif kind == "content_block_stop":
            if index != open_index:
                problems.append(f"stop for block {index}, but the open block is {open_index}")
            open_index = None
    if open_index is not None:
        problems.append(f"block {open_index} is not stopped")
    if not any(e.get("type") == "message_delta" and (e.get("delta") or {}).get("stop_reason") for e in events):
        problems.append("no message_delta with a stop_reason")
    return problems


def _stream_tool_calls(events: list[dict]) -> list[dict]:
    """The tool_use blocks of a stream, with the input from the input_json_delta parts."""
    calls: dict[int, dict] = {}
    for e in events:
        block = e.get("content_block") or {}
        if e.get("type") == "content_block_start" and block.get("type") == "tool_use":
            calls[e["index"]] = {"name": block.get("name"), "parts": []}
        delta = e.get("delta") or {}
        if delta.get("type") == "input_json_delta" and e.get("index") in calls:
            calls[e["index"]]["parts"].append(delta.get("partial_json", ""))
    return [{"name": c["name"], "input": json.loads("".join(c["parts"]) or "{}")} for c in calls.values()]


def _blocks(reply: Reply, kind: str) -> list[dict]:
    return [b for b in (reply.body or {}).get("content", []) if b.get("type") == kind]


def _text(reply: Reply) -> str:
    return "".join(b.get("text", "") for b in _blocks(reply, "text"))


def _tool_check(calls: list[dict], tools: list[dict], needed: list[str]) -> tuple[bool, str]:
    schemas = {t["name"]: t["input_schema"] for t in tools}
    problems = []
    for call in calls:
        if call["name"] not in schemas:
            problems.append(f"unknown tool {call['name']}")
        else:
            problems += schema_errors(call["input"], schemas[call["name"]])
    missing = [name for name in needed if name not in {c["name"] for c in calls}]
    problems += [f"no call of {name}" for name in missing]
    note = f"{len(calls)} tool calls: {', '.join(c['name'] for c in calls)}"
    return bool(calls) and not problems, "; ".join([note] + problems)


def tool_calls(tools: list[dict], needed: list[str]):
    return lambda reply, client: _tool_check(_blocks(reply, "tool_use"), tools, needed)


def contains(*words: str):
    def check(reply: Reply, client: "Client") -> tuple[bool, str]:
        text = _text(reply)
        return all(w.lower() in text.lower() for w in words), f"text: {text[:200]!r}"
    return check


def contains_any(*words: str):
    def check(reply: Reply, client: "Client") -> tuple[bool, str]:
        text = _text(reply)
        return any(w.lower() in text.lower() for w in words), f"text: {text[:200]!r}"
    return check


def answers(reply: Reply, client: Client) -> tuple[bool, str]:
    kinds = [b.get("type") for b in (reply.body or {}).get("content", [])]
    return "text" in kinds or "tool_use" in kinds, f"blocks: {', '.join(kinds)}; text: {_text(reply)[:200]!r}"


def stream_tool_call(tools: list[dict]):
    def check(reply: Reply, client: Client) -> tuple[bool, str]:
        problems = stream_problems(reply.events)
        ok, note = _tool_check(_stream_tool_calls(reply.events), tools, [tools[0]["name"]])
        return ok and not problems, "; ".join([note] + problems)
    return check


def thinking_lands_in_block(reply: Reply, client: Client) -> tuple[bool, str]:
    thinking = "".join(b.get("thinking", "") for b in _blocks(reply, "thinking"))
    text = _text(reply)
    tags = "<think>" in text or "</think>" in text
    note = (f"thinking block {len(thinking)} chars, text {text[:80]!r}, think tags in text: {tags},"
            f" output_tokens {(reply.body.get('usage') or {}).get('output_tokens')}")
    return bool(thinking) and "391" in text and not tags, note


def no_thinking(reply: Reply, client: Client) -> tuple[bool, str]:
    thinking = "".join(b.get("thinking", "") for b in _blocks(reply, "thinking"))
    return not thinking, f"thinking block {len(thinking)} chars, text {_text(reply)[:80]!r}"


def stops_at_max_tokens(reply: Reply, client: Client) -> tuple[bool, str]:
    return reply.body.get("stop_reason") == "max_tokens", f"stop_reason {reply.body.get('stop_reason')}"


SAMPLING = {"temperature": 0.2, "top_p": 0.5, "top_k": 7}


def sampling_in_slots(reply: Reply, client: Client) -> tuple[bool, str]:
    slots = client.request("GET", "/slots")
    if not slots.ok:
        return False, f"/slots: {slots.error_text()}"
    params = slots.body[0].get("params", {})
    seen = {key: round(params[key], 3) if isinstance(params.get(key), float) else params.get(key) for key in SAMPLING}
    return seen == SAMPLING, "/slots: " + ", ".join(f"{k} {v}" for k, v in seen.items())


def counts_tokens(reply: Reply, client: Client) -> tuple[bool, str]:
    tokens = reply.body.get("input_tokens")
    return isinstance(tokens, int) and tokens > 0, f"input_tokens {tokens}"


WEATHER = {"name": "get_weather", "description": "Get the current weather in a city.", "input_schema": {
    "type": "object", "required": ["city", "unit"], "properties": {
        "city": {"type": "string"}, "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}}}}
TIME = {"name": "get_time", "description": "Get the current local time in a city.", "input_schema": {
    "type": "object", "required": ["city"], "properties": {"city": {"type": "string"}}}}
DEPLOY = {"name": "create_deployment", "description": "Create a Kubernetes deployment.", "input_schema": {
    "type": "object", "required": ["name", "replicas", "containers"], "properties": {
        "name": {"type": "string"},
        "replicas": {"type": "integer"},
        "containers": {"type": "array", "items": {
            "type": "object", "required": ["name", "image", "ports", "resources"], "properties": {
                "name": {"type": "string"}, "image": {"type": "string"},
                "ports": {"type": "array", "items": {"type": "integer"}},
                "resources": {"type": "object", "required": ["cpu", "memory"], "properties": {
                    "cpu": {"type": "string"}, "memory": {"type": "string"}}}}}}}}}

WEATHER_QUESTION = "What is the weather in Helsinki now? Use celsius."
TOOL_USE = {"role": "assistant", "content": [
    {"type": "tool_use", "id": "toolu_probe_1", "name": "get_weather", "input": {"city": "Helsinki", "unit": "celsius"}}]}


def _user(text: str) -> dict:
    return {"role": "user", "content": text}


def _tool_result(content: str, is_error: bool = False) -> dict:
    return {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_probe_1", "content": content, "is_error": is_error}]}


@dataclass(frozen=True)
class Case:
    name: str
    description: str
    body: dict  # the request without "model"; max_tokens has a default
    check: Callable[[Reply, Client], tuple[bool, str]]
    path: str = "/v1/messages"


CASES = (
    Case("plain", "One user message", {"messages": [_user("Reply with the word PONG and nothing else.")]},
         contains("PONG")),
    Case("two_system_blocks", "Two system blocks at the start", {
        "system": [{"type": "text", "text": "Code A is KIWI-17."}, {"type": "text", "text": "Code B is ZEBRA-42."}],
        "messages": [_user("Tell me code A and code B.")]}, contains("KIWI-17", "ZEBRA-42")),
    Case("system_in_middle", "A system message in the middle of the conversation", {"messages": [
        _user("Hello."), {"role": "assistant", "content": "Hello. How can I help?"},
        {"role": "system", "content": "Code C is LIME-93."}, _user("What is code C? Answer with the code only.")]},
        contains("LIME-93")),
    Case("tool_call", "The model must call a tool, the input must match the schema",
         {"tools": [WEATHER], "messages": [_user(WEATHER_QUESTION)]}, tool_calls([WEATHER], ["get_weather"])),
    Case("tool_round_trip", "Assistant tool_use, user tool_result, final answer", {"tools": [WEATHER], "messages": [
        _user(WEATHER_QUESTION), TOOL_USE, _tool_result("Helsinki: -3 C, light snow.")]}, contains_any("-3", "snow")),
    Case("parallel_tools", "Two tools called in one turn", {"tools": [WEATHER, TIME], "messages": [_user(
        "I need the weather in Helsinki in celsius and the local time in Tokyo. Call both tools now, in this"
        " one turn.")]}, tool_calls([WEATHER, TIME], ["get_weather", "get_time"])),
    Case("nested_arguments", "A tool with nested object and array arguments", {"tools": [DEPLOY], "messages": [_user(
        "Create a deployment named web with 3 replicas and two containers: nginx (image nginx:1.27, ports 80"
        " and 443, cpu 500m, memory 256Mi) and log-shipper (image fluent-bit:3.1, port 2020, cpu 100m, memory"
        " 64Mi). Use the tool.")]}, tool_calls([DEPLOY], ["create_deployment"])),
    Case("tool_result_error", "A tool result with is_error true", {"tools": [WEATHER], "messages": [
        _user(WEATHER_QUESTION), TOOL_USE,
        _tool_result("Error: the weather service is not available (HTTP 503).", is_error=True)]}, answers),
    Case("stream_tool_call", "stream true with a tool call, the event sequence must be well formed", {
        "stream": True, "tools": [WEATHER], "messages": [_user(WEATHER_QUESTION)]}, stream_tool_call([WEATHER])),
    Case("thinking_budget", "thinking enabled with a budget, the reasoning must be in a thinking block", {
        "thinking": {"type": "enabled", "budget_tokens": 1024},
        "messages": [_user("What is 17 times 23? Answer with the number only.")]}, thinking_lands_in_block),
    Case("thinking_disabled", "thinking disabled, the response must not have a thinking block", {
        "thinking": {"type": "disabled"}, "messages": [_user("Reply with the word PONG and nothing else.")]},
        no_thinking),
    Case("max_tokens", "max_tokens is reached, stop_reason must be max_tokens", {
        "max_tokens": 16, "messages": [_user("Write an essay of 500 words about rivers.")]}, stops_at_max_tokens),
    Case("client_sampling", "temperature, top_p and top_k from the client must override the server defaults", {
        **SAMPLING, "max_tokens": 64, "messages": [_user("Say hello.")]}, sampling_in_slots),
    Case("count_tokens", "/v1/messages/count_tokens gives the input token count",
         {"messages": [_user("Reply with the word PONG.")]}, counts_tokens, path="/v1/messages/count_tokens"),
)


def _excerpt(reply: Reply) -> str:
    if not reply.events:
        return reply.text[:EXCERPT_CHARS]
    names = []
    for e in reply.events:
        block = (e.get("content_block") or {}).get("type")
        names.append(f"{e.get('type')}({block})" if block else str(e.get("type")))
    groups = [(name, len(list(run))) for name, run in itertools.groupby(names)]
    return ", ".join(name if count == 1 else f"{name} x{count}" for name, count in groups)[:EXCERPT_CHARS]


def run_case(client: Client, model: str, case: Case) -> dict:
    body = {"model": model, "max_tokens": CASE_MAX_TOKENS, **case.body}
    if case.path.endswith("count_tokens"):
        del body["max_tokens"]
    client.wait_idle()
    reply = client.request("POST", case.path, body)
    passed, note, error = False, "", None
    if not reply.ok:
        error = reply.error_text()
    else:
        try:
            passed, note = case.check(reply, client)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError) as e:
            note = f"unexpected response: {type(e).__name__}: {e}"
    stop = next((e["delta"].get("stop_reason") for e in reply.events if e.get("type") == "message_delta"), None)
    if isinstance(reply.body, dict):
        stop = reply.body.get("stop_reason", stop)
    return {"name": case.name, "description": case.description, "path": case.path, "http_status": reply.status,
            "passed": passed, "note": note, "error": error, "stop_reason": stop,
            "seconds": round(reply.seconds, 2), "response": _excerpt(reply)}


def protocol_probe(client: Client, model: str, cases=CASES, log: Callable[[str], None] = lambda line: None) -> dict:
    records = []
    for case in cases:
        record = run_case(client, model, case)
        records.append(record)
        log(f"protocol {case.name}: {'pass' if record['passed'] else 'FAIL'} (HTTP {record['http_status']})"
            f" {record['error'] or record['note']}"[:300])
    return {"cases": records, "passed": sum(r["passed"] for r in records), "total": len(records)}


def gate_failures(protocol: dict) -> list[dict]:
    """The cases of GATE_CASES that failed in a protocol probe result."""
    return [case for case in protocol["cases"] if case["name"] in GATE_CASES and not case["passed"]]


def probe_server(base_url: str, api_key: str, model: str, out_dir: Path, kinds=("speed", "protocol"),
                 context_tokens: int | None = None, max_context: int | None = None, targets=DEFAULT_TARGETS,
                 decode_tokens: int = DECODE_TOKENS, timeout_s: float = 1800.0, config: dict | None = None,
                 log: Callable[[str], None] = print) -> dict[str, Path]:
    """Run the probes against a server and write <out_dir>/<kind>.json. Stage 2
    calls this function also for a managed server."""
    client = Client(base_url, api_key, timeout_s)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for kind in kinds:
        header = {"schema": SCHEMA, "kind": kind, "base_url": base_url, "model": model, "config": config,
                  "server": client.server_info(), "started_at": utc_now()}
        if kind == "speed":
            data = speed_probe(client, model, targets, decode_tokens, context_tokens, max_context, log)
        else:
            data = protocol_probe(client, model, log=log)
        paths[kind] = out_dir / f"{kind}.json"
        paths[kind].write_text(json.dumps({**header, **data, "finished_at": utc_now()}, indent=2) + "\n")
    return paths
