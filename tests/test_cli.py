import json

import pytest

from fakes import FakePodman, check_by_marker
from llm_eval import cli
from llm_eval.server import ExternalServer, ServerError
from test_results import RESULT_OK
from test_trial import agent_that, root  # noqa: F401  (fixture)


@pytest.fixture
def fake(monkeypatch):
    podman = FakePodman(agent=agent_that([RESULT_OK]), check=check_by_marker())
    monkeypatch.setattr(cli, "Podman", lambda: podman)
    monkeypatch.setattr(ExternalServer, "check_health", lambda self: None)
    return podman


def test_selfcheck_ok(root, fake, capsys):
    code = cli.main(["--root", str(root), "selfcheck"])

    assert code == 0
    assert "t1: ok" in capsys.readouterr().out


def test_selfcheck_failure(root, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Podman", lambda: FakePodman(check=check_by_marker("main.txt")))

    code = cli.main(["--root", str(root), "selfcheck", "t1"])

    assert code == 1
    assert "t1: FAIL" in capsys.readouterr().out


def test_selfcheck_unknown_task(root, fake, capsys):
    assert cli.main(["--root", str(root), "selfcheck", "nope"]) == 2
    assert "nope" in capsys.readouterr().err


def test_run_writes_results(root, fake, capsys):
    out = root / "results"

    code = cli.main(["--root", str(root), "run", "--config", str(root / "c.toml"), "--task", "t1",
                     "--reps", "2", "--out", str(out)])

    assert code == 0
    assert json.loads((out / "t1-r2" / "result.json").read_text())["passed"] is True
    text = capsys.readouterr().out
    assert "t1 r1 PASS" in text
    assert str(out) in text


def test_run_default_out_dir(root, fake, monkeypatch):
    monkeypatch.setattr(cli, "DEFAULT_OUT", root / "evidence")

    assert cli.main(["--root", str(root), "run", "--config", str(root / "c.toml")]) == 0

    (run_dir,) = (root / "evidence").iterdir()
    assert run_dir.name.endswith("-local-test")


def test_run_stops_when_selfcheck_fails(root, monkeypatch, capsys):
    podman = FakePodman(check=check_by_marker("main.txt"))
    monkeypatch.setattr(cli, "Podman", lambda: podman)

    code = cli.main(["--root", str(root), "run", "--config", str(root / "c.toml"), "--out", str(root / "o")])

    assert code == 1
    assert podman.of_kind("agent") == []
    assert "selfcheck" in capsys.readouterr().err


def test_run_stops_when_server_is_not_healthy(root, fake, monkeypatch, capsys):
    def unhealthy(self):
        raise ServerError("server down")

    monkeypatch.setattr(ExternalServer, "check_health", unhealthy)

    code = cli.main(["--root", str(root), "run", "--config", str(root / "c.toml"), "--out", str(root / "o")])

    assert code == 1
    assert "server down" in capsys.readouterr().err


def test_run_bad_config(root, fake, capsys):
    (root / "bad.toml").write_text('[server]\nmode = "other"\n')

    assert cli.main(["--root", str(root), "run", "--config", str(root / "bad.toml")]) == 2
    assert "server.mode" in capsys.readouterr().err
