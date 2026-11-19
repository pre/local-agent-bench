import json

from llm_eval.metrics import ServerLogObserver, parse_timings

LOG = """\
0.26.626.143 I srv  server_run_i: model loaded
1.51.986.333 I slot print_timing: id  0 | task 0 | prompt processing, n_tokens =  23304, progress = 1.00, t =  73.34 s / 317.74 tokens per second
1.56.042.503 I slot print_timing: id  0 | task 0 | n_gen =    102, tg =  26.21 t/s, tg_3s =  26.46 t/s
1.57.413.625 I slot print_timing: id  0 | task 0 | prompt eval time =   75419.91 ms / 23308 tokens (    3.24 ms per token,   309.04 tokens per second)
1.57.413.633 I slot print_timing: id  0 | task 0 |        eval time =    5225.27 ms /   134 tokens (   39.29 ms per token,    25.45 tokens per second)
1.57.413.635 I slot print_timing: id  0 | task 0 |       total time =   80645.18 ms / 23442 tokens
1.57.413.655 I slot print_timing: id  0 | task 0 | draft acceptance = 0.60993 (   86 accepted /   141 generated), mean len =  2.83
2.41.931.955 I slot print_timing: id  0 | task 63 | prompt eval time =     580.09 ms /   92 tokens (    6.31 ms per token,   158.60 tokens per second)
2.41.931.965 I slot print_timing: id  0 | task 63 |        eval time =    3992.48 ms /   130 tokens (   30.95 ms per token,    32.31 tokens per second)
2.41.931.981 I slot print_timing: id  0 | task 63 | draft acceptance = 0.79825 (   91 accepted /   114 generated), mean len =  3.39
"""


def test_parse_timings_sums_all_requests():
    timings = parse_timings(LOG)

    assert timings == {
        "requests": 2,
        "prompt_tokens": 23400,
        "prompt_seconds": 76.0,
        "prompt_tps": 307.89,
        "decode_tokens": 264,
        "decode_seconds": 9.218,
        "decode_tps": 28.64,
        "draft_accepted": 177,
        "draft_generated": 255,
        "draft_acceptance": 0.6941,
    }


def test_parse_timings_without_draft_and_without_requests():
    no_draft = "\n".join(line for line in LOG.splitlines() if "draft" not in line)

    assert parse_timings(no_draft)["draft_accepted"] is None
    assert parse_timings(no_draft)["draft_acceptance"] is None
    assert parse_timings("") == {
        "requests": 0, "prompt_tokens": 0, "prompt_seconds": 0.0, "prompt_tps": None,
        "decode_tokens": 0, "decode_seconds": 0.0, "decode_tps": None,
        "draft_accepted": None, "draft_generated": None, "draft_acceptance": None,
    }


class FakeLogs:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def call(self, args):
        self.calls.append(args)
        return 0, self.text


def test_observer_saves_the_log_of_the_trial(tmp_path):
    podman = FakeLogs(LOG)
    observer = ServerLogObserver(podman, "llama-x")

    observer.start(tmp_path)
    timings = observer.stop()

    assert observer.name == "server"
    assert timings["requests"] == 2
    assert (tmp_path / "server.log").read_text() == LOG
    ((cmd, flag, since, name),) = podman.calls
    assert (cmd, flag, name) == ("logs", "--since", "llama-x")
    assert since.endswith("Z") and "T" in since
    json.dumps(timings)
