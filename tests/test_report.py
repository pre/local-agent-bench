import json

import pytest

from llm_eval.report import config_stats, load_run, render_report, sign_test, wilson
from runfiles import SHA_A, SHA_B, memory, server, trial, write_run


def test_wilson_interval():
    assert wilson(0, 0) == (0.0, 1.0)
    lo, hi = wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4)
    assert hi == pytest.approx(0.7634, abs=1e-4)
    lo, hi = wilson(10, 10)
    assert lo == pytest.approx(0.7225, abs=1e-4)
    assert hi == pytest.approx(1.0)


def test_sign_test_is_two_sided_and_exact():
    assert sign_test(0, 0) == 1.0
    assert sign_test(5, 0) == pytest.approx(0.0625)
    assert sign_test(0, 6) == pytest.approx(0.03125)
    assert sign_test(3, 1) == pytest.approx(0.625)


def test_load_run_complete(tmp_path):
    run = load_run(write_run(tmp_path / "r1", [trial("t1"), trial("t2")]))

    assert len(run.results) == 2
    assert run.expected == 2
    assert not run.partial


def test_load_run_partial_when_not_finished(tmp_path):
    run = load_run(write_run(tmp_path / "r1", [trial("t1")], finished=False))

    assert run.partial


def test_load_run_partial_when_results_are_missing(tmp_path):
    run = load_run(write_run(tmp_path / "r1", [trial("t1")], tasks=["t1", "t2"], reps=2))

    assert run.expected == 4
    assert run.partial


def test_load_run_reads_probes(tmp_path):
    run_dir = write_run(tmp_path / "r1", [trial("t1")])
    (run_dir / "probes").mkdir()
    (run_dir / "probes" / "speed.json").write_text('{"results": []}')

    assert load_run(run_dir).probes == {"speed": {"results": []}}


def test_load_run_without_run_json(tmp_path):
    run = load_run(tmp_path)

    assert run.results == []
    assert not run.partial
    assert "no run.json, 0 trials" in render_report([run])


def test_harness_errors_are_not_in_pass_rate_or_score(tmp_path):
    trials = [trial("t1"), trial("t2", passed=False, score=0.5),
              trial("t3", passed=False, reason="harness_error", wall=5.0)]

    (stats,) = config_stats([load_run(write_run(tmp_path / "r", trials))])

    assert (stats.passes, stats.n, stats.harness_errors) == (1, 2, 1)
    assert stats.mean_score == pytest.approx(0.75)
    assert stats.median_wall == 100.0
    assert stats.total_wall == 205.0
    assert stats.failures == {"verify_failed": 1}


def test_harness_error_without_wall_time_and_turns(tmp_path):
    # The harness writes null for these values when a trial raises before the agent runs.
    trials = [trial("t1", wall=40.0),
              trial("t2", passed=False, reason="harness_error", wall=None, turns=None)]

    run = load_run(write_run(tmp_path / "r", trials))
    (stats,) = config_stats([run])

    assert stats.total_wall == 40.0
    assert stats.median_wall == 40.0
    assert "harness" in render_report([run])


def test_rates_come_from_summed_tokens_and_seconds(tmp_path):
    trials = [trial("t1", server=server(1000, 10.0, 100, 2.0, 60, 100)),
              trial("t2", server=server(100, 2.0, 300, 20.0, 10, 100)),
              trial("t3", server=None)]

    (stats,) = config_stats([load_run(write_run(tmp_path / "r", trials))])

    assert stats.prompt_tps == pytest.approx(1100 / 12)
    assert stats.decode_tps == pytest.approx(400 / 22)
    assert stats.draft_acceptance == pytest.approx(0.35)


def test_rates_are_none_without_server_values(tmp_path):
    (stats,) = config_stats([load_run(write_run(tmp_path / "r", [trial("t1")]))])

    assert stats.prompt_tps is None
    assert stats.draft_acceptance is None
    assert stats.gtt_peak_mib is None


def test_memory_is_peak_of_peaks_and_minimum_of_minimums(tmp_path):
    trials = [trial("t1", memory=memory(70000, 40000, 8000)), trial("t2", memory=memory(75000, 30000, 8100)),
              trial("t3")]

    (stats,) = config_stats([load_run(write_run(tmp_path / "r", trials))])

    assert (stats.gtt_peak_mib, stats.mem_available_min_mib, stats.swap_free_min_mib) == (75000, 30000, 8000)


