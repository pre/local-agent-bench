import json
from pathlib import Path

from llm_eval.podman import RunResult
from llm_eval.results import classify, redact_tree, secret_values, summarize_transcript
from llm_eval.workspace import CheckResult

RESULT_OK = {
    "type": "result", "subtype": "success", "is_error": False, "num_turns": 4,
    "duration_ms": 9000, "duration_api_ms": 8000, "ttft_ms": 70000, "api_error_status": None,
    "terminal_reason": "completed", "result": "Done.",
    "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 80,
              "cache_creation_input_tokens": 0},
}


def tool_use(name="Bash"):
    return {"type": "assistant", "message": {"id": "m1", "content": [
        {"type": "text", "text": "x"}, {"type": "tool_use", "id": "t1", "name": name, "input": {}}]}}


def tool_result(is_error=False):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1", "is_error": is_error, "content": "out"}]}}


def write_transcript(tmp_path: Path, events: list, junk: str = "") -> Path:
    path = tmp_path / "transcript.jsonl"
    path.write_text(junk + "".join(json.dumps(e) + "\n" for e in events))
    return path


def test_summarize_counts_tools_errors_and_reads_result(tmp_path):
    events = [
        {"type": "system", "subtype": "init", "claude_code_version": "2.1.328", "model": "m"},
        tool_use(), tool_result(), tool_use("Read"), tool_result(is_error=True),
        {"type": "system", "subtype": "api_retry", "attempt": 1},
        {"type": "assistant", "error": "server_error", "message": {"content": [{"type": "text", "text": "API Error"}]}},
        RESULT_OK,
    ]

    s = summarize_transcript(write_transcript(tmp_path, events, junk="not json\n"))

    assert s.tool_calls == 2
    assert s.tool_errors == 1
    assert s.api_errors == 2
    assert s.turns == 4
    assert s.claude_code_version == "2.1.328"
    assert s.result["subtype"] == "success"
    assert s.tokens == {"input": 100, "output": 20, "cache_read": 80, "cache_creation": 0}


PERMISSION_DENIED = {  # the shape of Claude Code 2.1.328: "message" is a string, not an object
    "type": "system", "subtype": "permission_denied", "tool_name": "Bash", "tool_use_id": "t1",
    "decision_reason_type": "safetyCheck", "decision_reason": "Dangerous rm operation",
    "message": "Dangerous rm operation detected: '/work/*'",
}


def test_summarize_counts_permission_denials_with_a_string_message(tmp_path):
    events = [tool_use(), PERMISSION_DENIED, tool_result(is_error=True), PERMISSION_DENIED, RESULT_OK]

    s = summarize_transcript(write_transcript(tmp_path, events))

    assert s.permission_denials == 2
    assert (s.tool_calls, s.tool_errors, s.turns) == (1, 1, 4)


def test_summarize_missing_or_empty_transcript(tmp_path):
    s = summarize_transcript(tmp_path / "none.jsonl")

    assert s.result is None
    assert s.turns == 0
    assert s.tokens is None


def agent(code=0, timed_out=False):
    return RunResult(code, timed_out, 10.0)


def check(passed=True, error=None):
    verify = None if error else {"passed": passed, "score": 1.0 if passed else 0.5, "checks": []}
    return CheckResult(verify, error, RunResult(0, False, 1.0))


def summary_with(tmp_path, result):
    return summarize_transcript(write_transcript(tmp_path, [result] if result else []))


def test_classify_pass(tmp_path):
    assert classify(agent(), summary_with(tmp_path, RESULT_OK), check(True)) == (True, None, None)


def test_classify_verify_failed(tmp_path):
    assert classify(agent(), summary_with(tmp_path, RESULT_OK), check(False))[:2] == (False, "verify_failed")


def test_classify_timeout_wins_over_a_passing_check(tmp_path):
    assert classify(agent(137, True), summary_with(tmp_path, None), check(True))[:2] == (False, "timeout")


