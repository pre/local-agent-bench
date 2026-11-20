"""The chat templates in templates/."""

import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# tokenizer.chat_template of gpt-oss-120b-F16.gguf (unsloth/gpt-oss-120b-GGUF, revision ff1a82da).
GPT_OSS_EMBEDDED = Path(__file__).parent / "gpt-oss-120b-embedded-template.jinja"

# A system or developer message that is not the first message becomes a developer
# message at its position. The embedded template drops it.
GPT_OSS_ADDED = [
    "    {%- elif message.role == 'system' or message.role == 'developer' -%}\n",
    '        {{- "<|start|>developer<|message|># Instructions\\n\\n" + message.content + "<|end|>" }}\n',
]
USER_BRANCH = "        {{- \"<|start|>user<|message|>\" + message.content + \"<|end|>\" }}\n"


def test_gpt_oss_template_only_adds_the_branch_for_a_later_system_message():
    # keepends: a newline after the last line of the template is also a difference.
    embedded = GPT_OSS_EMBEDDED.read_text().splitlines(keepends=True)
    patched = (ROOT / "templates" / "gpt-oss-120b.jinja").read_text().splitlines(keepends=True)

    diff = list(difflib.ndiff(embedded, patched))

    assert [line[2:] for line in diff if line.startswith("- ")] == []
    assert [line[2:] for line in diff if line.startswith("+ ")] == GPT_OSS_ADDED
    assert patched[patched.index(GPT_OSS_ADDED[0]) - 1] == USER_BRANCH
