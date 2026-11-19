"""Read the stream-json transcript of Claude Code, decide the outcome of a trial
and remove the API key from the result files."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .podman import RunResult
from .workspace import CheckResult

FAILURE_REASONS = ("verify_failed", "timeout", "max_turns", "api_error", "context_overflow", "harness_error")
CONTEXT_OVERFLOW = re.compile(r"prompt is too long|exceeds the available context|context length", re.IGNORECASE)


@dataclass(frozen=True)
class TranscriptSummary:
    result: dict | None  # the final "result" event of Claude Code
    claude_code_version: str | None
    turns: int
    tool_calls: int
    tool_errors: int
    api_errors: int
    error_texts: tuple[str, ...]

    @property
    def tokens(self) -> dict | None:
        if not self.result or "usage" not in self.result:
            return None
        usage = self.result["usage"]
        return {
            "input": usage.get("input_tokens", 0),
            "output": usage.get("output_tokens", 0),
            "cache_read": usage.get("cache_read_input_tokens", 0),
            "cache_creation": usage.get("cache_creation_input_tokens", 0),
        }


def read_events(path: Path) -> list[dict]:
    """Return the JSON objects of the file. Lines that are not JSON are ignored."""
    if not path.exists():
        return []
    events = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def summarize_transcript(path: Path) -> TranscriptSummary:
    result, version = None, None
    tool_calls = tool_errors = api_errors = assistant_messages = 0
    error_texts = []
    for event in read_events(path):
        kind = event.get("type")
        content = event.get("message", {}).get("content", [])
        if kind == "system" and event.get("subtype") == "init":
            version = event.get("claude_code_version")
        elif kind == "system" and event.get("subtype") == "api_retry":
            api_errors += 1
        elif kind == "assistant":
            assistant_messages += 1
            tool_calls += sum(1 for block in content if block.get("type") == "tool_use")
            if event.get("error"):
                api_errors += 1
                error_texts += [block.get("text", "") for block in content if block.get("type") == "text"]
        elif kind == "user" and isinstance(content, list):
            tool_errors += sum(1 for b in content if b.get("type") == "tool_result" and b.get("is_error"))
        elif kind == "result":
            result = event
    turns = result.get("num_turns", assistant_messages) if result else assistant_messages
    return TranscriptSummary(result, version, turns, tool_calls, tool_errors, api_errors, tuple(error_texts))


def classify(agent: RunResult, summary: TranscriptSummary, check: CheckResult | None) -> tuple[bool, str | None, str | None]:
    """Return (passed, failure reason, detail). A trial passes only when Claude Code
    completed normally and the check passed."""
    result = summary.result
    if agent.timed_out:
        return False, "timeout", None
    if check is None or check.error:
        return False, "harness_error", f"check: {check.error if check else 'did not run'}"
    if result is None:
        return False, "harness_error", f"no result event from Claude Code, exit code {agent.exit_code}"
    if result.get("subtype") == "error_max_turns":
        return False, "max_turns", None
    if result.get("is_error") or result.get("api_error_status"):
        texts = [str(result.get("result", "")), *summary.error_texts]
        detail = texts[0][:500] or None
        if any(CONTEXT_OVERFLOW.search(t) for t in texts):
            return False, "context_overflow", detail
        return False, "api_error", detail
    if not check.verify["passed"]:
        return False, "verify_failed", None
    return True, None, None


def redact_tree(root: Path, secret: str, replacement: str = "<redacted>") -> int:
    """Replace `secret` in each regular file below root. Return the count of changed files."""
    needle, changed = secret.encode(), 0
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        if needle in data:
            path.write_bytes(data.replace(needle, replacement.encode()))
            changed += 1
    return changed


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")
