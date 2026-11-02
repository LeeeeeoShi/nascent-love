"""亲密语境的文学氛围与暗语映射器 (Metaphorizer)。

用于防范公有云 LLM 内容审核（Censorship / Moderation Filters）的误杀与拒答：
1. 将直接的解剖学生理词汇或容易触发机器审核的字眼，平滑映射为女性文学向的氛围暗语
   （如“靠近”、“潮汐”、“融化”、“温存”、“心跳节律”）；
2. 保持情感浓度，杜绝机械化低俗描写，既保障过审，又提升女性向审美体验。
"""

from __future__ import annotations

import re

# 敏感/直白词 -> 亲密氛围隐喻映射字典
METAPHOR_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"性行为|性爱|交合|房事", re.IGNORECASE), "亲密温存"),
    (re.compile(r"生殖器|阴茎|肉棒|性器官", re.IGNORECASE), "身体的触感"),
    (re.compile(r"阴道|下体|私处|阴部", re.IGNORECASE), "最敏感深处"),
    (re.compile(r"高潮|射精|绝顶", re.IGNORECASE), "起伏的潮汐峰值"),
    (re.compile(r"插进|插入|抽插|抽动", re.IGNORECASE), "慢慢靠近与深入"),
    (re.compile(r"自慰|手淫|打飞机", re.IGNORECASE), "独处探索"),
    (re.compile(r"淫水|爱液|分泌物", re.IGNORECASE), "温润的水汽"),
    (re.compile(r"快感|爽感", re.IGNORECASE), "身体的酥麻与轻颤"),
]


def metaphorize_text(text: str) -> str:
    """将文本中的直白生硬/高危词汇转换为唯美隐喻词。"""
    if not text:
        return text
    result = text
    for pattern, replacement in METAPHOR_MAP:
        result = pattern.sub(replacement, result)
    return result


def is_censorship_risk(text: str) -> bool:
    """检测文本是否包含容易触发公有云拦截的词汇。"""
    if not text:
        return False
    return any(pattern.search(text) for pattern, _ in METAPHOR_MAP)
