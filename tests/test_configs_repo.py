"""The configuration files in configs/."""

from pathlib import Path

import pytest

from llm_eval.config import load_config
from llm_eval.server import llama_server_args

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs"

# The command line of the server llama-qwen38 (just up-mtp of ~/dev/local-llm/llama-server).
LLAMA_QWEN38 = (
    "--host 0.0.0.0 --port 8080 --api-key-file /run/api-key"
    " -m /models/UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf --alias qwen3.8-flash-next"
    " -ngl 999 -fa on -np 1 -lzm on -c 131072 -ctk q8_0 -ctv q8_0 --jinja --temp 1.0 --top-p 0.95"
    " --top-k 20 --min-p 0.0 --chat-template-file /run/chat-template.jinja"
    " -md /models/MTP/mtp-Qwen3.8-Flash-Next-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 3"
)


def pairs(args: list[str]) -> set[tuple[str, str | None]]:
    """The flags with their values, without the order of the flags."""
    result, i = set(), 0
    while i < len(args):
        if i + 1 < len(args) and not args[i + 1].startswith("-"):
            result.add((args[i], args[i + 1]))
            i += 2
        else:
            result.add((args[i], None))
            i += 1
    return result


def args_of(name: str) -> set:
    return pairs(llama_server_args(load_config(CONFIGS / name).server))


def test_base_has_the_settings_of_llama_qwen38():
    base = load_config(CONFIGS / "qwen38-base.toml")

    assert pairs(llama_server_args(base.server)) == pairs(LLAMA_QWEN38.split())
    assert base.server.managed.chat_template == "templates/qwen38-flash-next.jinja"
    assert (ROOT / base.server.managed.chat_template).is_file()
    assert base.client.env == load_config(CONFIGS / "qwen38-external.toml").client.env


@pytest.mark.parametrize("name, removed, added", [
    ("qwen38-effort-medium.toml", set(), {("--chat-template-kwargs", '{"reasoning_effort":"medium"}')}),
    ("qwen38-effort-low.toml", set(), {("--chat-template-kwargs", '{"reasoning_effort":"low"}')}),
    ("qwen38-iq4-xs.toml", {("-m", "/models/UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf")},
     {("-m", "/models/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00004.gguf")}),
    ("qwen38-kv-f16.toml", {("-ctk", "q8_0"), ("-ctv", "q8_0")}, {("-ctk", "f16"), ("-ctv", "f16")}),
    ("qwen38-ctx-65536.toml", {("-c", "131072")}, {("-c", "65536")}),
    ("qwen38-no-mtp.toml", {("-md", "/models/MTP/mtp-Qwen3.8-Flash-Next-Q8_0.gguf"),
                            ("--spec-type", "draft-mtp"), ("--spec-draft-n-max", "3")}, set()),
    ("qwen38-temp-0.6.toml", {("--temp", "1.0")}, {("--temp", "0.6")}),
])
def test_variant_changes_one_setting(name, removed, added):
    base, variant = args_of("qwen38-base.toml"), args_of(name)

    assert base - variant == removed
    assert variant - base == added
    assert load_config(CONFIGS / name).name == name.removesuffix(".toml")


def test_context_variant_changes_the_client_too():
    assert load_config(CONFIGS / "qwen38-ctx-65536.toml").server.context_tokens == 65536


def test_external_names_its_container():
    assert load_config(CONFIGS / "qwen38-external.toml").server.container == "llama-qwen38"


@pytest.mark.parametrize("name, model", [("claude-sonnet-5.5-gateway.toml", "Claude-Sonnet-5-5"),
                                         ("claude-opus-5.5-gateway.toml", "Claude-Opus-5-5")])
def test_gateway_configs_use_one_model_and_the_profile_secrets(name, model):
    cfg = load_config(CONFIGS / name)

    assert cfg.name == name.removesuffix(".toml")
    assert cfg.server.mode == "remote"
    assert cfg.server.agent_network == "proxy"
    assert cfg.server.model == model
    assert cfg.server.context_tokens is None
    assert cfg.client.secrets.names == ("ANTHROPIC_API_KEY", "ANTHROPIC_CUSTOM_HEADERS")
    assert "ANTHROPIC_AUTH_TOKEN" not in cfg.client.env