def test_classify_check_error_is_harness_error(tmp_path):
    passed, reason, detail = classify(agent(), summary_with(tmp_path, RESULT_OK), check(error="verify.json is missing"))

    assert (passed, reason) == (False, "harness_error")
    assert "verify.json" in detail


def test_classify_max_turns(tmp_path):
    result = {**RESULT_OK, "subtype": "error_max_turns", "is_error": True}

    assert classify(agent(1), summary_with(tmp_path, result), check(True))[:2] == (False, "max_turns")


def test_classify_api_error(tmp_path):
    result = {**RESULT_OK, "is_error": True, "api_error_status": 500, "result": "API Error: 500"}

    assert classify(agent(1), summary_with(tmp_path, result), check(False))[:2] == (False, "api_error")


def test_classify_context_overflow(tmp_path):
    result = {**RESULT_OK, "is_error": True, "api_error_status": 400,
              "result": "API Error: 400 the request exceeds the available context size"}

    assert classify(agent(1), summary_with(tmp_path, result), check(False))[:2] == (False, "context_overflow")


def test_classify_no_result_event_is_harness_error(tmp_path):
    passed, reason, detail = classify(agent(125), summary_with(tmp_path, None), check(False))

    assert (passed, reason) == (False, "harness_error")
    assert "exit code 125" in detail


def test_redact_tree_replaces_secret_in_all_files(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.txt").write_text("token=SECRET1 and SECRET1")
    (tmp_path / "y.bin").write_bytes(b"\x00SECRET1\x00")
    (tmp_path / "z.txt").write_text("clean")
    (tmp_path / "link").symlink_to(tmp_path / "z.txt")

    changed = redact_tree(tmp_path, ["SECRET1"])

    assert changed == 2
    assert (tmp_path / "a" / "x.txt").read_text() == "token=<redacted> and <redacted>"
    assert (tmp_path / "y.bin").read_bytes() == b"\x00<redacted>\x00"
    assert (tmp_path / "z.txt").read_text() == "clean"


def test_redact_tree_replaces_each_secret_and_ignores_empty_values(tmp_path):
    (tmp_path / "x.txt").write_text("a=SECRET1 b=SECRET2 c=")

    changed = redact_tree(tmp_path, ["SECRET1", "", "SECRET2"])

    assert changed == 1
    assert (tmp_path / "x.txt").read_text() == "a=<redacted> b=<redacted> c="


def test_secret_values_add_the_values_of_custom_headers():
    env = {"ANTHROPIC_API_KEY": "key-0123456789", "ANTHROPIC_CUSTOM_HEADERS": "Sub-Key: abc12345\nOther: x y z w",
           "EMPTY": ""}

    values = secret_values(env)

    assert set(values) == {"key-0123456789", "Sub-Key: abc12345\nOther: x y z w", "abc12345"}
    assert values == sorted(values, key=len, reverse=True)


def test_secret_values_leave_out_short_values():
    # A placeholder such as "dummy" is not a secret, and its redaction would change normal text in the evidence.
    env = {"ANTHROPIC_API_KEY": "dummy", "ANTHROPIC_CUSTOM_HEADERS": "Sub-Key: 0123456789abcdef"}

    assert secret_values(env) == ["Sub-Key: 0123456789abcdef", "0123456789abcdef"]


def test_summarize_reads_models_and_cost(tmp_path):
    def reply(model):
        return {"type": "assistant", "message": {"model": model, "content": [{"type": "text", "text": "x"}]}}

    result = {**RESULT_OK, "total_cost_usd": 0.42, "modelUsage": {"Claude-Test-1": {"costUSD": 0.42}}}
    s = summarize_transcript(write_transcript(tmp_path, [reply("claude-test-1"), reply("claude-test-1"),
                                                         reply("other"), result]))

    assert s.models == ("claude-test-1", "other")
    assert s.result["total_cost_usd"] == 0.42
