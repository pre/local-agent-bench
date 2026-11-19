"""A fake llama-server on the loopback interface for the probe tests.

/tokenize gives one token for each character (the code point), so /detokenize
can reverse it. /v1/messages echoes the text of the request, calls the first
tool when the request has tools, and gives HTTP 500 for a system message in
the middle of the conversation (the old chat template did that).
"""

import http.server
import json
import threading

KEY = "sk-probe-secret-4711"


def _texts(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [t for item in value for t in _texts(item)]
    if isinstance(value, dict):
        return [t for key in ("text", "content") if key in value for t in _texts(value[key])]
    return []


TOOL_INPUTS = {
    "get_weather": {"city": "Helsinki", "unit": "celsius"},
    "get_time": {"city": "Tokyo"},
    "create_deployment": {"name": "web", "replicas": 3, "containers": [
        {"name": "nginx", "image": "nginx:1.27", "ports": [80, 443], "resources": {"cpu": "500m", "memory": "256Mi"}},
        {"name": "log-shipper", "image": "fluent-bit:3.1", "ports": [2020],
         "resources": {"cpu": "100m", "memory": "64Mi"}}]},
}


def message_reply(body: dict) -> dict:
    content = [{"type": "thinking", "thinking": "Let me think.", "signature": ""}]
    stop = "end_turn"
    tools = body.get("tools", [])
    last = body["messages"][-1]["content"]
    after_tool = isinstance(last, list) and any(b.get("type") == "tool_result" for b in last)
    if tools and not after_tool:
        content += [{"type": "tool_use", "id": f"toolu_{i}", "name": t["name"], "input": TOOL_INPUTS[t["name"]]}
                    for i, t in enumerate(tools)]
        stop = "tool_use"
    else:
        echo = " ".join(_texts(body.get("system", [])) + _texts(body["messages"]))
        content.append({"type": "text", "text": f"Echo: {echo} 391 -3 snow"})
    if body.get("max_tokens", 1000) < 20:
        content, stop = content[:1], "max_tokens"
    return {"id": "msg_1", "type": "message", "role": "assistant", "content": content, "model": body["model"],
            "stop_reason": stop, "usage": {"input_tokens": 10, "output_tokens": 5}}


def message_events(reply: dict) -> list[dict]:
    events = [{"type": "message_start", "message": {**reply, "content": [], "stop_reason": None}}]
    for i, block in enumerate(reply["content"]):
        if block["type"] == "tool_use":
            events.append({"type": "content_block_start", "index": i, "content_block": {**block, "input": {}}})
            text = json.dumps(block["input"])
            events += [{"type": "content_block_delta", "index": i,
                        "delta": {"type": "input_json_delta", "partial_json": text[k:k + 7]}}
                       for k in range(0, len(text), 7)]
        else:
            events.append({"type": "content_block_start", "index": i, "content_block": {"type": block["type"]}})
        events.append({"type": "content_block_stop", "index": i})
    events += [{"type": "message_delta", "delta": {"stop_reason": reply["stop_reason"]}, "usage": {}},
               {"type": "message_stop"}]
    return events


def chat_chunks(body: dict) -> list[dict]:
    prompt = body["messages"][0]["content"]
    n = body["max_tokens"]
    chunks = [{"choices": [{"index": 0, "delta": {"role": "assistant", "content": None}}]}]
    chunks += [{"choices": [{"index": 0, "delta": {"content": "word "}}]} for _ in range(3)]
    timings = {"cache_n": 3, "prompt_n": len(prompt) + 10, "prompt_ms": 2000.0, "predicted_n": n,
               "predicted_ms": n * 40.0, "draft_n": 100, "draft_n_accepted": 75}
    chunks.append({"choices": [{"index": 0, "finish_reason": "length", "delta": {}}], "timings": timings})
    return chunks


class State:
    def __init__(self):
        self.requests: list[tuple[str, str, dict | None]] = []
        self.busy_polls = 0  # /slots reports a busy slot this many times
        self.slot_params: dict = {"temperature": 1.0, "top_p": 0.95, "top_k": 20}
        self.fail: dict[str, tuple[int, str]] = {}  # path -> (status, body)
        self.fail_type = "text/plain"


def make_handler(state: State):
    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, status: int, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _sse(self, events: list[dict], named: bool):
            data = b""
            for e in events:
                if named:
                    data += f"event: {e['type']}\n".encode()
                data += f"data: {json.dumps(e)}\n\n".encode()
            if not named:
                data += b"data: [DONE]\n\n"
            self._send(200, data, "text/event-stream")

        def _authorized(self) -> bool:
            if self.headers.get("Authorization") == f"Bearer {KEY}":
                return True
            self._send(401, {"error": {"message": "Invalid API Key"}})
            return False

        def do_GET(self):
            state.requests.append(("GET", self.path, None))
            if not self._authorized():
                return
            if self.path == "/slots":
                busy = state.busy_polls > 0
                state.busy_polls -= 1
                self._send(200, [{"id": 0, "is_processing": busy, "params": state.slot_params}])
            elif self.path == "/props":
                self._send(200, {"build_info": "b1-test", "model_path": "/m.gguf", "total_slots": 1,
                                 "default_generation_settings": {"n_ctx": 4096}, "chat_template": "long"})
            else:
                self._send(404, {"error": {"message": "File Not Found"}})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.requests.append(("POST", self.path, body))
            if not self._authorized():
                return
            if self.path in state.fail:
                status, text = state.fail[self.path]
                self._send(status, text.encode(), state.fail_type)
            elif self.path == "/tokenize":
                self._send(200, {"tokens": [ord(c) for c in body["content"]]})
            elif self.path == "/detokenize":
                self._send(200, {"content": "".join(chr(t) for t in body["tokens"])})
            elif self.path == "/v1/chat/completions":
                self._sse(chat_chunks(body), named=False)
            elif self.path == "/v1/messages/count_tokens":
                self._send(200, {"input_tokens": 12})
            elif self.path == "/v1/messages":
                roles = [m["role"] for m in body["messages"]]
                if "system" in roles[1:]:
                    self._send(500, {"error": {"code": 500, "message": "System message must be at the beginning.",
                                               "type": "server_error"}})
                    return
                for key in ("temperature", "top_p", "top_k"):
                    if key in body:
                        state.slot_params[key] = body[key]
                reply = message_reply(body)
                if body.get("stream"):
                    self._sse(message_events(reply), named=True)
                else:
                    self._send(200, reply)
            else:
                self._send(404, {"error": {"message": "File Not Found"}})

        def log_message(self, *args):
            pass

    return Handler


class FakeLlama:
    def __init__(self):
        self.state = State()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.state))
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
