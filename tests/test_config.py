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


MANAGED = """
name = "managed-test"

[server]
mode = "managed"
image = "example.org/llama@sha256:abc"
models_dir = "~/models/m"
model_file = "q4/m-00001-of-00002.gguf"
model = "m"
context_tokens = 4096
api_key_file = "~/key"
port = 8091

[server.args]
-ngl = 999
--jinja = true
--temp = 0.6

[client]
"""


def test_loads_managed_server(tmp_path):
    cfg = load_config(write(tmp_path, MANAGED))

    server = cfg.server
    assert server.mode == "managed"
    assert server.url == "http://127.0.0.1:8091"
    assert server.container == "llm-eval-server"
    assert server.model == "m"
    managed = server.managed
    assert managed.image == "example.org/llama@sha256:abc"
    assert managed.models_dir == Path.home() / "models" / "m"
    assert managed.model_file == "q4/m-00001-of-00002.gguf"
    assert managed.port == 8091
    assert managed.args == {"-ngl": 999, "--jinja": True, "--temp": 0.6}
    assert managed.draft is None
    assert managed.chat_template is None
    assert managed.gtt_max_used_mib == 12288
    assert managed.start_timeout_s == 900
    assert managed.gtt_min_margin_mib == 4096
    assert managed.mem_available_min_mib == 2048


@pytest.mark.parametrize("value", [0, 4096])
def test_mem_available_min_comes_from_the_configuration(tmp_path, value):
    text = MANAGED.replace("port = 8091", f"port = 8091\nmem_available_min_mib = {value}")

    assert load_config(write(tmp_path, text)).server.managed.mem_available_min_mib == value


@pytest.mark.parametrize("key", ["gtt_max_used_mib", "gtt_min_margin_mib", "mem_available_min_mib"])
@pytest.mark.parametrize("value", ['"2048"', "true", "2048.0"])
def test_memory_limits_must_be_integers(tmp_path, key, value):
    text = MANAGED.replace("port = 8091", f"port = 8091\n{key} = {value}")

    with pytest.raises(ConfigError, match=f"server.{key} must be an integer"):
        load_config(write(tmp_path, text))


def test_managed_draft_and_template(tmp_path):
    text = MANAGED.replace("[server.args]", """
chat_template = "templates/t.jinja"
gtt_max_used_mib = 100000

[server.args]""").replace("[client]", """
[server.draft]
model_file = "mtp/d.gguf"
args = { --spec-type = "draft-mtp" }

[client]
""").replace("port = 8091\n", "port = 8091\nstart_timeout_s = 60\n")

    managed = load_config(write(tmp_path, text)).server.managed

    assert managed.draft.model_file == "mtp/d.gguf"
    assert managed.draft.args == {"--spec-type": "draft-mtp"}
    assert managed.chat_template == "templates/t.jinja"
    assert managed.gtt_max_used_mib == 100000
    assert managed.start_timeout_s == 60


def test_empty_draft_model_file_means_no_draft(tmp_path):
    write(tmp_path, MANAGED.replace("[client]", '[server.draft]\nmodel_file = "d.gguf"\n[client]'), "base.toml")

    cfg = load_config(write(tmp_path, 'base = "base.toml"\n[server.draft]\nmodel_file = ""\n', "v.toml"))

    assert cfg.server.managed.draft is None


def test_managed_image_must_be_pinned(tmp_path):
    with pytest.raises(ConfigError, match="digest"):
        load_config(write(tmp_path, MANAGED.replace("@sha256:abc", ":latest")))


@pytest.mark.parametrize("flag", ["-c", "--port", "-m", "--alias", "--chat-template-file", "-md"])
def test_managed_args_cannot_set_harness_flags(tmp_path, flag):
    with pytest.raises(ConfigError, match=f"the harness sets {flag}"):
        load_config(write(tmp_path, MANAGED.replace("-ngl = 999", f'{flag} = "x"')))


