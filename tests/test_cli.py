import json

import pytest

from fakes import FakePodman, check_by_marker
from llm_eval import cli
from llm_eval.server import ExternalServer, ServerError
from llm_eval.config import load_config
from test_config import EXTERNAL, write
from test_results import RESULT_OK
from test_task import TASK_TOML, make_task
from test_trial import agent_that, root  # noqa: F401  (fixture)


class FakeSampler:
    name = "memory"

    def start(self, trial_dir):
        pass

    def stop(self):
        return {"samples": 1}


@pytest.fixture
def fake(monkeypatch):
    podman = FakePodman(agent=agent_that([RESULT_OK]), check=check_by_marker())
    monkeypatch.setattr(cli, "Podman", lambda: podman)
    monkeypatch.setattr(cli, "MemorySampler", FakeSampler)
    monkeypatch.setattr(ExternalServer, "check_health", lambda self: None)
    return podman


def run(root, *args) -> int:
    return cli.main(["--root", str(root), "run", *args])


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


def test_run_has_the_memory_observer(root, fake):
    out = root / "o"

    assert run(root, "--config", str(root / "c.toml"), "--out", str(out)) == 0

    result = json.loads((out / "t1-r1" / "result.json").read_text())
    assert result["memory"] == {"samples": 1}
    assert result["server"] is None


def test_make_observers(tmp_path):
    ext = load_config(write(tmp_path, EXTERNAL, "a.toml"))
    with_container = load_config(write(tmp_path, EXTERNAL.replace('mode = "external"',
                                                                   'mode = "external"\ncontainer = "x"'), "b.toml"))

    assert [o.name for o in cli.make_observers(ext.server, None)] == ["memory"]
    observers = cli.make_observers(with_container.server, "podman")
    assert [o.name for o in observers] == ["memory", "server"]
    assert observers[1].container == "x"


@pytest.fixture
def two_tasks(root):
    make_task(root / "tasks", "t2", TASK_TOML.format(id="t2").replace("quick = true", "quick = false"))
    (root / "tasks" / "t2" / "solution" / "fixed.txt").write_text("")
    return root


def trial_dirs(out):
    return sorted(d.name for d in out.iterdir() if d.is_dir())


@pytest.fixture
def hard_task(two_tasks):
    toml = TASK_TOML.format(id="h1").replace("quick = true", "quick = false\nhard = true")
    make_task(two_tasks / "tasks", "h1", toml)
    (two_tasks / "tasks" / "h1" / "solution" / "fixed.txt").write_text("")
    return two_tasks


@pytest.mark.parametrize("tier, dirs", [
    ("quick", ["t1-r1"]),
    ("base", ["t1-r1", "t2-r1"]),
    ("hard", ["h1-r1"]),
    ("full", ["h1-r1", "h1-r2", "h1-r3", "t1-r1", "t1-r2", "t1-r3", "t2-r1", "t2-r2", "t2-r3"]),
])
def test_tiers_select_tasks_and_repetitions(hard_task, fake, tier, dirs):
    out = hard_task / "o"

    assert run(hard_task, "--config", str(hard_task / "c.toml"), "--tier", tier, "--out", str(out)) == 0

    assert trial_dirs(out) == dirs


def test_task_and_reps_override_the_tier(two_tasks, fake):
    out = two_tasks / "o"

    code = run(two_tasks, "--config", str(two_tasks / "c.toml"), "--tier", "quick", "--task", "t2",
               "--reps", "2", "--out", str(out))

    assert code == 0
    assert trial_dirs(out) == ["t2-r1", "t2-r2"]


def test_several_configs_run_one_after_the_other(root, fake, monkeypatch):
    monkeypatch.setattr(cli, "DEFAULT_OUT", root / "evidence")
    (root / "d.toml").write_text((root / "c.toml").read_text().replace('"local-test"', '"other"'))

    assert run(root, "--config", str(root / "c.toml"), "--config", str(root / "d.toml")) == 0

    names = sorted(d.name.split("-", 1)[1] for d in (root / "evidence").iterdir())
    assert names == ["local-test", "other"]


def test_out_with_several_configs_is_an_error(root, fake, capsys):
    code = run(root, "--config", str(root / "c.toml"), "--config", str(root / "c.toml"), "--out", str(root / "o"))

    assert code == 2
    assert "--out" in capsys.readouterr().err


def test_existing_run_directory_needs_resume(root, fake, capsys):
    out = root / "o"
    assert run(root, "--config", str(root / "c.toml"), "--out", str(out)) == 0

    assert run(root, "--config", str(root / "c.toml"), "--out", str(out)) == 2
    assert f"--resume {out}" in capsys.readouterr().err


def test_resume(two_tasks, fake):
    out = two_tasks / "o"
    assert run(two_tasks, "--config", str(two_tasks / "c.toml"), "--reps", "2", "--out", str(out)) == 0
    (out / "t2-r2" / "result.json").unlink()
    agents_before = len(fake.of_kind("agent"))

    assert run(two_tasks, "--resume", str(out)) == 0

    assert len(fake.of_kind("agent")) == agents_before + 1
    assert (out / "t2-r2" / "result.json").exists()


def test_resume_refuses_a_changed_config(root, fake, capsys):
    out = root / "o"
    assert run(root, "--config", str(root / "c.toml"), "--out", str(out)) == 0
    (root / "c.toml").write_text((root / "c.toml").read_text().replace("65536", "1000"))

    assert run(root, "--resume", str(out)) == 2
    assert "changed" in capsys.readouterr().err


def test_resume_takes_the_plan_from_run_json(root, fake, capsys):
    assert run(root, "--resume", str(root / "o"), "--reps", "2") == 2
    assert "run.json" in capsys.readouterr().err


def test_resume_and_config_exclude_each_other(root, fake):
    with pytest.raises(SystemExit):
        run(root, "--resume", str(root / "o"), "--config", str(root / "c.toml"))


def test_server_error_of_one_config_does_not_stop_the_next(root, fake, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DEFAULT_OUT", root / "evidence")
    (root / "d.toml").write_text((root / "c.toml").read_text().replace('"local-test"', '"other"'))
    real = cli.open_server

    def open_server(cfg, *args, **kw):
        if cfg.url.endswith(":8080") and open_server.first:
            open_server.first = False
            raise ServerError("GTT used is too high")
        return real(cfg, *args, **kw)

    open_server.first = True
    monkeypatch.setattr(cli, "open_server", open_server)

    assert run(root, "--config", str(root / "c.toml"), "--config", str(root / "d.toml")) == 1

    assert "local-test: GTT used is too high" in capsys.readouterr().err
    assert len(fake.of_kind("agent")) == 1


def test_interrupt_tells_how_to_resume(root, fake, monkeypatch, capsys):
    def interrupt(*args, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "execute_run", interrupt)

    assert run(root, "--config", str(root / "c.toml"), "--out", str(root / "o")) == 130
    assert f"--resume {root / 'o'}" in capsys.readouterr().err


def test_replace_goes_to_the_server(root, fake, monkeypatch):
    seen = {}
    real = cli.open_server

    def open_server(cfg, scratch, **kw):
        seen.update(kw)
        return real(cfg, scratch, **kw)

    monkeypatch.setattr(cli, "open_server", open_server)

    assert run(root, "--config", str(root / "c.toml"), "--out", str(root / "o"), "--replace") == 0
    assert seen["replace"] is True
    assert seen["podman"] is fake
    assert seen["out_dir"] == root / "o"
