"""Fakes for podman. A fake container is a Python function that gets the host paths of its mounts."""

import json
from collections.abc import Callable
from pathlib import Path

from llm_eval.podman import ContainerSpec, RunResult

Behaviour = Callable[[ContainerSpec, dict[str, Path]], tuple[int, str]]


def mounts(spec: ContainerSpec) -> dict[str, Path]:
    return {m.container: m.host for m in spec.mounts}


def kind(spec: ContainerSpec) -> str:
    """The second part of the container name: agent, check, diff, solution or version."""
    return spec.name.split("-")[2]


class FakePodman:
    def __init__(self, **behaviours: Behaviour):
        self.behaviours = behaviours
        self.specs: list[ContainerSpec] = []
        self.timeouts: list[float] = []
        self.outputs: list[ContainerSpec] = []

    def run(self, spec: ContainerSpec, stdout: Path, stderr: Path, timeout_s: float) -> RunResult:
        self.specs.append(spec)
        self.timeouts.append(timeout_s)
        behaviour = self.behaviours.get(kind(spec), lambda s, m: (0, ""))
        code, out = behaviour(spec, mounts(spec))
        stdout.write_text(out)
        stderr.write_text(f"stderr of {spec.name}\n")
        if code == "timeout":
            return RunResult(137, True, timeout_s)
        return RunResult(code, False, 1.5)

    def output(self, spec: ContainerSpec) -> str:
        self.outputs.append(spec)
        return "2.1.328 (Claude Code)"

    def image_info(self, image: str) -> dict:
        return {"name": image, "id": "imageid", "digest": "sha256:digest", "labels": {}}

    def of_kind(self, name: str) -> list[ContainerSpec]:
        return [s for s in self.specs if kind(s) == name]


def write_verify(out_dir: Path, passed: bool) -> None:
    checks = [{"name": "a", "passed": True}, {"name": "b", "passed": passed}]
    data = {"passed": passed, "score": 1.0 if passed else 0.5, "checks": checks}
    (out_dir / "verify.json").write_text(json.dumps(data))


def check_by_marker(marker: str = "fixed.txt") -> Behaviour:
    """A check that passes when the file `marker` exists in /work."""

    def behaviour(spec: ContainerSpec, m: dict[str, Path]) -> tuple[int, str]:
        write_verify(m["/out"], (m["/work"] / marker).exists())
        return 0, "check output\n"

    return behaviour
