"""The report, compare and probe commands."""

import json

import pytest

from fake_llama import KEY, FakeLlama
from llm_eval import cli
from runfiles import SHA_B, trial, write_run
from test_config import EXTERNAL, REMOTE


@pytest.fixture
def runs(tmp_path):
    a = write_run(tmp_path / "run-a", [trial("t1"), trial("t2", passed=False)])
    b = write_run(tmp_path / "run-b", [trial("t1", name="c2", sha=SHA_B), trial("t2", name="c2", sha=SHA_B)])
    return a, b


def test_report_to_stdout(runs, capsys):
    assert cli.main(["report", str(runs[0]), str(runs[1])]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Evaluation report")
    assert "| t2 | 1/1 | 0/1 |" in out


def test_report_to_file(runs, tmp_path, capsys):
    out = tmp_path / "report.md"

    assert cli.main(["report", str(runs[0]), "--out", str(out)]) == 0

    assert out.read_text().startswith("# Evaluation report")
    assert str(out) in capsys.readouterr().out


def test_report_of_a_missing_directory(tmp_path, capsys):
    assert cli.main(["report", str(tmp_path / "nope")]) == 2
    assert "nope" in capsys.readouterr().err


def test_compare(runs, capsys):
    assert cli.main(["compare", str(runs[0]), str(runs[1])]) == 0
    assert "# Comparison" in capsys.readouterr().out


@pytest.fixture
def fake():
    server = FakeLlama()
    yield server
    server.stop()


def probe_config(tmp_path, url):
    key = tmp_path / "key"
    key.write_text(KEY + "\n")
    path = tmp_path / "c.toml"
    path.write_text(EXTERNAL.replace("~/key", str(key)).replace("http://127.0.0.1:8080", url)
                    .replace("65536", "4096"))
    return path


def test_probe_protocol(fake, tmp_path, capsys):
    out = tmp_path / "out"

    code = cli.main(["probe", "--config", str(probe_config(tmp_path, fake.url)), "--out", str(out),
                     "--kind", "protocol"])

    assert code == 0
    data = json.loads((out / "probes" / "protocol.json").read_text())
    assert data["config"]["name"] == "local-test"
    assert not (out / "probes" / "speed.json").exists()
    assert "protocol system_in_middle: FAIL" in capsys.readouterr().out


def test_probe_speed_uses_context_and_max_context(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "DEFAULT_OUT", tmp_path / "evidence")

    code = cli.main(["probe", "--config", str(probe_config(tmp_path, fake.url)), "--kind", "speed",
                     "--target", "1000", "--target", "2000", "--target", "3500", "--max-context", "1500",
                     "--decode-tokens", "16"])

    assert code == 0
    (run_dir,) = (tmp_path / "evidence").iterdir()
    assert run_dir.name.startswith("probe-") and run_dir.name.endswith("-local-test")
    data = json.loads((run_dir / "probes" / "speed.json").read_text())
    assert [r["target_tokens"] for r in data["results"]] == [1000]
    assert [s["target_tokens"] for s in data["skipped"]] == [2000, 3500]
    assert "context of the configuration (4096 tokens)" in data["skipped"][1]["reason"]


def test_probe_refuses_a_remote_endpoint(tmp_path, capsys):
    path = tmp_path / "remote.toml"
    path.write_text(REMOTE)

    code = cli.main(["probe", "--config", str(path)])

    assert code == 2
    assert "local server" in capsys.readouterr().err
