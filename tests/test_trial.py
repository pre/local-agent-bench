import json
from pathlib import Path

import pytest

from fakes import FakePodman, check_by_marker
from llm_eval.config import load_config
from llm_eval.podman import run_args
from llm_eval.server import ExternalServer, RemoteServer, ServerError, open_server
from llm_eval.task import load_task
from llm_eval.trial import RunContext, agent_env, execute_run, make_run_id
from test_config import EXTERNAL, REMOTE
from test_results import RESULT_OK, tool_result, tool_use
from test_task import make_task

SECRET = "sk-secret-123"


@pytest.fixture(autouse=True)
def healthy(monkeypatch):
    monkeypatch.setattr(ExternalServer, "check_health", lambda self: None)
    monkeypatch.setattr(RemoteServer, "check_health", lambda self: None)


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


def run(root: Path, podman, reps=1, observers=(), resume=False, config="c.toml"):
    cfg = load_config(root / config)
    out = root / "out"
    with open_server(cfg.server, root / "scratch", gtt_total=lambda: 112640) as server:
        ctx = RunContext("run1", out, cfg, root, podman, server, list(observers))
        results = execute_run(ctx, [load_task(root / "tasks" / "t1")], reps, resume=resume)
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


def test_run_json_has_the_server_values(root):
    podman = FakePodman(agent=agent_that([RESULT_OK]), check=check_by_marker())

    _, out = run(root, podman)

    server = json.loads((out / "run.json").read_text())["server"]
    assert server == {"mode": "external", "url": "http://127.0.0.1:8080", "container": None, "gtt_total_mib": 112640}


def test_exception_in_a_trial_becomes_a_harness_error(root):
    calls = []

    def agent(spec, m):
        calls.append(spec)
        if len(calls) == 1:
            raise RuntimeError("podman went away")
        return agent_that([RESULT_OK])(spec, m)

    class Observer:
        name = "memory"
        stopped = 0

        def start(self, trial_dir):
            pass

        def stop(self):
            Observer.stopped += 1
            return {}

    podman = FakePodman(agent=agent, check=check_by_marker())

    results, out = run(root, podman, reps=2, observers=[Observer()])

    error, ok = results
    assert error["passed"] is False
    assert error["failure_reason"] == "harness_error"
    assert "RuntimeError: podman went away" in error["failure_detail"]
    assert set(error) == set(ok)
    assert json.loads((out / "t1-r1" / "result.json").read_text()) == error
    assert "podman went away" in (out / "t1-r1" / "harness_error.txt").read_text()
    assert ok["passed"] is True
    assert Observer.stopped == 2


def test_progress_line_for_each_trial(root, capsys):
    podman = FakePodman(agent=agent_that([RESULT_OK]), check=check_by_marker())

    _, out = run(root, podman, reps=2)

    lines = [line for line in capsys.readouterr().out.splitlines() if " t1 r" in line]
    assert "[1/2] local-test t1 r1 PASS wall 1.5 s passed 1/1" in lines[0]
    assert "[2/2] local-test t1 r2 PASS wall 1.5 s passed 2/2" in lines[1]
    log = (out / "run.log").read_text()
    assert lines[0] in log and lines[1] in log


def test_resume_skips_trials_with_a_result(root, capsys):
    podman = FakePodman(agent=agent_that([RESULT_OK]), check=check_by_marker())
    _, out = run(root, podman, reps=3)
    (out / "t1-r2" / "result.json").unlink()  # an interrupted trial
    (out / "t1-r3" / "result.json").unlink()
    podman = FakePodman(agent=agent_that([RESULT_OK]), check=check_by_marker())

    results, _ = run(root, podman, reps=3, resume=True)

    assert len(podman.of_kind("agent")) == 2
    assert [r["rep"] for r in results] == [1, 2, 3]
    assert all(r["passed"] for r in results)
    run_json = json.loads((out / "run.json").read_text())
    assert run_json["trials"] == 3 and run_json["passed"] == 3
    assert len(run_json["resumed_at"]) == 1
    assert "[3/3] local-test t1 r3 PASS" in capsys.readouterr().out


