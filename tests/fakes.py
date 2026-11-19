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
        self.calls: list[list[str]] = []
        self.containers: dict[str, dict] = {}
        self.server_log = "llama-server log\n"
        self.server_runs = True  # False: a started server container stops at once
        self.run_exit_code = 0

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

    def call(self, args: list[str]) -> tuple[int, str]:
        """podman commands for a detached container (the managed server). The fake
        keeps the state of each container in self.containers."""
        self.calls.append(args)
        command, name = args[0], args[-1]
        if command == "run" and "-d" in args:
            name = args[args.index("--name") + 1]
            labels = dict(args[i + 1].split("=") for i, a in enumerate(args) if a == "--label")
            self.containers[name] = {"labels": labels, "running": self.server_runs}
            return self.run_exit_code, "containerid\n"
        if command == "run":
            return 0, "version: 1.0.0-dev (build 12531, commit e4b620af1)\nbuilt with GNU 16.2.1\n"
        if command == "ps":
            return 0, "".join(f"{n}  image  Up\n" for n in self.containers)
        if name not in self.containers:
            return 125, f"Error: no such container {name}\n"
        container = self.containers[name]
        if command == "container":  # container inspect
            info = {"Config": {"Labels": container["labels"]}, "ImageDigest": "sha256:serverdigest",
                    "State": {"Running": container["running"], "Status": "running" if container["running"] else "exited"}}
            return 0, json.dumps([info])
        if command == "logs":
            return 0, self.server_log
        if command in ("stop", "kill"):
            container["running"] = False
            return 0, ""
        if command == "rm":
            del self.containers[name]
            return 0, ""
        raise AssertionError(f"unexpected podman call {args}")

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
