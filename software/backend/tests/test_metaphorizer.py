from __future__ import annotations

import sys
sys.path.insert(0, "software/backend")

from app.services.metaphorizer import is_censorship_risk, metaphorize_text


def test_metaphorize_sensitive_terms():
    raw = "我想要高潮，你在插入的时候轻一点"
    metaphorized = metaphorize_text(raw)
    assert "高潮" not in metaphorized
    assert "插入" not in metaphorized
    assert "潮汐峰值" in metaphorized
    assert "靠近与深入" in metaphorized


def test_is_censorship_risk():
    assert is_censorship_risk("自慰体验") is True
    assert is_censorship_risk("今天去公园散步，天气很好") is False
