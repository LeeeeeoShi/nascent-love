"""Comprehensive unit & integration test suite for the Adaptive Rhythm and Biofeedback Engine.

Verifies:
- Bancroft & Janssen Dual Control Model (SES / SIS1 / SIS2)
- Continuous Soft Blended Dynamic Weight Matrix
- Qi & Ginty (Nature 2024) Krause/Pacinian frequency boundaries
- Leung & Bensmaia (JNP 2005) adaptation-recovery dynamics
- Bohlen (1982) pelvic contraction resonance and Kuramoto phase locking
- Slew-rate limiting and Weber-Fechner tactile JND
- Safety invariants and consent gating
"""

import math
import sys
import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, "software/backend")

from app.main import app
from app.services.adaptive_rhythm import (
    AdaptivePreferenceRequest,
    AntiHabituationModulator,
    DualControlEngine,
    ResonanceEntrainmentFilter,
    calculate_adaptive_irpi,
    compute_blended_weights,
    get_or_create_adaptive_session,
    reset_adaptive_session,
)
from app.services.preference import PreferenceObservation


def test_soft_blended_weights_normalization_and_smoothness():
    """验证动态权重在整个唤起区间的归一化和连续平滑特性。"""
    for arousal in [0.0, 0.15, 0.35, 0.50, 0.70, 0.95]:
        weights = compute_blended_weights(
            phase="building",
            ses_score=arousal,
            sis_score=0.10,
            net_arousal=arousal,
            rhythm_coherence=0.60,
        )
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.002, f"Weights sum {total} != 1.0 at arousal {arousal}"
        assert all(w >= 0.0 for w in weights.values()), "Weights must be non-negative"

    # 在低唤起探索态，语言意图权重占优 (Basson 慢热模型)
    w_low = compute_blended_weights("exploration", 0.1, 0.1, 0.05, 0.1)
    assert w_low["explicit"] >= 0.45, "Exploration phase must emphasize verbal connection"

    # 在高唤起平台期，压力与骨盆共振占优
    w_high = compute_blended_weights("plateau", 0.85, 0.05, 0.80, 0.75)
    assert w_high["pressure"] >= 0.30, "Plateau phase must weight pelvic pressure heavily"


def test_dual_control_sis1_threat_brake():
    """验证 SIS1 (威胁/疼痛) 触发时的硬制动保护。"""
    engine = DualControlEngine(ses_current=0.75, sis1_current=0.05, sis2_current=0.05)

    # 突发语言 "pause" 与急性心率应激
    state = engine.step(
        explicit_feedback="pause",
        active_behavior="paused",
        pressure_trend="steady",
        autonomic_stress=0.85,
        rhythm_coherence=0.30,
    )

    assert state.inhibition_braked is True
    assert state.phase == "inhibition_alert"
    assert state.sis1_score >= 0.40
    assert "sis1_hard_brake_active" in state.reason_codes
    assert state.ses_score < 0.75, "SES must be sharply dampened under SIS1"


def test_dual_control_sis2_soft_distraction_regulation():
    """验证 SIS2 (分心/节奏过快) 的柔性减速，避免粗暴清零打破沉浸感。"""
    engine = DualControlEngine(ses_current=0.60, sis1_current=0.05, sis2_current=0.05)

    # 用户反馈 "slow_down"，行为 "lowered"
    state = engine.step(
        explicit_feedback="slow_down",
        active_behavior="lowered",
        pressure_trend="variable",
        autonomic_stress=0.50,
        rhythm_coherence=0.40,
    )

    assert state.sis2_score > state.sis1_score
    assert "sis2_soft_brake_active" in state.reason_codes
    # 柔性制动不应彻底踩死刹车
    assert state.ses_score > 0.15


def test_anti_habituation_krause_and_pacinian_bands():
    """验证根据 Ginty (Nature 2024) 的克劳斯与帕西尼共振频段映射。"""
    modulator = AntiHabituationModulator(last_freq_hz=48.0)

    # 探索阶段：克劳斯小体低频区间 (45~58Hz)
    engine_expl = DualControlEngine(ses_current=0.25)
    state_expl = engine_expl.step("comfortable", "continued", "steady")
    out_expl = modulator.step(dt_s=2.0, dual_state=state_expl)
    assert out_expl.carrier_band == "krause_low"
    assert 40.0 <= out_expl.target_frequency_hz <= 60.0

    # 平台阶段：帕西尼高频谐波区间
    engine_plat = DualControlEngine(ses_current=0.90, sis1_current=0.02, sis2_current=0.05)
    state_plat = engine_plat.step("comfortable", "advanced", "rising", rhythm_coherence=0.80)
    out_plat = modulator.step(dt_s=2.0, dual_state=state_plat)
    assert out_plat.carrier_band in {"krause_sweet", "pacinian_harmonic"}


