"""run --probe: the probes against the server of the run, and the gate of the basic protocol cases."""

import json

import pytest

from fake_llama import KEY, FakeLlama
from llm_eval import cli, probe
from test_cli import FakeSampler, fake, run  # noqa: F401  (fixture)
from test_trial import root  # noqa: F401  (fixture)


@pytest.fixture
def llama(root):
    server = FakeLlama()
    key = root.parent / "probe-key"
    key.write_text(KEY + "\n")
    config = (root / "c.toml").read_text()
    config = config.replace("http://127.0.0.1:8080", server.url).replace(str(root.parent / "key"), str(key))
    (root / "c.toml").write_text(config)
    yield server
    server.stop()


def paths_of(llama) -> list[str]:
    return [path for method, path, body in llama.state.requests if method == "POST"]


def test_probe_protocol_writes_the_file_before_the_trials(root, fake, llama):
    out = root / "o"

    assert run(root, "--config", str(root / "c.toml"), "--out", str(out), "--probe", "protocol") == 0

    protocol = json.loads((out / "probes" / "protocol.json").read_text())
    assert protocol["total"] == len(probe.CASES)
    assert protocol["config"]["name"] == "local-test"
    assert not (out / "probes" / "speed.json").exists()
    assert (out / "t1-r1" / "result.json").exists()


def test_probe_all_runs_protocol_first_then_speed(root, fake, llama):
    out = root / "o"

    assert run(root, "--config", str(root / "c.toml"), "--out", str(out), "--probe", "all",
               "--probe-target", "1000") == 0

    speed = json.loads((out / "probes" / "speed.json").read_text())
    assert [r["target_tokens"] for r in speed["results"]] == [1000]
    posts = paths_of(llama)
    assert posts.index("/v1/messages") < posts.index("/v1/chat/completions")
    assert KEY not in (out / "probes" / "speed.json").read_text()


def test_probe_memory_goes_to_the_probe_directory(root, fake, llama, monkeypatch):
    class Sampler(FakeSampler):
        def start(self, trial_dir):
            (trial_dir / "memory.csv").write_text("time,gtt_used_mib\n")

        def stop(self):
            return {"gtt_used_peak_mib": 90000, "samples": 3}

    monkeypatch.setattr(cli, "MemorySampler", Sampler)
    out = root / "o"

    assert run(root, "--config", str(root / "c.toml"), "--out", str(out), "--probe", "protocol") == 0

    assert json.loads((out / "probes" / "memory.json").read_text()) == {"gtt_used_peak_mib": 90000, "samples": 3}
    assert (out / "probes" / "memory.csv").exists()


def test_speed_targets_of_a_run_are_1000_and_23000(root, fake, monkeypatch):
    seen = []

    def probe_server(base_url, api_key, model, out_dir, kinds, **kw):
        seen.append((kinds, kw["targets"]))
        return {}

    monkeypatch.setattr(probe, "probe_server", probe_server)

    assert run(root, "--config", str(root / "c.toml"), "--out", str(root / "o"), "--probe", "speed") == 0
    assert seen == [(("speed",), (1000, 23000))]


@pytest.mark.parametrize("probe_args", [["protocol"], ["all", "--probe-target", "1000"]])
def test_gate_stops_the_trials_when_a_basic_case_fails(root, fake, llama, probe_args, capsys):
    llama.state.fail["/v1/messages"] = (500, "template error")
    out = root / "o"

    assert run(root, "--config", str(root / "c.toml"), "--out", str(out), "--probe", *probe_args) == 1

    assert fake.of_kind("agent") == []
    assert not (out / "probes" / "speed.json").exists()
    assert json.loads((out / "probes" / "memory.json").read_text()) == {"samples": 1}
    info = json.loads((out / "run.json").read_text())
    assert info["probe_gate"]["failed_cases"] == ["plain", "tool_call", "tool_round_trip"]
    assert info["tasks"] == ["t1"] and info["config"]["name"] == "local-test"
    assert "plain" in (out / "run.log").read_text()
    err = capsys.readouterr().err
    assert "tool_round_trip" in err and "HTTP 500" in err
    assert cli.main(["report", str(out)]) == 0
    assert "STOPPED: the protocol probe failed the basic cases plain" in capsys.readouterr().out


def test_gate_ignores_the_other_cases(root, fake, llama):
    llama.state.fail["/v1/messages/count_tokens"] = (500, "no")
    out = root / "o"

    assert run(root, "--config", str(root / "c.toml"), "--out", str(out), "--probe", "protocol") == 0
    assert (out / "t1-r1" / "result.json").exists()


def test_gate_of_one_config_does_not_stop_the_next(root, fake, llama, monkeypatch):
    monkeypatch.setattr(cli, "DEFAULT_OUT", root / "evidence")
    bad = FakeLlama()
    bad.state.fail["/v1/messages"] = (400, "bad")
    (root / "d.toml").write_text((root / "c.toml").read_text().replace(llama.url, bad.url)
                                 .replace('"local-test"', '"broken"'))
    try:
        code = run(root, "--config", str(root / "d.toml"), "--config", str(root / "c.toml"), "--probe", "protocol")
    finally:
        bad.stop()

    assert code == 1
    assert len(fake.of_kind("agent")) == 1
    runs = {d.name.split("-", 1)[1]: d for d in (root / "evidence").iterdir()}
    assert "probe_gate" in json.loads((runs["broken"] / "run.json").read_text())
    assert (runs["local-test"] / "t1-r1" / "result.json").exists()


def test_gate_on_resume_keeps_run_json(root, fake, llama):
    out = root / "o"
    assert run(root, "--config", str(root / "c.toml"), "--out", str(out), "--reps", "2") == 0
    (out / "t1-r2" / "result.json").unlink()
    llama.state.fail["/v1/messages"] = (500, "template error")

    assert run(root, "--resume", str(out), "--probe", "protocol") == 1

    info = json.loads((out / "run.json").read_text())
    assert info["reps"] == 2 and info["trials"] == 2
    assert info["probe_gate"]["failed_cases"] == ["plain", "tool_call", "tool_round_trip"]


def test_probe_target_needs_probe(root, fake, capsys):
    assert run(root, "--config", str(root / "c.toml"), "--probe-target", "1000") == 2
    assert "--probe" in capsys.readouterr().err
