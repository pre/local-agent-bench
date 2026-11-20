"""Speed of the server during a trial, from the print_timing lines of the llama-server log."""

import re
from datetime import datetime, timezone
from pathlib import Path

PROMPT = re.compile(r"prompt eval time =\s*([\d.]+) ms /\s*(\d+) tokens")
DECODE = re.compile(r"\|\s*eval time =\s*([\d.]+) ms /\s*(\d+) tokens")
DRAFT = re.compile(r"draft acceptance = [\d.]+ \(\s*(\d+) accepted /\s*(\d+) generated\)")
CANCEL = re.compile(r"cancel task, id_task = (\d+)")
PROGRESS = re.compile(r"\| task (\d+) \| n_gen =\s*(\d+)")


def parse_timings(log: str) -> dict:
    """Totals of the completed requests in the log. A rate is total tokens / total seconds.

    A cancelled request (for example at the time limit of a trial) has no totals
    in the log, only a line "n_gen = <tokens>" about each 3 s. Its values are
    not in the totals: cancelled_requests counts them, and
    cancelled_decode_tokens_min is the sum of their last n_gen values."""
    prompt = [(float(ms), int(n)) for ms, n in PROMPT.findall(log)]
    decode = [(float(ms), int(n)) for ms, n in DECODE.findall(log)]
    draft = [(int(a), int(g)) for a, g in DRAFT.findall(log)]
    prompt_tokens, prompt_s = sum(n for _, n in prompt), sum(ms for ms, _ in prompt) / 1000
    decode_tokens, decode_s = sum(n for _, n in decode), sum(ms for ms, _ in decode) / 1000
    accepted, generated = (sum(a for a, _ in draft), sum(g for _, g in draft)) if draft else (None, None)
    cancelled = set(CANCEL.findall(log))
    last_n_gen = {task: int(n) for task, n in PROGRESS.findall(log) if task in cancelled}
    return {
        "requests": len(prompt),
        "prompt_tokens": prompt_tokens,
        "prompt_seconds": round(prompt_s, 3),
        "prompt_tps": _rate(prompt_tokens, prompt_s, 2),
        "decode_tokens": decode_tokens,
        "decode_seconds": round(decode_s, 3),
        "decode_tps": _rate(decode_tokens, decode_s, 2),
        "draft_accepted": accepted,
        "draft_generated": generated,
        "draft_acceptance": _rate(accepted, generated, 4) if draft else None,
        "cancelled_requests": len(cancelled),
        "cancelled_decode_tokens_min": sum(last_n_gen.values()),
    }


def _rate(count: int, total: float, digits: int) -> float | None:
    return round(count / total, digits) if total else None


class ServerLogObserver:
    """Trial observer "server": saves the server log of the trial as server.log and parses it."""

    name = "server"

    def __init__(self, podman, container: str):
        self.podman = podman
        self.container = container

    def start(self, trial_dir: Path) -> None:
        self.trial_dir = trial_dir
        self.since = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def stop(self) -> dict:
        _, log = self.podman.call(["logs", "--since", self.since, self.container])
        (self.trial_dir / "server.log").write_text(log)
        return parse_timings(log)