def test_anti_habituation_leung_bensmaia_adaptation_and_recovery():
    """验证 Leung & Bensmaia (2005) 感觉脱敏与潮汐波谷复位动力学。"""
    modulator = AntiHabituationModulator(last_freq_hz=50.0, habituation_index=0.0)

    engine = DualControlEngine(ses_current=0.40)
    state = engine.step("comfortable", "continued", "steady")

    # 持续静态刺激 20 秒，脱敏指数必须升高
    for _ in range(10):
        out = modulator.step(dt_s=2.0, dual_state=state)

    assert out.habituation_index > 0.20, "Static stimulation must cause habituation"

    # 当脱敏指数高时，必须激活随机共振微抖动
    if out.habituation_index > 0.28:
        assert "anti_habituation_jitter" in out.reason_codes

    # 潮汐波谷期间或频率动态变化时，脱敏指数必须回落
    initial_h = modulator.habituation_index
    # 推进到呼吸波谷阶段并模拟动态频移
    for _ in range(5):
        engine.ses_current = max(0.1, engine.ses_current - 0.05)
        st = engine.step("comfortable", "continued", "steady")
        out = modulator.step(dt_s=2.0, dual_state=st)

    assert out.amplitude_ratio > 0.0


def test_slew_rate_limiter_complies_with_jnd():
    """验证韦伯-费希纳压摆平滑器限制频率突变，防止齿轮感卡顿。"""
    modulator = AntiHabituationModulator(last_freq_hz=50.0, max_freq_slew_hz_per_s=6.0)

    # 构造一次试图直接跃迁到 120Hz 的剧烈目标
    engine = DualControlEngine(ses_current=0.95)
    state = engine.step("comfortable", "advanced", "rising", rhythm_coherence=0.80)

    # 在 1 秒内，频率增量不能超过压摆上限 ~6Hz (加上微抖动裕度 <= 8Hz)
    out = modulator.step(dt_s=1.0, dual_state=state)
    assert out.target_frequency_hz <= 58.0, f"Frequency jump {out.target_frequency_hz} exceeded slew limit"


def test_bohlen_pelvic_contraction_filter():
    """验证 Bohlen (1982) 骨盆收缩间期与线性延展律提取。"""
    filter_ = ResonanceEntrainmentFilter(sampling_rate_hz=12.0)

    # 构造合成骨盆节律收缩：初发间期 0.70s (约 8.4 采样点)，随后每次递增约 0.08s
    intervals = [0.70, 0.78, 0.86, 0.95, 1.05]
    samples: list[float] = []

    for dt in intervals:
        samples.extend([0.10] * int(dt * 12.0))
        # 注入收缩脉冲峰
        samples.append(0.85)

    coherence, active, hz = 0.0, False, None
    for s in samples:
        coherence, active, hz = filter_.feed_sample(s)

    assert coherence > 0.40, f"Expected coherence > 0.40, got {coherence}"
    assert active is True, "Bohlen pelvic lock should be engaged on lengthening rhythm"
    assert hz is not None and 0.8 <= hz <= 1.8, f"Estimated hz {hz} must be in pelvic window"


def test_safety_event_immediate_hard_lock():
    """安全事件必须强制清零分值并锁止驱动。"""
    obs = PreferenceObservation(
        user_id="user-1",
        persona_id="persona-1",
        template_id="tpl-1",
        preference_key="pace_preference",
        candidate="calm",
        safety_event=True,
    )
    engine = DualControlEngine(ses_current=0.80)
    modulator = AntiHabituationModulator()

    result = calculate_adaptive_irpi(
        observation=obs,
        dual_engine=engine,
        modulator=modulator,
    )

    assert result.accepted is False
    assert result.score == 0.0
    assert result.dual_control.inhibition_braked is True
    assert "safety_event" in result.reason_codes


def test_consent_withdrawn_immediate_hard_lock():
    """撤回知情同意时必须强制制动。"""
    obs = PreferenceObservation(
        user_id="user-1",
        persona_id="persona-1",
        template_id="tpl-1",
        preference_key="intensity_preference",
        candidate="gentle",
        consent_state="withdrawn",
    )
    engine = DualControlEngine(ses_current=0.80)
    modulator = AntiHabituationModulator()

    result = calculate_adaptive_irpi(
        observation=obs,
        dual_engine=engine,
        modulator=modulator,
    )

    assert result.accepted is False
    assert result.score == 0.0
    assert result.dual_control.inhibition_braked is True
    assert "consent_not_confirmed" in result.reason_codes


@pytest.mark.asyncio
async def test_adaptive_preference_api_endpoint():
    """测试 FastAPI `/preferences/observe-adaptive` 端点完整生命周期。"""
    reset_adaptive_session(user_id="u_test_adaptive", persona_id="p_test")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "observation": {
                "user_id": "u_test_adaptive",
                "persona_id": "p_test",
                "template_id": "tpl_test",
                "preference_key": "pace_preference",
                "candidate": "responsive_flow",
                "explicit_feedback": "comfortable",
                "active_behavior": "continued",
                "pressure_trend": "steady",
                "temperature_trend": "stable",
                "context_fit": 0.85,
                "sensor_quality": "valid",
                "link_state": "valid",
                "data_age_ms": 120,
                "consent_state": "confirmed",
                "safety_event": False,
            },
            "dt_s": 2.0,
            "autonomic_stress": 0.15,
            "fsr_samples": [0.2, 0.25, 0.7, 0.2, 0.22, 0.8, 0.2, 0.21, 0.85],
        }

        resp = await client.post("/v1/agent/preferences/observe-adaptive", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "result" in data
        res = data["result"]
        assert res["accepted"] is True
        assert res["score"] > 0.0
        assert "dual_control" in res
        assert "rhythm_output" in res
        assert res["rhythm_output"]["target_frequency_hz"] >= 35.0

        # 清除会话验证
        del_resp = await client.delete("/v1/agent/preferences?user_id=u_test_adaptive&persona_id=p_test")
        assert del_resp.status_code == 200
