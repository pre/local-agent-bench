import json

import pytest

from fake_llama import KEY, FakeLlama
from llm_eval import probe
from llm_eval.probe import (CASES, Client, build_prompt, corpus_text, probe_server, protocol_probe, schema_errors,
                            speed_probe, stream_problems)


@pytest.fixture
def fake():
    server = FakeLlama()
    yield server
    server.stop()


@pytest.fixture
def client(fake):
    return Client(fake.url, KEY, timeout_s=10)


SCHEMA = {"type": "object", "required": ["name", "items"], "properties": {
    "name": {"type": "string"},
    "count": {"type": "integer"},
    "mode": {"type": "string", "enum": ["a", "b"]},
    "items": {"type": "array", "items": {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}}},
}}


def test_schema_errors_accepts_valid_input():
    assert schema_errors({"name": "x", "count": 2, "mode": "a", "items": [{"id": 1}]}, SCHEMA) == []


def test_schema_errors_finds_each_problem():
    errors = schema_errors({"count": True, "mode": "c", "items": [{"id": "1"}, {}]}, SCHEMA)

    assert errors == ["input: name is missing", "input.count: not integer", "input.mode: 'c' not in ['a', 'b']",
                      "input.items[0].id: not integer", "input.items[1]: id is missing"]


def test_schema_errors_wrong_top_type():
    assert schema_errors("text", SCHEMA) == ["input: not object"]


def good_stream():
    return [{"type": "message_start"}, {"type": "ping"},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "a"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}, {"type": "message_stop"}]


def test_stream_problems_good_sequence():
    assert stream_problems(good_stream()) == []


def test_stream_problems_bad_sequences():
    events = good_stream()
    assert stream_problems(events[1:-1]) == ["the first event is not message_start", "the last event is not message_stop"]
    assert stream_problems([e for e in events if e["type"] != "message_delta"]) == [
        "no message_delta with a stop_reason"]
    assert stream_problems([e for e in events if e["type"] != "content_block_stop"]) == ["block 0 is not stopped"]
    bad = events[:3] + [{"type": "content_block_delta", "index": 1, "delta": {}}] + events[4:]
    assert stream_problems(bad) == ["delta for block 1, but the open block is 0"]
    twice = events[:3] + [events[2]] + events[3:]
    assert stream_problems(twice) == ["block 0 starts before block 0 stops", "block index 0, expected 1"]


def test_corpus_has_prose_and_code():
    text = corpus_text()

    assert len(text) > 1_000_000
    assert "# File: argparse.py" in text[:200_000]
    assert "## assert" in text[:20_000]


def test_build_prompt_has_nonce_first_and_about_the_target_size(client):
    corpus = corpus_text()
    tokens = client.tokenize(corpus[:20_000])

    one = build_prompt(client, 5000, tokens)
    two = build_prompt(client, 5000, tokens)

    assert one.startswith("Probe ") and two.startswith("Probe ")
    assert one[:40] != two[:40]
    assert abs(len(one) - 5000) <= 2
    assert one.endswith(probe.INSTRUCTION)


def test_build_prompt_needs_enough_corpus(client):
    with pytest.raises(probe.ProbeError, match="corpus"):
        build_prompt(client, 5000, [65] * 100)


def test_speed_probe_records_timings(fake, client):
    data = speed_probe(client, "m", targets=[1000, 2000, 5000], decode_tokens=64, context_tokens=4096)

    first, second = data["results"]
    assert first["target_tokens"] == 1000
    assert first["prompt_tokens"] == 1010
    assert first["cache_tokens"] == 3
    assert first["prompt_seconds"] == 2.0
    assert first["prompt_tps"] == 505.0
    assert first["decode_tokens"] == 64
    assert first["decode_tps"] == 25.0
    assert first["draft_acceptance"] == 0.75
    assert first["finish_reason"] == "length"
    assert 0 <= first["ttft_s"] <= first["total_s"]
    assert first["error"] is None
    assert data["skipped"] == [{"target_tokens": 5000, "reason": "above the context of the configuration"
                                " (4096 tokens) minus 64 decode tokens and a margin of 1024"}]
    body = next(b for m, p, b in fake.state.requests if p == "/v1/chat/completions")
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["stream"] is True
    assert body["messages"][0]["content"].startswith("Probe ")


def test_speed_probe_max_context(client):
    data = speed_probe(client, "m", targets=[1000, 2000], decode_tokens=8, max_context=1500)

    assert [r["target_tokens"] for r in data["results"]] == [1000]
    assert data["skipped"][0]["reason"] == "above --max-context 1500"


def test_speed_probe_stops_after_an_error(fake, client):
    fake.state.fail["/v1/chat/completions"] = (503, "Loading model")

    data = speed_probe(client, "m", targets=[1000, 2000], decode_tokens=8)

    assert data["results"] == [{"target_tokens": 1000, "error": "HTTP 503: Loading model"}]
    assert data["skipped"] == [{"target_tokens": 2000, "reason": "an earlier request failed"}]


