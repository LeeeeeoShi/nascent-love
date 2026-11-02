from __future__ import annotations

import sys
sys.path.insert(0, "software/backend")

import pytest
from app.services.json_repair import repair_and_parse_json


def test_standard_json():
    data = repair_and_parse_json('{"dialogue": "我在", "tts_style": "温柔"}')
    assert data["dialogue"] == "我在"
    assert data["tts_style"] == "温柔"


def test_markdown_codeblock():
    raw = """Here is the result:
```json
{
  "dialogue": "靠过来点",
  "scene_ctrl": "next"
}
```
Hope it helps!"""
    data = repair_and_parse_json(raw)
    assert data["dialogue"] == "靠过来点"
    assert data["scene_ctrl"] == "next"


def test_trailing_commas():
    raw = '{"dialogue": "慢一点", "items": [1, 2, ], }'
    data = repair_and_parse_json(raw)
    assert data["dialogue"] == "慢一点"
    assert data["items"] == [1, 2]


def test_truncated_json_repair():
    # Model output cut off by max_tokens or timeout
    raw = '{"dialogue": "（把你揽进怀里）别怕，我们慢慢'
    data = repair_and_parse_json(raw)
    assert "dialogue" in data
    assert "别怕，我们慢慢" in data["dialogue"]


def test_no_json():
    with pytest.raises(ValueError):
        repair_and_parse_json("这是一段纯文本，没有任何大括号")
