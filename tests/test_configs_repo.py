"""The configuration files in configs/."""

import re
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


def test_effort_variants_set_the_effort_of_claude_code():
    # Claude Code sends output_config.effort in each request, and the request value
    # replaces the reasoning_effort of --chat-template-kwargs.
    assert load_config(CONFIGS / "qwen38-effort-medium.toml").client.env["CLAUDE_CODE_EFFORT_LEVEL"] == "medium"
    assert load_config(CONFIGS / "qwen38-effort-low.toml").client.env["CLAUDE_CODE_EFFORT_LEVEL"] == "low"


SERVER_FLAGS = "--host 0.0.0.0 --port 8080 --api-key-file /run/api-key -c 131072"
MODELS = {
    "gpt-oss-120b.toml": (
        "-m /models/gpt-oss-120b-F16.gguf --alias gpt-oss-120b"
        " -ngl all -fa on -lm none -np 1 -b 2048 -ub 2048 --jinja --reasoning-effort high --temp 1.0 --top-p 1.0"
        " --top-k 0 --min-p 0.0"),
    "qwen3-coder-next.toml": (
        "-m /models/UD-Q8_K_XL/Qwen3-Coder-Next-UD-Q8_K_XL-00001-of-00003.gguf --alias qwen3-coder-next"
        " -ngl all -fa on -lm none -np 1 --jinja --temp 1.0 --top-p 0.95 --top-k 40 --min-p 0.01"),
    "qwen38-27b.toml": (
        "-m /models/Qwen3.8-27B-Q8_0.gguf --alias qwen3.8-27b"
        " -ngl all -fa on -lm none -np 1 --jinja --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0"
        " --spec-type draft-mtp --spec-draft-n-max 2 --chat-template-file /run/chat-template.jinja"),
    "glm-53-flash.toml": (
        "-m /models/UD-IQ2_XXS/GLM-5.3-Flash-UD-IQ2_XXS-00001-of-00004.gguf --alias glm-5.3-flash"
        " -ngl all -fa on -lm none -np 1 -ub 512 -ctk q8_0 -ctv q8_0 -cram 0 -ctxcp 4"
        " --jinja --reasoning-effort high --temp 1.0 --top-p 0.95"),
}


@pytest.mark.parametrize("name, flags", MODELS.items())
def test_model_configuration_has_the_flags_of_the_research(name, flags):
    config = load_config(CONFIGS / name)

    assert pairs(llama_server_args(config.server)) == pairs(f"{SERVER_FLAGS} {flags}".split())
    assert config.name == name.removesuffix(".toml")
    assert config.server.managed.port == 8090
    assert config.server.managed.image == load_config(CONFIGS / "qwen38-base.toml").server.managed.image
    assert config.server.managed.draft is None


def test_model_directories_follow_the_download_list():
    listed = {line.split("\t")[0] for line in (ROOT / "download" / "models.tsv").read_text().splitlines()
              if not line.startswith("#")}
    dirs = {load_config(CONFIGS / name).server.managed.models_dir.name for name in MODELS}

    assert dirs == listed


def test_only_glm_needs_a_clean_gpu():
    limits = {name: load_config(CONFIGS / name).server.managed.gtt_max_used_mib for name in MODELS}

    assert limits.pop("glm-53-flash.toml") == 6000
    assert set(limits.values()) == {12288}


def test_qwen38_27b_uses_the_patched_template():
    assert load_config(CONFIGS / "qwen38-27b.toml").server.managed.chat_template == "templates/qwen38-flash-next.jinja"


def help_flags() -> set[str]:
    """The flags of `llama-server --help` of the pinned image (build 12531). The
    flag names are in the first 40 characters of a line."""
    text = (Path(__file__).parent / "llama-server-help-build12531.txt").read_text()
    return {flag for line in text.splitlines() if line.startswith("-")
            for flag in re.findall(r"--?[A-Za-z][\w-]*", line[:40])}


@pytest.mark.parametrize("path", sorted(CONFIGS.glob("*.toml")), ids=lambda p: p.name)
def test_each_configuration_loads_and_uses_known_flags(path):
    config = load_config(path)

    if config.server.managed:
        flags = {arg for arg in llama_server_args(config.server) if re.fullmatch(r"--?[A-Za-z][\w-]*", arg)}
        assert flags - help_flags() == set()