def test_wait_idle_polls_slots(fake, client):
    fake.state.busy_polls = 2

    waited = client.wait_idle(max_wait_s=5, poll_s=0.01)

    assert waited > 0
    assert sum(1 for _, p, _ in fake.state.requests if p == "/slots") == 3


def test_wait_idle_stops_at_the_limit(fake, client):
    fake.state.busy_polls = 1000

    assert client.wait_idle(max_wait_s=0.05, poll_s=0.01) >= 0.05


def test_wait_idle_without_slots_endpoint(fake):
    client = Client(fake.url, "wrong", timeout_s=5)

    assert client.wait_idle() == 0.0


def test_client_network_error():
    reply = Client("http://127.0.0.1:1", KEY, timeout_s=5).request("GET", "/health")

    assert reply.status is None
    assert reply.error


def test_protocol_probe_runs_each_case(fake, client):
    data = protocol_probe(client, "m")

    cases = {c["name"]: c for c in data["cases"]}
    assert list(cases) == [c.name for c in CASES]
    failed = [name for name, c in cases.items() if not c["passed"]]
    assert failed == ["system_in_middle", "thinking_disabled"]
    middle = cases["system_in_middle"]
    assert middle["http_status"] == 500
    assert middle["first_attempt"]["http_status"] == 500
    assert "first_attempt" not in cases["thinking_disabled"]
    assert "System message must be at the beginning" in middle["error"]
    assert "System message must be at the beginning" in middle["response"]
    assert cases["parallel_tools"]["note"].startswith("2 tool calls: get_weather, get_time")
    assert "message_start, content_block_start(thinking), content_block_stop" in cases["stream_tool_call"]["response"]
    assert cases["client_sampling"]["note"] == "/slots: temperature 0.2, top_p 0.5, top_k 7"
    assert cases["max_tokens"]["stop_reason"] == "max_tokens"
    assert data["passed"] == len(CASES) - 2


def gate_names(data: dict) -> list[str]:
    return [case["name"] for case in probe.gate_failures(data)]


def test_gate_case_that_fails_once_runs_again_and_passes(fake, client):
    fake.state.system_in_middle = "keep"
    fake.state.fail_next["/v1/messages"] = [(503, "busy")]

    data = protocol_probe(client, "m")

    plain = data["cases"][0]
    assert plain["passed"]
    assert plain["first_attempt"]["http_status"] == 503 and not plain["first_attempt"]["passed"]
    assert gate_names(data) == []


def test_gate_case_that_fails_twice_stops_the_gate(fake, client):
    fake.state.system_in_middle = "keep"
    fake.state.fail_next["/v1/messages"] = [(503, "busy"), (503, "busy")]

    data = protocol_probe(client, "m")

    assert gate_names(data) == ["plain"]
    assert data["cases"][0]["http_status"] == data["cases"][0]["first_attempt"]["http_status"] == 503


def test_gate_stops_on_a_rejected_system_message_in_the_middle(fake, client):
    data = protocol_probe(client, "m")

    assert gate_names(data) == ["system_in_middle"]


def test_gate_accepts_a_system_message_in_the_middle_that_is_dropped(fake, client):
    fake.state.system_in_middle = "drop"

    data = protocol_probe(client, "m")

    middle = next(case for case in data["cases"] if case["name"] == "system_in_middle")
    assert middle["http_status"] == 200 and not middle["passed"]
    assert "first_attempt" not in middle
    assert gate_names(data) == []


def test_protocol_case_with_invalid_tool_input(fake, client, monkeypatch):
    from fake_llama import TOOL_INPUTS
    monkeypatch.setitem(TOOL_INPUTS, "get_weather", {"city": 7})

    (case,) = [c for c in CASES if c.name == "tool_call"]
    record = probe.run_case(client, "m", case)

    assert not record["passed"]
    assert "input.city: not string" in record["note"]
    assert "input: unit is missing" in record["note"]


def test_probe_server_writes_files_without_the_key(fake, tmp_path):
    lines = []

    paths = probe_server(fake.url, KEY, "m", tmp_path / "probes", kinds=("speed", "protocol"), targets=[1000],
                         decode_tokens=8, config={"name": "c1", "sha256": "abc"}, log=lines.append)

    speed = json.loads(paths["speed"].read_text())
    protocol = json.loads(paths["protocol"].read_text())
    assert speed["schema"] == protocol["schema"] == 1
    assert speed["config"] == {"name": "c1", "sha256": "abc"}
    assert speed["server"] == {"build_info": "b1-test", "model_path": "/m.gguf", "total_slots": 1, "n_ctx": 4096}
    assert speed["finished_at"] >= speed["started_at"]
    assert protocol["total"] == len(CASES)
    for path in paths.values():
        assert KEY not in path.read_text()
    assert any("1000" in line for line in lines)
    assert any("system_in_middle" in line and "FAIL" in line for line in lines)