@pytest.mark.parametrize("path", ["/etc/t.jinja", "other/t.jinja", "templates/../x.jinja"])
def test_chat_template_must_be_below_templates(tmp_path, path):
    with pytest.raises(ConfigError, match="templates/"):
        load_config(write(tmp_path, MANAGED.replace("[server.args]", f'chat_template = "{path}"\n[server.args]')))


def test_managed_keys_are_not_allowed_for_external(tmp_path):
    with pytest.raises(ConfigError, match="server.image"):
        load_config(write(tmp_path, EXTERNAL.replace('mode = "external"', 'mode = "external"\nimage = "x"')))


def test_external_url_is_not_allowed_for_managed(tmp_path):
    with pytest.raises(ConfigError, match="server.url"):
        load_config(write(tmp_path, MANAGED.replace('mode = "managed"', 'mode = "managed"\nurl = "http://x"')))


def test_external_container(tmp_path):
    text = EXTERNAL.replace('mode = "external"', 'mode = "external"\ncontainer = "llama-x"')

    cfg = load_config(write(tmp_path, text))

    assert cfg.server.container == "llama-x"
    assert cfg.server.managed is None
    assert load_config(write(tmp_path, EXTERNAL, "e.toml")).server.container is None


REMOTE = """
name = "remote-test"

[server]
mode = "remote"
url = "https://gateway.example.org/api"
model = "Claude-Test-1"

[client]
[client.secrets]
from_profile = "~/profile.sh"
names = ["ANTHROPIC_API_KEY", "ANTHROPIC_CUSTOM_HEADERS"]
"""


def test_loads_remote_server_and_secrets(tmp_path):
    cfg = load_config(write(tmp_path, REMOTE))

    server = cfg.server
    assert server.mode == "remote"
    assert server.url == "https://gateway.example.org/api"
    assert server.model == "Claude-Test-1"
    assert server.api_key_file is None
    assert server.context_tokens is None
    assert server.agent_network == "proxy"
    assert server.ca_file == Path("/etc/ssl/certs/ca-certificates.crt")
    assert server.container is None and server.managed is None
    assert cfg.client.secrets.from_profile == Path.home() / "profile.sh"
    assert cfg.client.secrets.names == ("ANTHROPIC_API_KEY", "ANTHROPIC_CUSTOM_HEADERS")


def test_remote_context_tokens_and_ca_file(tmp_path):
    text = REMOTE.replace('model = "Claude-Test-1"', 'model = "m"\ncontext_tokens = 200000\nca_file = "~/ca.crt"')

    server = load_config(write(tmp_path, text)).server

    assert server.context_tokens == 200000
    assert server.ca_file == Path.home() / "ca.crt"


def test_remote_url_must_be_https(tmp_path):
    with pytest.raises(ConfigError, match="https"):
        load_config(write(tmp_path, REMOTE.replace("https://", "http://")))


@pytest.mark.parametrize("key", ['api_key_file = "~/key"', 'health_path = "/x"', 'container = "c"',
                                 'agent_url = "http://x"'])
def test_local_server_keys_are_not_allowed_for_remote(tmp_path, key):
    with pytest.raises(ConfigError, match="unknown keys"):
        load_config(write(tmp_path, REMOTE.replace('mode = "remote"', f'mode = "remote"\n{key}')))


def test_client_secrets_need_from_profile_and_names(tmp_path):
    with pytest.raises(ConfigError, match="client.secrets.names"):
        load_config(write(tmp_path, REMOTE.replace('names = ["ANTHROPIC_API_KEY", "ANTHROPIC_CUSTOM_HEADERS"]', "")))
    with pytest.raises(ConfigError, match="client.secrets.colour"):
        load_config(write(tmp_path, REMOTE + 'colour = "red"\n'))


def test_client_without_secrets(tmp_path):
    assert load_config(write(tmp_path, EXTERNAL)).client.secrets is None