def test_unhealthy_server_stops_the_run(root, monkeypatch):
    def unhealthy(self):
        raise ServerError("server down")

    monkeypatch.setattr(ExternalServer, "check_health", unhealthy)
    podman = FakePodman(agent=agent_that([RESULT_OK]), check=check_by_marker())

    with pytest.raises(ServerError):
        run(root, podman)

    assert podman.of_kind("agent") == []


API_KEY = "gw-api-key-77"
SUBSCRIPTION_KEY = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def remote_root(root, tmp_path):
    profile = tmp_path / "profile.sh"
    profile.write_text(f'export ANTHROPIC_API_KEY="{API_KEY}"\n'
                       f'export ANTHROPIC_CUSTOM_HEADERS="Sub-Key: {SUBSCRIPTION_KEY}"\n')
    (root / "remote.toml").write_text(REMOTE.replace("~/profile.sh", str(profile)))
    return root


def leaking_agent(spec, m):
    """An agent that writes all its secret values (and the subscription key alone)
    into its work, its transcript and its configuration directory."""
    leak = " ".join([*spec.secret_env.values(), SUBSCRIPTION_KEY])
    (m["/work"] / "fixed.txt").write_text(leak)
    (m["/claude-config"] / "session.json").write_text(json.dumps({"env": dict(spec.secret_env)}))
    reply = {"type": "assistant", "message": {"model": "claude-test-1", "content": [{"type": "text", "text": leak}]}}
    result = {**RESULT_OK, "total_cost_usd": 0.42, "modelUsage": {"Claude-Test-1": {"costUSD": 0.42}}}
    return 0, "".join(json.dumps(e) + "\n" for e in [reply, result])


def test_remote_trial_gets_the_profile_secrets_and_no_local_key(remote_root):
    podman = FakePodman(agent=leaking_agent, check=check_by_marker())

    run(remote_root, podman, config="remote.toml")

    (spec,) = podman.of_kind("agent")
    assert spec.secret_env == {"ANTHROPIC_API_KEY": API_KEY, "ANTHROPIC_CUSTOM_HEADERS": f"Sub-Key: {SUBSCRIPTION_KEY}"}
    assert spec.network == "none"
    assert spec.env["ANTHROPIC_BASE_URL"] == "https://gateway.example.org/api"
    assert spec.env["HTTPS_PROXY"] == "http://127.0.0.1:8080"
    assert spec.env["NODE_EXTRA_CA_CERTS"] == spec.env["SSL_CERT_FILE"] == "/run/llm-eval-ca.crt"
    for name in ("ANTHROPIC_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL", "ANTHROPIC_DEFAULT_FABLE_MODEL",
                 "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL"):
        assert spec.env[name] == "Claude-Test-1"
    assert "CLAUDE_CODE_MAX_CONTEXT_TOKENS" not in spec.env
    assert "/run/llm-eval-ca.crt" in {m.container for m in spec.mounts}


def test_remote_secrets_are_not_in_podman_arguments_or_trial_files(remote_root):
    podman = FakePodman(agent=leaking_agent, check=check_by_marker())

    results, out = run(remote_root, podman, config="remote.toml")

    assert results[0]["passed"] is True
    secrets = [API_KEY.encode(), SUBSCRIPTION_KEY.encode()]
    arguments = [" ".join(run_args(s)) for s in [*podman.specs, *podman.outputs]]
    arguments += [" ".join(call) for call in podman.calls]
    for secret in secrets:
        assert all(secret.decode() not in a for a in arguments)
    files = [p for p in out.rglob("*") if p.is_file()]
    assert out / "t1-r1" / "claude-config" / "session.json" in files
    for path in files:
        data = path.read_bytes()
        assert not any(secret in data for secret in secrets), path


def test_result_has_cost_and_the_models_of_the_responses(remote_root):
    podman = FakePodman(agent=leaking_agent, check=check_by_marker())

    results, out = run(remote_root, podman, config="remote.toml")

    assert results[0]["total_cost_usd"] == 0.42
    assert results[0]["models"] == ["claude-test-1"]
    assert results[0]["model_usage"] == {"Claude-Test-1": {"costUSD": 0.42}}
    run_json = json.loads((out / "run.json").read_text())
    assert run_json["reported_models"] == ["claude-test-1"]
    assert run_json["server"]["mode"] == "remote"
    assert "gtt_total_mib" not in run_json["server"]