def test_same_name_with_other_sha_is_another_row(tmp_path):
    a = load_run(write_run(tmp_path / "a", [trial("t1", sha=SHA_A)]))
    b = load_run(write_run(tmp_path / "b", [trial("t1", sha=SHA_B, passed=False)]))

    rows = config_stats([a, b])

    assert [r.label for r in rows] == ["c1 @aaaaaaaa", "c1 @bbbbbbbb"]


def test_rows_sort_by_pass_rate_then_median_wall(tmp_path):
    runs = [
        load_run(write_run(tmp_path / "slow", [trial("t1", name="slow", wall=300.0)])),
        load_run(write_run(tmp_path / "bad", [trial("t1", name="bad", passed=False, wall=10.0)])),
        load_run(write_run(tmp_path / "fast", [trial("t1", name="fast", wall=50.0)])),
    ]

    assert [r.label for r in config_stats(runs)] == ["fast", "slow", "bad"]


@pytest.fixture
def two_configs(tmp_path):
    a = [trial("t1", r, wall=100.0 + r, server=server(20000, 60.0, 3000, 100.0, 600, 1000),
               memory=memory(76800, 40960, 8192)) for r in (1, 2, 3)]
    a += [trial("t2", 1), trial("t2", 2, passed=False, score=0.5, failed_checks=("order",), turns=33),
          trial("t2", 3, passed=False, reason="harness_error")]
    b = [trial("t1", r, name="c2", sha=SHA_B, passed=r == 1, reason="timeout", wall=1800.0) for r in (1, 2, 3)]
    b += [trial("t2", r, name="c2", sha=SHA_B, passed=False, score=0.0) for r in (1, 2)]
    return [load_run(write_run(tmp_path / "run-a", a, reps=3)),
            load_run(write_run(tmp_path / "run-b", b, reps=3, finished=False))]


def test_report_tables(two_configs):
    text = render_report(two_configs)

    assert "## Configurations" in text
    row = next(line for line in text.splitlines() if line.startswith("| c1 "))
    assert "4/5" in row and "80 %" in row
    assert "333.3" in row  # prompt tok/s: 60000 tokens in 180 s
    assert "30.0" in row  # decode tok/s
    assert "0.60" in row  # draft acceptance
    assert "75.0" in row and "40.0" in row and "8.0" in row  # GiB
    assert "verify_failed 1" in row
    assert row.rstrip(" |").endswith("1")  # harness errors
    assert "| t1 | 3/3 | 1/3 |" in text
    assert "| t2 | 1/2, score 0.75, 1 harness error | 0/2 |" in text


def test_report_lists_failed_trials(two_configs):
    text = render_report(two_configs)

    assert "| run-a | t2 | 2 | verify_failed | 0.50 | order | 33 | 100.0 |" in text
    assert "| run-a | t2 | 3 | harness_error | n/a | - | 10 | 100.0 |" in text
    assert "timeout" in text


def config_row(text: str, label: str) -> dict[str, str]:
    section = text.split("## Configurations", 1)[1].split("\n## ", 1)[0]
    lines = [line for line in section.splitlines() if line.startswith("| ")]
    header = [cell.strip() for cell in lines[0].strip("|").split("|")]
    row = next(line for line in lines if line.startswith(f"| {label} |"))
    return dict(zip(header, (cell.strip() for cell in row.strip("|").split("|"))))


def test_base_and_hard_pass_come_from_the_hard_flag_of_the_trials(tmp_path):
    trials = [trial("t1"), trial("t2", passed=False), trial("t3", hard=True),
              trial("hard-old", passed=False),  # no "hard" key: the ID decides
              trial("hard-new", hard=False),
              trial("hard-err", passed=False, reason="harness_error")]

    row = config_row(render_report([load_run(write_run(tmp_path / "r", trials))]), "c1")

    assert row["Pass rate (95 % interval)"].startswith("3/5,")
    assert (row["Base pass"], row["Hard pass"]) == ("2/3", "1/2")


def test_base_and_hard_pass_without_trials_of_a_tier(tmp_path):
    row = config_row(render_report([load_run(write_run(tmp_path / "r", [trial("t1")]))]), "c1")

    assert (row["Base pass"], row["Hard pass"]) == ("1/1", "-")


def test_report_marks_partial_runs_and_limits(two_configs):
    text = render_report(two_configs)

    assert "run-b" in text and "PARTIAL" in text
    assert "5 of 6 trials" in text
    limits = text.split("## Limits", 1)[1]
    assert "c1: 5 trials" in limits
    assert "percentage points" in limits


def test_report_marks_configuration_names_with_two_sha_values(tmp_path):
    a = load_run(write_run(tmp_path / "a", [trial("t1", sha=SHA_A)]))
    b = load_run(write_run(tmp_path / "b", [trial("t1", sha=SHA_B)]))

    assert "has 2 different SHA-256 values" in render_report([a, b])


