"""A fake podman command for the tests that start llm-eval as a process.

The directory $FAKE_PODMAN_DIR holds calls.jsonl, with a "start" line and an
"end" line for each call, and containers/<name>.json for each container that
exists. A podman command that a signal kills has no "end" line.

The fake sets SIGINT, SIGTERM and SIGHUP to the default action, so that a signal
kills it also when the harness ignores the signal. Real podman can do the same,
because the Go runtime can install its own handlers.

- run -d: a detached server container. It runs until stop, kill or rm.
- run --rm with an agent container: it runs until stop or rm, or until
  $FAKE_PODMAN_AGENT_S seconds (default 60).
- run --rm with a check container: verify.json passes when /work/fixed.txt exists.
- stop, and rm -f of a running container, take $FAKE_PODMAN_STOP_S seconds (default 0).
"""

import json
import os
import signal
import sys
import time
from pathlib import Path

for _signal in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(_signal, signal.SIG_DFL)

STATE = Path(os.environ["FAKE_PODMAN_DIR"])
CONTAINERS = STATE / "containers"
STOP_S = float(os.environ.get("FAKE_PODMAN_STOP_S", "0"))
AGENT_S = float(os.environ.get("FAKE_PODMAN_AGENT_S", "60"))


def record(event: str, args: list[str], **extra) -> None:
    line = json.dumps({"event": event, "argv": args, "pid": os.getpid(), "ppid": os.getppid(), "pgid": os.getpgid(0), **extra})
    with (STATE / "calls.jsonl").open("a") as f:
        f.write(line + "\n")


def path_of(name: str) -> Path:
    return CONTAINERS / f"{name}.json"


def load(name: str) -> dict | None:
    path = path_of(name)
    return json.loads(path.read_text()) if path.exists() else None


def save(name: str, state: dict) -> None:
    CONTAINERS.mkdir(parents=True, exist_ok=True)
    path_of(name).write_text(json.dumps(state))


def missing(name: str) -> int:
    print(f"Error: no such container {name}", file=sys.stderr)
    return 125


def option(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args else None


def run(args: list[str]) -> int:
    name = option(args, "--name")
    if name is None:  # llama-server --version
        print("version: 1.0.0-dev (build 12531, commit e4b620af1)")
        return 0
    if "-d" in args:
        labels = dict(args[i + 1].split("=") for i, a in enumerate(args) if a == "--label")
        save(name, {"labels": labels, "running": True})
        print("containerid")
        return 0
    mounts = dict(reversed(args[i + 1].removesuffix(":ro").split(":")) for i, a in enumerate(args) if a == "-v")
    kind = name.split("-")[2]
    if kind == "check":
        passed = (Path(mounts["/work"]) / "fixed.txt").exists()
        checks = [{"name": "fixed", "passed": passed}]
        (Path(mounts["/out"]) / "verify.json").write_text(json.dumps(
            {"passed": passed, "score": 1.0 if passed else 0.0, "checks": checks}))
    elif kind == "agent":
        save(name, {"labels": {}, "running": True})
        deadline = time.monotonic() + AGENT_S
        while (load(name) or {}).get("running") and time.monotonic() < deadline:
            time.sleep(0.05)
        path_of(name).unlink(missing_ok=True)
    elif kind == "version":
        print("2.1.328 (Claude Code)")
    return 0


def stop(name: str) -> int:
    state = load(name)
    if state is None:
        return missing(name)
    time.sleep(STOP_S)
    save(name, {**state, "running": False})
    return 0


def main(args: list[str]) -> int:
    command, name = args[0], args[-1]
    if command == "image":
        print(json.dumps([{"Id": "imageid", "Digest": "sha256:digest", "Labels": {}}]))
        return 0
    if command == "run":
        return run(args)
    if command == "ps":
        return 0
    state = load(name)
    if command == "container":  # container inspect
        if state is None:
            return missing(name)
        status = {"Running": state["running"], "Status": "running" if state["running"] else "exited"}
        print(json.dumps([{"Config": {"Labels": state["labels"]}, "ImageDigest": "sha256:serverdigest",
                           "State": status}]))
        return 0
    if command == "logs":
        if state is None:
            return missing(name)
        print("fake llama-server log")
        return 0
    if command == "stop":
        return stop(name)
    if command == "kill":
        if state is None:
            return missing(name)
        save(name, {**state, "running": False})
        return 0
    if command == "rm":
        if state is None:
            return 0 if "--ignore" in args else missing(name)
        if state["running"]:
            if "-f" not in args:
                print(f"Error: container {name} is running", file=sys.stderr)
                return 2
            stop(name)
        path_of(name).unlink(missing_ok=True)  # the fake agent can remove it first
        return 0
    print(f"fake podman: unknown command {args}", file=sys.stderr)
    return 125


if __name__ == "__main__":
    argv = sys.argv[1:]
    record("start", argv)
    code = main(argv)
    record("end", argv, code=code)
    sys.exit(code)
