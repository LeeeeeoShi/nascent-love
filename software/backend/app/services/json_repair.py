"""鲁棒的 JSON 解析与截断自动修复工具。

用于抵御大模型输出常见问题：
1. 输出夹杂 Markdown 代码块 (```json ... ```)；
2. 尾随逗号 (trailing comma)；
3. 超时或 max_tokens 截断导致的未闭合引号、大括号或中括号；
4. 首尾冗余非 JSON 文本。
"""

from __future__ import annotations

import json
import re
from typing import Any


def repair_and_parse_json(text: str) -> dict[str, Any]:
    """解析并尝试自动修复大模型返回的 JSON 文本。"""
    if not text or not text.strip():
        raise ValueError("Empty input string")

    cleaned = text.strip()

    # 1. 提取 Markdown 代码块内部内容
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if code_block_match:
        cleaned = code_block_match.group(1).strip()

    # 2. 尝试标准解析
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 3. 定位最外层 JSON 对象的起始 '{'
    start = cleaned.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in text: {text[:80]}")

    candidate = cleaned[start:]
    last_brace = candidate.rfind("}")
    if last_brace != -1:
        truncated = candidate[: last_brace + 1]
    else:
        truncated = candidate

    # 4. 去除尾随逗号 (e.g. `{"a": 1, }` -> `{"a": 1}`)
    truncated = re.sub(r",\s*([}\]])", r"\1", truncated)

    try:
        data = json.loads(truncated)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 5. 符号栈补全：修复截断的字符串与未闭合的大/中括号
    in_string = False
    escape = False
    stack: list[str] = []
    repaired: list[str] = []

    for char in candidate:
        if escape:
            escape = False
            repaired.append(char)
            continue
        if char == "\\":
            escape = True
            repaired.append(char)
            continue
        if char == '"':
            in_string = not in_string
            repaired.append(char)
            continue
        if not in_string:
            if char in "{[":
                stack.append("}" if char == "{" else "]")
            elif char in "}]":
                if stack and stack[-1] == char:
                    stack.pop()
        repaired.append(char)

    if in_string:
        repaired.append('"')
    while stack:
        repaired.append(stack.pop())

    final_text = re.sub(r",\s*([}\]])", r"\1", "".join(repaired))
    data = json.loads(final_text)
    if not isinstance(data, dict):
        raise ValueError("Parsed JSON root is not an object")
    return data