def test_report_of_the_sample_shape_without_observers(tmp_path):
    run = load_run(write_run(tmp_path / "r", [trial("go-bugfix", wall=878.4)]))

    text = render_report([run])

    assert "| go-bugfix | 1/1 |" in text
    assert "No failed trials." in text
    assert "n/a" in text


def test_report_adds_probe_section(tmp_path):
    run_dir = write_run(tmp_path / "r", [trial("t1")])
    (run_dir / "probes").mkdir()
    speed = {"model": "m", "decode_tokens": 256, "results": [
        {"target_tokens": 1000, "prompt_tokens": 1012, "cache_tokens": 3, "prompt_seconds": 3.1, "prompt_tps": 326.5,
         "decode_tokens": 256, "decode_seconds": 9.0, "decode_tps": 28.4, "ttft_s": 3.3, "draft_acceptance": 0.7,
         "error": None}],
        "skipped": [{"target_tokens": 120000, "reason": "above --max-context 30000"}]}
    protocol = {"model": "m", "cases": [
        {"name": "plain", "http_status": 200, "passed": True, "note": "text 4 chars", "error": None},
        {"name": "system_in_middle", "http_status": 500, "passed": False, "note": "",
         "error": "System message must be at the beginning"}]}
    (run_dir / "probes" / "speed.json").write_text(json.dumps(speed))
    (run_dir / "probes" / "protocol.json").write_text(json.dumps(protocol))

    text = render_report([load_run(run_dir)])

    assert "## Probes" in text
    assert "| 1000 | 1012 | 3 | 3.1 | 326.5 | 256 | 9.0 | 28.4 | 3.3 | 0.70 |" in text
    assert "120000" in text and "above --max-context" in text
    assert "| system_in_middle | 500 | FAIL |" in text
    assert "1 of 2 cases pass" in text


def test_report_of_a_probe_directory_only(tmp_path):
    (tmp_path / "probes").mkdir()
    (tmp_path / "probes" / "protocol.json").write_text(json.dumps({"model": "m", "cases": []}))

    text = render_report([load_run(tmp_path)])

    assert "No trial results." in text
    assert "## Probes" in text


MANAGED = {"mode": "managed", "gtt_used_before_start_mib": 2048, "gtt_used_after_load_mib": 81920,
           "gtt_used_load_peak_mib": 82944, "gtt_total_mib": 112640}


def memory_row(text: str, label: str) -> list[str]:
    section = text.split("## Memory", 1)[1].split("\n## ", 1)[0]
    line = next(line for line in section.splitlines() if line.startswith(f"| {label} |"))
    return [cell.strip() for cell in line.strip("|").split("|")][1:]


def test_gtt_peak_includes_the_probes_and_the_server_start(tmp_path):
    trials = [trial("t1", memory=memory(84000, 30000, 8000))]
    probed = load_run(write_run(tmp_path / "a", trials, server=MANAGED,
                                probe_memory=memory(90000, 20000, 7000, psi_full=2.5)))
    loaded = load_run(write_run(tmp_path / "b", [trial("t1", name="c2", sha=SHA_B)],
                                server={**MANAGED, "gtt_used_load_peak_mib": 95000}))

    a, b = sorted(config_stats([probed, loaded]), key=lambda s: s.label)

    assert (a.gtt_peak_mib, a.mem_available_min_mib, a.swap_free_min_mib, a.psi_full_max) == (90000, 20000, 7000, 2.5)
    assert b.gtt_peak_mib == 95000


def test_memory_section_of_a_managed_run(tmp_path):
    trials = [trial("t1", memory=memory(83968, 30720, 8192, psi_full=1.25))]
    run = load_run(write_run(tmp_path / "r", trials, server=MANAGED, probe_memory=memory(86016, 40960, 9216)))

    text = render_report([run])

    assert text.index("## Configurations") < text.index("## Memory") < text.index("## Tasks")
    assert memory_row(text, "c1") == ["110.0", "2.0", "80.0", "84.0", "82.0", "26.0", "30.0", "8.0", "1.25"]
    assert "on the machine of the run" in text
    assert "## Probes" not in text
    assert "| c1 | 1 |" in text and "| 84.0 |" in text.split("## Memory")[0]


