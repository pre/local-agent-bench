from pathlib import Path

import pytest

from llm_eval.config import ConfigError, ProfileSecrets
from llm_eval.profile_secrets import read_profile_secrets

PROFILE = """\
# A shell profile like the one of Claude Code for the gateway.
echo "the profile writes to stdout"
export ANTHROPIC_API_KEY="key-1"
export ANTHROPIC_CUSTOM_HEADERS="Sub-Key: abc 123"
export EMPTY=""
OTHER="$ANTHROPIC_API_KEY-other"
"""


def profile(tmp_path: Path, text: str = PROFILE) -> Path:
    path = tmp_path / "profile.sh"
    path.write_text(text)
    return path


def test_reads_the_named_values(tmp_path):
    secrets = ProfileSecrets(profile(tmp_path), ("ANTHROPIC_API_KEY", "ANTHROPIC_CUSTOM_HEADERS", "OTHER", "EMPTY"))

    assert read_profile_secrets(secrets) == {
        "ANTHROPIC_API_KEY": "key-1",
        "ANTHROPIC_CUSTOM_HEADERS": "Sub-Key: abc 123",
        "OTHER": "key-1-other",
        "EMPTY": "",
    }


def test_no_secrets_gives_an_empty_dict():
    assert read_profile_secrets(None) == {}


def test_missing_name_is_an_error(tmp_path):
    secrets = ProfileSecrets(profile(tmp_path), ("ANTHROPIC_API_KEY", "NOT_SET"))

    with pytest.raises(ConfigError, match="does not set NOT_SET") as e:
        read_profile_secrets(secrets)
    assert "key-1" not in str(e.value)


def test_missing_profile_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        read_profile_secrets(ProfileSecrets(tmp_path / "none.sh", ("A",)))
