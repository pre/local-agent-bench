from pathlib import Path

import pytest

from llm_eval.config import ConfigError, load_config

EXTERNAL = """
name = "local-test"

[server]
mode = "external"
url = "http://127.0.0.1:8080"
api_key_file = "~/key"
model = "test-model"
context_tokens = 65536

[client]
[client.env]
CLAUDE_CODE_ATTRIBUTION_HEADER = "0"
"""


def write(tmp_path: Path, text: str, name: str = "c.toml") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_loads_external_server_and_client(tmp_path):
    cfg = load_config(write(tmp_path, EXTERNAL))

    assert cfg.name == "local-test"
    assert cfg.server.mode == "external"
    assert cfg.server.url == "http://127.0.0.1:8080"
    assert cfg.server.api_key_file == Path.home() / "key"
    assert cfg.server.model == "test-model"
    assert cfg.server.context_tokens == 65536
    assert cfg.server.agent_network == "proxy"
    assert cfg.server.health_path == "/health"
    assert cfg.client.image == "localhost/llm-eval-agent:latest"
    assert cfg.client.env == {"CLAUDE_CODE_ATTRIBUTION_HEADER": "0"}


def test_name_defaults_to_file_stem(tmp_path):
    cfg = load_config(write(tmp_path, EXTERNAL.replace('name = "local-test"', ""), "abc.toml"))

    assert cfg.name == "abc"


def test_sha256_changes_with_content(tmp_path):
    a = load_config(write(tmp_path, EXTERNAL, "a.toml"))
    b = load_config(write(tmp_path, EXTERNAL.replace("65536", "131072"), "b.toml"))

    assert len(a.sha256) == 64
    assert a.sha256 != b.sha256


def test_agent_url_is_required_for_a_podman_network(tmp_path):
    text = EXTERNAL.replace('model = "test-model"', 'model = "m"\nagent_network = "slirp4netns:allow_host_loopback=true"')

    with pytest.raises(ConfigError, match="agent_url"):
        load_config(write(tmp_path, text))


def test_agent_url_with_podman_network(tmp_path):
    text = EXTERNAL.replace(
        'model = "test-model"',
        'model = "m"\nagent_network = "container:srv"\nagent_url = "http://127.0.0.1:8080"',
    )

    cfg = load_config(write(tmp_path, text))

    assert cfg.server.agent_network == "container:srv"
    assert cfg.server.agent_url == "http://127.0.0.1:8080"


def test_managed_mode_is_not_implemented(tmp_path):
    with pytest.raises(ConfigError, match="managed"):
        load_config(write(tmp_path, EXTERNAL.replace('"external"', '"managed"')))


def test_unknown_mode_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="mode"):
        load_config(write(tmp_path, EXTERNAL.replace('"external"', '"other"')))


def test_missing_key_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="server.model"):
        load_config(write(tmp_path, EXTERNAL.replace('model = "test-model"', "")))


def test_unknown_key_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="colour"):
        load_config(write(tmp_path, EXTERNAL.replace("[client]", 'colour = "red"\n[client]')))


def test_base_key_is_not_implemented(tmp_path):
    with pytest.raises(ConfigError, match="base"):
        load_config(write(tmp_path, 'base = "other.toml"\n' + EXTERNAL))


def test_repository_config_loads():
    root = Path(__file__).resolve().parents[1]

    cfg = load_config(root / "configs" / "qwen38-external.toml")

    assert cfg.server.model == "qwen3.8-flash-next"
    assert cfg.server.context_tokens == 131072