def test_client_event_that_is_not_json(fake, client):
    fake.state.fail["/v1/messages"] = (200, "data: {not json\n\n")
    fake.state.fail_type = "text/event-stream"

    reply = client.request("POST", "/v1/messages", {"stream": True})

    assert reply.status == 200
    assert not reply.ok
    assert reply.error.startswith("JSONDecodeError")


def answer(text: str) -> probe.Reply:
    return probe.Reply(200, body={"content": [{"type": "text", "text": text}]})


def case_named(name: str) -> probe.Case:
    return next(c for c in CASES if c.name == name)


@pytest.mark.parametrize("hyphen", ["-", "\u2010", "\u2011", "\u2012", "\u2013", "\u2212"])
def test_two_system_blocks_accepts_each_hyphen_character(hyphen):
    text = f"**Code A:** KIWI{hyphen}17  \n**Code B:** ZEBRA{hyphen}42"

    passed, _ = case_named("two_system_blocks").check(answer(text), None)

    assert passed


# The text blocks of the passes in the probes of real runs.
@pytest.mark.parametrize("text", [
    "**Code A:** KIWI-17  \n**Code B:** ZEBRA-42",
    "**Code A:** KIWI‑17  \n**Code B:** ZEBRA‑42",
    "Here are the codes you requested:\n\n- **Code A:** KIWI-17\n- **Code B:** ZEBRA-42",
    "Here you go:\n\n- **Code A:** KIWI-17\n- **Code B:** ZEBRA-42",
    "Sure!  \n- **Code A** is **KIWI-17**  \n- **Code B** is **ZEBRA-42**",
    "Code A: KIWI-17  \nCode B: ZEBRA-42",
    "Code A is KIWI-17. Code B is ZEBRA-42.",
    "Code A is KIWI-17.  \nCode B is ZEBRA-42.",
    "Code A is **KIWI-17**.  \nCode B is **ZEBRA-42**.",
])
def test_two_system_blocks_passes_the_answers_of_real_runs(text):
    passed, note = case_named("two_system_blocks").check(answer(text), None)

    assert passed
    assert note == f"text: {text!r}"


@pytest.mark.parametrize("text", [
    # 20261126T230254Z-glm-53-flash: a second reasoning section after the answer.
    "Code A: KIWI-17  \nCode B: ZEBRA-42We need answer? Need parse. User says \"Tell me code A and code B.\" Earlier"
    " system says Code A is KIWI-17.Code B is ZEBRA-42. Need provide codes? Is there hidden policy? It's benign."
    " Need maybe state Code A: KIWI-17, Code B: ZEBRA-42.</think>Code A: KIWI-17  \nCode B: ZEBRA-42",
    "<think>The system blocks give the codes.</think>Code A: KIWI-17, code B: ZEBRA-42",
    "The system gives Code A is KIWI-17 and Code B is ZEBRA-42. So: Code A: KIWI-17, Code B: ZEBRA-42",
])
def test_two_system_blocks_fails_when_the_reasoning_is_in_the_text(text):
    passed, note = case_named("two_system_blocks").check(answer(text), None)

    assert not passed
    assert note.startswith("the codes are in the text, but also reasoning")


def test_two_system_blocks_fails_without_a_code():
    text = "I don’t have any information about “code A” or “code B” in this conversation."

    passed, note = case_named("two_system_blocks").check(answer(text), None)

    assert not passed
    assert note == f"text: {text!r}"


@pytest.mark.parametrize("text", [
    "LIME-93", "LIME-93.", "LIME-93!", "lime-93\n", "`LIME-93`", "**LIME‑93**", "```text\nLIME-93\n```",
    "Code C is LIME-93.", "Code C: LIME-93", "Code C is: LIME-93", "Code C = LIME-93", "The code is LIME-93.",
    "<think>The system message gives code C.</think>LIME-93",
])
def test_system_in_middle_passes_when_the_answer_states_the_code(text):
    passed, _ = case_named("system_in_middle").check(answer(text), None)

    assert passed


@pytest.mark.parametrize("text", [
    "I don't have any information about \"code C\" — I can't confirm that it equals LIME-93, so I can't just"
    " repeat that.",
    "I don’t know code C. Is it LIME-93?",
    "Code C is not LIME-93.",
    "I cannot confirm LIME-93.",
    "Hello! What can I do for you?",
    "```c\n#include <stdio.h>\n\nint main(void) {\n    printf(\"Hello, World!\\n\");\n    return 0;\n}\n```",
])
def test_system_in_middle_fails_on_a_refusal_or_doubt(text):
    passed, note = case_named("system_in_middle").check(answer(text), None)

    assert not passed
    assert note.startswith("the code is in the text, but with refusal or doubt" if "LIME-93" in text else "text:")