def test_memory_section_of_an_old_run_uses_the_first_trial(tmp_path):
    trials = [trial("t1", memory=memory(88162, 16809, 569, gtt_start=88068), started="2026-11-19T20:06:17+00:00"),
              trial("t2", memory=memory(88073, 27195, 2000, gtt_start=87794), started="2026-11-19T18:45:02+00:00")]
    old = {"mode": "managed", "gtt_used_before_start_mib": 2441}

    text = render_report([load_run(write_run(tmp_path / "r", trials, server=old))])

    assert memory_row(text, "c1")[:6] == ["n/a", "2.4", "85.7", "86.1", "83.7", "n/a"]
    assert "first trial" in text


def test_memory_section_of_an_external_server(tmp_path):
    trials = [trial("t1", memory=memory(51200, 30720, 8192, gtt_start=50176))]
    external = {"mode": "external", "url": "http://127.0.0.1:8080", "container": None, "gtt_total_mib": 112640}

    text = render_report([load_run(write_run(tmp_path / "r", trials, server=external))])

    assert memory_row(text, "c1")[:6] == ["110.0", "n/a", "49.0", "50.0", "n/a", "60.0"]
    assert "external server" in text


def test_remote_configuration_has_no_gtt_values(tmp_path):
    trials = [trial("t1", memory=memory(88064, 30720, 8192))]
    remote = {"mode": "remote", "url": "https://gateway.example.org", "model": "m", "agent_network": "proxy"}

    run = load_run(write_run(tmp_path / "r", trials, server=remote))
    (stats,) = config_stats([run])
    text = render_report([run])

    assert stats.gtt_peak_mib is None
    assert memory_row(text, "c1") == ["n/a"] * 6 + ["30.0", "8.0", "0.10"]
    config_row = next(line for line in text.splitlines() if line.startswith("| c1 | 1 |"))
    assert "86.0" not in config_row and "| n/a | 30.0 | 8.0 |" in config_row
    assert "does not use the local GPU memory" in text


def test_cost_is_the_sum_of_the_trials_of_a_remote_configuration(tmp_path):
    trials = [{**trial("t1"), "total_cost_usd": 0.42}, {**trial("t2", passed=False), "total_cost_usd": 0.1},
              {**trial("t3", passed=False, reason="harness_error"), "total_cost_usd": None}]
    remote = {"mode": "remote", "url": "https://gateway.example.org", "model": "m", "agent_network": "proxy"}

    row = config_row(render_report([load_run(write_run(tmp_path / "r", trials, server=remote))]), "c1")

    assert row["Cost USD"] == "0.52"


def test_cost_of_a_local_configuration_is_not_available(tmp_path):
    trials = [{**trial("t1"), "total_cost_usd": 0.42}]  # the estimate of Claude Code has no meaning for a local server

    row = config_row(render_report([load_run(write_run(tmp_path / "r", trials, server=MANAGED))]), "c1")

    assert row["Cost USD"] == "n/a"


def test_runs_list_the_reported_models_of_a_remote_run(tmp_path):
    remote = {"mode": "remote", "url": "https://gateway.example.org", "model": "Claude-Test-1"}
    remote_dir = write_run(tmp_path / "remote", [trial("t1")], server=remote)
    info = json.loads((remote_dir / "run.json").read_text())
    (remote_dir / "run.json").write_text(json.dumps({**info, "reported_models": ["claude-test-1", "other"]}))
    local = write_run(tmp_path / "local", [trial("t1", name="c2", sha=SHA_B)], server=MANAGED)

    runs = render_report([load_run(remote_dir), load_run(local)]).split("## Runs", 1)[1].split("\n## ", 1)[0]

    assert "- `remote` (c1): 1 of 1 trial, started 2026-11-19T10:00:00+00:00, finished 2026-11-19T11:00:00+00:00," \
           " reported models claude-test-1, other" in runs
    assert "reported models" not in next(line for line in runs.splitlines() if "`local`" in line)


def test_merged_runs_take_before_and_after_from_the_run_with_the_highest_peak(tmp_path):
    low = load_run(write_run(tmp_path / "a", [trial("t1", memory=memory(83968, 30720, 8192))], server=MANAGED))
    high_server = {**MANAGED, "gtt_used_before_start_mib": 4096, "gtt_used_after_load_mib": 86016,
                   "gtt_total_mib": 102400}
    high = load_run(write_run(tmp_path / "b", [trial("t2", memory=memory(88064, 20480, 4096))], server=high_server))

    text = render_report([low, high])

    assert memory_row(text, "c1") == ["110.0", "4.0", "84.0", "86.0", "82.0", "14.0", "20.0", "4.0", "0.10"]
    assert "highest GTT peak" in text


def test_memory_section_without_memory_values(tmp_path):
    text = render_report([load_run(write_run(tmp_path / "r", [trial("t1")]))])

    assert memory_row(text, "c1") == ["n/a"] * 9
