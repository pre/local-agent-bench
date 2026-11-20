"""Run containers with rootless podman. Unit tests replace Podman with a fake."""

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

# The image user "eval" has UID 1000. keep-id maps it to the host user, so the
# files that a container writes in a bind mount belong to the host user.
USERNS = "--userns=keep-id:uid=1000,gid=1000"


@dataclass(frozen=True)
class Mount:
    host: Path
    container: str
    readonly: bool = False

    def arg(self) -> str:
        return f"{self.host}:{self.container}" + (":ro" if self.readonly else "")


@dataclass(frozen=True)
class ContainerSpec:
    name: str
    image: str
    command: list[str]
    mounts: list[Mount] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # Given to podman through its process environment, so the values are not in argv.
    secret_env: dict[str, str] = field(default_factory=dict)
    network: str = "none"
    workdir: str = "/work"


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    timed_out: bool
    seconds: float


def run_args(spec: ContainerSpec) -> list[str]:
    args = ["run", "--rm", "--name", spec.name, USERNS, f"--network={spec.network}", "--init"]
    args += ["--workdir", spec.workdir]
    for mount in spec.mounts:
        args += ["-v", mount.arg()]
    for key, value in spec.env.items():
        args += ["-e", f"{key}={value}"]
    for key in spec.secret_env:
        args += ["-e", key]
    return args + [spec.image] + spec.command


class Podman:
    def __init__(self, executable: str = "podman"):
        self.executable = executable

    def run(self, spec: ContainerSpec, stdout: Path, stderr: Path, timeout_s: float) -> RunResult:
        env = {**os.environ, **spec.secret_env}
        start = time.monotonic()
        with stdout.open("wb") as out, stderr.open("wb") as err:
            proc = subprocess.Popen(
                [self.executable, *run_args(spec)],
                stdin=subprocess.DEVNULL, stdout=out, stderr=err, env=env,
            )
            try:
                code = proc.wait(timeout=timeout_s)
                timed_out = False
            except subprocess.TimeoutExpired:
                subprocess.run([self.executable, "stop", "-t", "10", spec.name], capture_output=True)
                code = proc.wait()
                timed_out = True
            except BaseException:  # a stop signal: the container must not continue without the harness
                self.call(["rm", "-f", "-t", "10", "--ignore", spec.name])
                proc.wait()
                raise
        return RunResult(code, timed_out, time.monotonic() - start)

    def output(self, spec: ContainerSpec) -> str:
        proc = subprocess.run(
            [self.executable, *run_args(spec)], capture_output=True, text=True, check=True
        )
        return proc.stdout.strip()

    def call(self, args: list[str]) -> tuple[int, str]:
        """Run one podman command. Return the exit code and stdout with stderr.

        The command runs in its own process group: the SIGINT and SIGHUP that a
        terminal or tmux sends to the process group of the harness do not stop
        it, for example the stop of the server during the cleanup."""
        proc = subprocess.run([self.executable, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors="replace", process_group=0)
        return proc.returncode, proc.stdout

    def image_info(self, image: str) -> dict:
        proc = subprocess.run(
            [self.executable, "image", "inspect", image], capture_output=True, text=True, check=True
        )
        info = json.loads(proc.stdout)[0]
        return {
            "name": image,
            "id": info["Id"],
            "digest": info.get("Digest"),
            "labels": info.get("Labels") or {},
        }
