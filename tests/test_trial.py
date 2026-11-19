import json
from pathlib import Path

import pytest

from fakes import FakePodman, check_by_marker
from llm_eval.config import load_config
from llm_eval.server import ExternalServer
from llm_eval.task import load_task
from llm_eval.trial import RunContext, agent_env, execute_run, make_run_id
from test_config import EXTERNAL
from test_results import RESULT_OK, tool_result, tool_use
from test_task import make_task

SECRET = "sk-secret-123"


@pytest.fixture
def root(tmp_path) -> Path:
    root = tmp_path / "repo"
    (root / "client-config").mkdir(parents=True)
    (root / "client-config" / "settings.json").write_text("{}")
    d = make_task(root / "tasks", "t1")
    (d / "workspace" / "main.txt").write_text("bug\n")
    (d / "solution" / "fixed.txt").write_text("")
    key = tmp_path / "key"
    key.write_text(SECRET + "\n")
    (root / "c.toml").write_text(EXTERNAL.replace("~/key", str(key)))
    return root


def agent_that(events, fix=True, code=0):
    def behaviour(spec, m):
        if fix:
            (m["/work"] / "fixed.txt").write_text(f"token {SECRET}\n")
        return code, "".join(json.dumps(e) + "\n" for e in events)

    return behaviour


def run(root: Path, podman, reps=1, observers=()):
    cfg = load_config(root / "c.toml")
    out = root / "out"
    with ExternalServer(cfg.server, root / "scratch") as server:
        ctx = RunContext("run1", out, cfg, root, podman, server, list(observers))
        results = execute_run(ctx, [load_task(root / "tasks" / "t1")], reps)
    return results, out


def test_trial_pass_writes_all_files(root):
    events = [{"type": "system", "subtype": "init", "claude_code_version": "2.1.328"},
              tool_use(), tool_result(), RESULT_OK]
    podman = FakePodman(agent=agent_that(events), check=check_by_marker(),
                        diff=lambda s, m: (0, "diff --git\n"))

    results, out = run(root, podman)

    trial = out / "t1-r1"
    result = json.loads((trial / "result.json").read_text())
    assert results == [result]
    assert result["passed"] is True
    assert result["failure_reason"] is None
    assert result["score"] == 1.0
    assert result["turns"] == 4
    assert result["tool_calls"] == 1
    assert result["tokens"]["input"] == 100
    assert result["claude_code_version"] == "2.1.328"
    assert result["image"]["digest"] == "sha256:digest"
    assert result["config"]["sha256"] == load_config(root / "c.toml").sha256
    assert result["wall_time_s"] == 1.5
    assert result["server"] is None and result["memory"] is None
    assert len(result["baseline"]) == 40
    for name in ("transcript.jsonl", "verify.json", "agent.diff", "agent.stderr", "check/check.stderr"):
        assert (trial / name).exists(), name
    assert (trial / "claude-config" / "settings.json").exists()
    run_json = json.loads((out / "run.json").read_text())
    assert run_json["run_id"] == "run1"
    assert run_json["passed"] == 1 and run_json["trials"] == 1


def test_agent_container_spec(root):
    podman = FakePodman(agent=agent_that([RESULT_OK]), check=check_by_marker())

    run(root, podman)

    (spec,) = podman.of_kind("agent")
    mounts = {m.container: m for m in spec.mounts}
    assert set(mounts) == {"/work", "/claude-config", "/run/llm-eval"}
    assert spec.network == "none"
    assert spec.secret_env == {"ANTHROPIC_AUTH_TOKEN": SECRET}
    assert SECRET not in json.dumps(spec.env)
    claude = spec.command[spec.command.index("claude"):]
    assert claude[:3] == ["claude", "-p", "Do the work.\n"]
    assert claude[3:] == ["--output-format", "stream-json", "--verbose", "--max-turns", "30",
                          "--dangerously-skip-permissions"]
    assert podman.timeouts[podman.specs.index(spec)] == 600


def test_secret_is_removed_from_trial_files(root):
    events = [{"type": "assistant", "message": {"content": [{"type": "text", "text": f"key {SECRET}"}]}}, RESULT_OK]
    podman = FakePodman(agent=agent_that(events), check=check_by_marker())

    _, out = run(root, podman)

    for path in out.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes(), path


def test_timeout_trial(root):
    podman = FakePodman(agent=lambda s, m: ("timeout", ""), check=check_by_marker())

    results, _ = run(root, podman)

    assert results[0]["passed"] is False
    assert results[0]["failure_reason"] == "timeout"


def test_reps_make_one_directory_each(root):
    podman = FakePodman(agent=agent_that([RESULT_OK], fix=False), check=check_by_marker())

    results, out = run(root, podman, reps=2)

    assert [r["rep"] for r in results] == [1, 2]
    assert [r["failure_reason"] for r in results] == ["verify_failed", "verify_failed"]
    assert (out / "t1-r2" / "result.json").exists()


def test_observers_add_their_values(root):
    class Observer:
        name = "memory"

        def start(self, trial_dir):
            self.dir = trial_dir

        def stop(self):
            return {"gtt_peak_mib": 1, "dir": self.dir.name}

    podman = FakePodman(agent=agent_that([RESULT_OK]), check=check_by_marker())

    results, _ = run(root, podman, observers=[Observer()])

    assert results[0]["memory"] == {"gtt_peak_mib": 1, "dir": "t1-r1"}


def test_agent_env_from_config(root):
    cfg = load_config(root / "c.toml")

    env = agent_env(cfg, "http://127.0.0.1:8080")

    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8080"
    assert env["ANTHROPIC_MODEL"] == "test-model"
    for tier in ("FABLE", "OPUS", "SONNET", "HAIKU"):
        assert env[f"ANTHROPIC_DEFAULT_{tier}_MODEL"] == "test-model"
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] == "test-model"
    assert env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "65536"
    assert env["CLAUDE_CODE_ATTRIBUTION_HEADER"] == "0"
    assert "ANTHROPIC_AUTH_TOKEN" not in env


def test_make_run_id():
    from datetime import datetime, timezone

    assert make_run_id("cfg", datetime(2026, 11, 19, 18, 1, 2, tzinfo=timezone.utc)) == "20261119T180102Z-cfg"
