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


def test_unknown_mode_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="mode"):
        load_config(write(tmp_path, EXTERNAL.replace('"external"', '"other"')))


def test_missing_key_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="server.model"):
        load_config(write(tmp_path, EXTERNAL.replace('model = "test-model"', "")))


def test_unknown_key_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="colour"):
        load_config(write(tmp_path, EXTERNAL.replace("[client]", 'colour = "red"\n[client]')))


def test_repository_config_loads():
    root = Path(__file__).resolve().parents[1]

    cfg = load_config(root / "configs" / "qwen38-external.toml")

    assert cfg.server.model == "qwen3.8-flash-next"
    assert cfg.server.context_tokens == 131072


def test_base_tables_merge_key_by_key(tmp_path):
    write(tmp_path, EXTERNAL, "base.toml")
    (tmp_path / "variants").mkdir()
    variant = write(tmp_path / "variants", """
base = "../base.toml"
name = "variant"

[server]
context_tokens = 1000

[client.env]
EXTRA = "1"
""", "v.toml")

    cfg = load_config(variant)

    assert cfg.name == "variant"
    assert cfg.server.context_tokens == 1000
    assert cfg.server.model == "test-model"
    assert cfg.client.env == {"CLAUDE_CODE_ATTRIBUTION_HEADER": "0", "EXTRA": "1"}
    assert "base" not in cfg.raw


def test_base_lists_and_scalars_replace(tmp_path):
    write(tmp_path, EXTERNAL.replace("[client]", '[client]\nconfig_dir = "a"\n'), "base.toml")
    variant = write(tmp_path, 'base = "base.toml"\n[client]\nconfig_dir = "b"\n', "v.toml")

    assert load_config(variant).client.config_dir == "b"
    assert load_config(variant).raw["client"]["config_dir"] == "b"


def test_base_name_is_not_inherited(tmp_path):
    write(tmp_path, EXTERNAL, "base.toml")

    cfg = load_config(write(tmp_path, 'base = "base.toml"\n', "my-variant.toml"))

    assert cfg.name == "my-variant"


def test_base_bases_chain(tmp_path):
    write(tmp_path, EXTERNAL, "a.toml")
    write(tmp_path, 'base = "a.toml"\n[server]\ncontext_tokens = 1\n', "b.toml")

    cfg = load_config(write(tmp_path, 'base = "b.toml"\n[server]\nmodel = "x"\n', "c.toml"))

    assert (cfg.server.context_tokens, cfg.server.model) == (1, "x")


def test_sha256_is_of_the_merged_values(tmp_path):
    full = load_config(write(tmp_path, EXTERNAL.replace('name = "local-test"', 'name = "v"'), "full.toml"))
    write(tmp_path, EXTERNAL, "base.toml")

    variant = load_config(write(tmp_path, 'base = "base.toml"\nname = "v"\n', "v.toml"))

    assert variant.sha256 == full.sha256


def test_base_loop_is_an_error(tmp_path):
    write(tmp_path, 'base = "b.toml"\n', "a.toml")
    write(tmp_path, 'base = "a.toml"\n', "b.toml")

    with pytest.raises(ConfigError, match="files make a loop"):
        load_config(tmp_path / "a.toml")


def test_missing_file_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="no.toml: file not found"):
        load_config(write(tmp_path, 'base = "no.toml"\n' + EXTERNAL))
