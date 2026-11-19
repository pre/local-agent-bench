"""Read secret environment variables from a shell profile (client.secrets).

A bash process sources the profile and writes only the named values to a pipe.
The values are never in a process argument list or in a file of the harness.
"""

import os
import subprocess
from pathlib import Path

from .config import ConfigError, ProfileSecrets

# $1 is the profile, the other arguments are the names. The profile gets a
# small environment, so a value that the profile does not set cannot come from
# the shell of the user. Each value ends with a NUL byte.
READ_SCRIPT = """
source "$1" >/dev/null 2>&1
shift
for name; do
  [[ -v $name ]] || { printf '%s\\n' "$name" >&2; exit 3; }
done
for name; do printf '%s\\0' "${!name}"; done
"""


def read_profile_secrets(secrets: ProfileSecrets | None) -> dict[str, str]:
    if secrets is None:
        return {}
    if not secrets.from_profile.is_file():
        raise ConfigError(f"client.secrets.from_profile {secrets.from_profile}: file not found")
    proc = subprocess.run(
        ["bash", "-c", READ_SCRIPT, "read-secrets", str(secrets.from_profile), *secrets.names],
        stdin=subprocess.DEVNULL, capture_output=True,
        env={"HOME": str(Path.home()), "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )
    if proc.returncode != 0:
        raise ConfigError(f"{secrets.from_profile} does not set {proc.stderr.decode().strip()}")
    values = proc.stdout.decode().split("\0")[:-1]
    return dict(zip(secrets.names, values, strict=True))
