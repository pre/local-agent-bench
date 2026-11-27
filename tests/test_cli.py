import json
import os
import signal
from types import SimpleNamespace

import pytest

from fakes import FakePodman, check_by_marker
from llm_eval import cli
from llm_eval.server import ExternalServer, ServerError
from llm_eval.stop import send_guard_signal
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
    real = ExternalServer.__enter__

    def enter(self):  # the start of the server
        if enter.first:
            enter.first = False
            raise ServerError("GTT used is too high")
        return real(self)

    enter.first = True
    monkeypatch.setattr(ExternalServer, "__enter__", enter)

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


def test_interrupt_before_run_json_tells_how_to_start_again(root, fake, monkeypatch, capsys):
    def interrupt(*args, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr(ExternalServer, "__enter__", interrupt)  # a stop signal during the start of the server
    out = root / "o"

    code = run(root, "--config", str(root / "c.toml"), "--out", str(out), "--tier", "quick", "--task", "t1",
               "--reps", "2", "--probe", "speed", "--probe-target", "1000")

    assert code == 130
    assert (f"To start it again: llm-eval run --config {root / 'c.toml'} --out {out} --tier quick --task t1"
            " --reps 2 --probe speed --probe-target 1000") in capsys.readouterr().err


TRIP = {"reason": "gtt_margin", "limit_mib": 4096, "gtt_used_mib": 109000, "gtt_total_mib": 112640,
        "mem_available_mib": 20000, "phase": "trial t1-r1", "time": "2026-11-23T02:00:00+00:00"}
LOWEST = {"gtt_margin": {"mib": 3640, "limit_mib": 4096, "phase": "trial t1-r1", "time": "2026-11-23T02:00:00+00:00"},
          "mem_available": {"mib": 18000, "limit_mib": 2048, "phase": "start", "time": "2026-11-23T01:00:00+00:00"}}


@pytest.fixture
def servers(monkeypatch):
    """The servers that the run opens, one for each configuration."""
    opened = []
    real = cli.open_server

    def open_server(cfg, *args, **kw):
        opened.append(real(cfg, *args, **kw))
        return opened[-1]

    monkeypatch.setattr(cli, "open_server", open_server)
    return opened


def trip(server, phase: str) -> None:
    """What the memory guard of a managed server does, for an external server of a test."""
    assert server.phase == phase
    server.guard = SimpleNamespace(trip={**TRIP, "phase": phase}, lowest=LOWEST)
    send_guard_signal()


def run_dirs(root) -> dict[str, object]:
    return {d.name.split("-", 1)[1]: d for d in (root / "evidence").iterdir()}


def test_memory_guard_stops_its_configuration_and_the_next_runs(root, fake, servers, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DEFAULT_OUT", root / "evidence")
    (root / "d.toml").write_text((root / "c.toml").read_text().replace('"local-test"', '"other"'))
    phases = []
    monkeypatch.setattr(ExternalServer, "check_health", lambda self: phases.append(self.phase))
    agent = fake.behaviours["agent"]

    def agent_with_a_trip(spec, mounts):
        if len(servers) == 1:
            trip(servers[0], "trial t1-r1")
        return agent(spec, mounts)

    fake.behaviours["agent"] = agent_with_a_trip

    code = run(root, "--config", str(root / "c.toml"), "--config", str(root / "d.toml"))

    assert code == cli.GUARD_EXIT == 3
    dirs = run_dirs(root)
    info = json.loads((dirs["local-test"] / "run.json").read_text())
    assert info["memory_guard"] == TRIP
    assert info["memory_guard_lowest"] == LOWEST
    assert not (dirs["local-test"] / "t1-r1" / "result.json").exists()
    assert (dirs["other"] / "t1-r1" / "result.json").exists()
    assert "memory_guard" not in json.loads((dirs["other"] / "run.json").read_text())
    assert phases == ["start", "between trials", "start", "between trials"]
    message = (f"llm-eval: local-test: the memory guard stopped the run of this configuration. The trial in"
               f" progress has no result. To continue: llm-eval run --resume {dirs['local-test']}")
    assert message in capsys.readouterr().err
    assert message in (dirs["local-test"] / "run.log").read_text()

    assert run(root, "--resume", str(dirs["local-test"])) == 0

    assert (dirs["local-test"] / "t1-r1" / "result.json").exists()
    assert json.loads((dirs["local-test"] / "run.json").read_text())["memory_guard"] == TRIP


def test_memory_guard_during_the_probes(root, fake, servers, monkeypatch):
    monkeypatch.setattr(cli, "probe_run", lambda ctx, choice, targets: trip(ctx.server, "probes"))
    out = root / "o"

    assert run(root, "--config", str(root / "c.toml"), "--out", str(out), "--probe", "protocol") == 3

    assert json.loads((out / "run.json").read_text())["memory_guard"]["phase"] == "probes"
    assert not (out / "t1-r1").exists()


def test_memory_guard_before_run_json_tells_how_to_start_again(root, fake, servers, monkeypatch, capsys):
    monkeypatch.setattr(cli, "start_run", lambda ctx, *args, **kw: trip(ctx.server, "start"))
    out = root / "o"

    assert run(root, "--config", str(root / "c.toml"), "--out", str(out)) == 3

    assert not (out / "run.json").exists()
    assert f"To start it again: llm-eval run --config {root / 'c.toml'} --out {out}" in capsys.readouterr().err


def test_stop_signal_after_a_guard_trip_records_the_trip(root, fake, servers, monkeypatch, capsys):
    def interrupt(ctx, *args):
        ctx.server.guard = SimpleNamespace(trip=TRIP, lowest=LOWEST)
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "execute_run", interrupt)
    out = root / "o"

    assert run(root, "--config", str(root / "c.toml"), "--out", str(out)) == 130

    info = json.loads((out / "run.json").read_text())
    assert info["memory_guard"] == TRIP
    assert info["memory_guard_lowest"] == LOWEST
    assert f"interrupted. To continue: llm-eval run --resume {out}" in capsys.readouterr().err


def test_run_records_the_lowest_values_of_the_memory_guard_without_a_trip(root, fake, monkeypatch):
    def check_health(server):
        server.guard = SimpleNamespace(trip=None, lowest=LOWEST)

    monkeypatch.setattr(ExternalServer, "check_health", check_health)
    out = root / "o"

    assert run(root, "--config", str(root / "c.toml"), "--out", str(out)) == 0

    info = json.loads((out / "run.json").read_text())
    assert info["memory_guard_lowest"] == LOWEST
    assert "memory_guard" not in info
    assert (out / "t1-r1" / "result.json").exists()


def test_resume_replaces_the_lowest_values_of_the_memory_guard_and_keeps_the_trip(root, fake, servers, monkeypatch):
    agent = fake.behaviours["agent"]

    def agent_with_a_trip(spec, mounts):
        if len(servers) == 1:
            trip(servers[0], "trial t1-r1")
        return agent(spec, mounts)

    fake.behaviours["agent"] = agent_with_a_trip
    out = root / "o"
    assert run(root, "--config", str(root / "c.toml"), "--out", str(out)) == cli.GUARD_EXIT
    assert json.loads((out / "run.json").read_text())["memory_guard_lowest"] == LOWEST
    higher ={"gtt_margin": {**LOWEST["gtt_margin"], "mib": 50000}, "mem_available": None}

    def check_health(server):
        server.guard = SimpleNamespace(trip=None, lowest=higher)

    monkeypatch.setattr(ExternalServer, "check_health", check_health)

    assert run(root, "--resume", str(out)) == 0

    info = json.loads((out / "run.json").read_text())
    assert info["memory_guard"] == TRIP  # the trip of the first start
    assert info["memory_guard_lowest"] == higher  # the last start, also with higher values


def test_external_server_has_no_memory_guard(root, fake, servers):
    assert run(root, "--config", str(root / "c.toml"), "--out", str(root / "o")) == 0

    assert servers[0].guard is None
    assert "memory_guard_lowest" not in json.loads((root / "o" / "run.json").read_text())


def test_stop_signal_during_the_cleanup_of_a_guard_trip(root, fake, servers, monkeypatch, capsys):
    class SamplerWithAStopSignal(FakeSampler):
        def stop(self):
            os.kill(os.getpid(), signal.SIGHUP)  # the observers stop in the cleanup of the trip
            return super().stop()

    monkeypatch.setattr(cli, "MemorySampler", SamplerWithAStopSignal)
    fake.behaviours["agent"] = lambda spec, mounts: trip(servers[0], "trial t1-r1")
    out = root / "o"

    code = run(root, "--config", str(root / "c.toml"), "--out", str(out))

    assert code == 130
    assert json.loads((out / "run.json").read_text())["memory_guard"]["phase"] == "trial t1-r1"
    assert ("the memory guard stopped the run of this configuration. The trial in progress has no result."
            f" To continue: llm-eval run --resume {out}") in capsys.readouterr().err
