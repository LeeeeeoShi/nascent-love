"""Scientific Adaptive Rhythm and Biofeedback Engine.

Grounding Research & Peer-Reviewed Literature:
1. Rosemary Basson (2000, 2001): Non-linear Circular Sexual Response & Responsive Desire
2. John Bancroft, Erick Janssen & Cynthia Graham (2000, 2006): Dual Control Model (SES / SIS1 / SIS2)
3. Lijun Qi, Michael Handler, Genelle Rankin, Seungwon Choi, David D. Ginty (Nature 2024):
   Krause corpuscles as dedicated genital vibrotactile sensors (40-80 Hz RA-LTMRs)
4. Y. Y. Leung, Sliman J. Bensmaia, Steven S. Hsiao, Kenneth O. Johnson (J Neurophysiol 2005):
   Exponential time courses of vibrotactile adaptation (tau_adapt ~ 24s) and recovery (tau_recover ~ 10s)
5. Nicole Prause et al. (Sex Relat Ther 2012):
   Vibration parameter boundaries (43-148 Hz, 37-783 um) and vibration-induced desensitization prevention
6. Joseph G. Bohlen et al. (Arch Sex Behav 1982):
   Pelvic contraction dynamics (initial interval T0 ~ 0.65-0.82s, linear lengthening kappa ~ 0.08-0.12s)
7. Stephen W. Porges (2007, 2011):
   Polyvagal Theory, Ventral Vagal Social Engagement & Heart Rate Variability (HRV / RMSSD)
8. James J. Collins et al. (Nature 1995):
   Stochastic resonance & 1/f pink noise micro-jitter in sensory mechanoreceptors
9. S. S. Stevens (1957) & Ronald T. Verrillo (1985):
   Tactile psychophysics, Stevens' power law, and Weber-Fechner Just Noticeable Difference (JND ~ 15%)
10. Wolfram Schultz (1998) & B. F. Skinner (1953):
    Dopaminergic reward prediction error and variable-interval micro-reinforcement
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .preference import (
    IRPIResult,
    PreferenceObservation,
    PreferenceSnapshot,
    _quality_gate,
)

PhaseType = Literal["exploration", "building", "plateau", "inhibition_alert", "aftercare"]

# 经典离散阶段基准权重矩阵
PHASE_WEIGHTS: dict[PhaseType, dict[str, float]] = {
    "exploration": {
        "explicit": 0.60,
        "behavior": 0.20,
        "pressure": 0.05,
        "temperature": 0.10,
        "context": 0.05,
    },
    "building": {
        "explicit": 0.25,
        "behavior": 0.30,
        "pressure": 0.25,
        "temperature": 0.10,
        "context": 0.10,
    },
    "plateau": {
        "explicit": 0.15,
        "behavior": 0.15,
        "pressure": 0.45,
        "temperature": 0.05,
        "context": 0.20,
    },
    "inhibition_alert": {
        "explicit": 0.85,
        "behavior": 0.05,
        "pressure": 0.05,
        "temperature": 0.00,
        "context": 0.05,
    },
    "aftercare": {
        "explicit": 0.50,
        "behavior": 0.10,
        "pressure": 0.05,
        "temperature": 0.25,
        "context": 0.10,
    },
}


def compute_blended_weights(
    phase: PhaseType,
    ses_score: float,
    sis_score: float,
    net_arousal: float,
    rhythm_coherence: float,
) -> dict[str, float]:
    """计算连续平滑混合权重 (Soft Blended Dynamic Weights)。

    避免离散跳档导致的权重跳变，基于 Softmax / Sigmoid 激活度进行平滑融合。
    """
    if sis_score >= 0.40 or phase == "inhibition_alert":
        return PHASE_WEIGHTS["inhibition_alert"].copy()

    if phase == "aftercare":
        return PHASE_WEIGHTS["aftercare"].copy()

    # 计算各阶段在连续参数空间中的相对激活度 (Logits)
    # 探索期激活度：随 net_arousal 增加呈高斯衰减
    w_expl = math.exp(-((net_arousal / 0.28) ** 2))
    # 构建期激活度：在 net_arousal 约 0.45 处达到峰值
    w_bldg = math.exp(-(((net_arousal - 0.45) / 0.22) ** 2))
    # 平台期激活度：随 net_arousal 和骨盆节律相干度增加呈 Sigmoid 增长
    sig_arousal = 1.0 / (1.0 + math.exp(-12.0 * (net_arousal - 0.65)))
    sig_coherence = 1.0 / (1.0 + math.exp(-8.0 * (rhythm_coherence - 0.45)))
    w_plat = sig_arousal * sig_coherence

    total = w_expl + w_bldg + w_plat
    if total < 1e-6:
        p_expl, p_bldg, p_plat = 1.0, 0.0, 0.0
    else:
        p_expl = w_expl / total
        p_bldg = w_bldg / total
        p_plat = w_plat / total

    blended: dict[str, float] = {}
    for key in ("explicit", "behavior", "pressure", "temperature", "context"):
        val = (
            p_expl * PHASE_WEIGHTS["exploration"][key]
            + p_bldg * PHASE_WEIGHTS["building"][key]
            + p_plat * PHASE_WEIGHTS["plateau"][key]
        )
        blended[key] = round(val, 4)

    # 归一化以保证权重严格和为 1.0
    weight_sum = sum(blended.values())
    if weight_sum > 0:
        for k in blended:
            blended[k] = round(blended[k] / weight_sum, 4)

    return blended


class DualControlState(BaseModel):
    """Bancroft & Janssen 双控制状态评估值。"""

    model_config = ConfigDict(extra="forbid")
    ses_score: float = Field(ge=0.0, le=1.0, description="性兴奋系统指数 (Sexual Excitation System)")
    sis_score: float = Field(ge=0.0, le=1.0, description="性抑制系统综合指数 (Sexual Inhibition System)")
    sis1_score: float = Field(default=0.0, ge=0.0, le=1.0, description="SIS1 威胁/疼痛/失控抑制指数")
    sis2_score: float = Field(default=0.0, ge=0.0, le=1.0, description="SIS2 分心/负荷/脱节抑制指数")
    net_arousal: float = Field(ge=0.0, le=1.0, description="净愉悦接受度 (Net Arousal Receptivity)")
    phase: PhaseType = Field(default="exploration")
    inhibition_braked: bool = False
    reason_codes: list[str] = Field(default_factory=list)


class AdaptiveRhythmOutput(BaseModel):
    """自适应调频与生物反馈控制输出。"""

    model_config = ConfigDict(extra="forbid")
    target_frequency_hz: float = Field(ge=20.0, le=250.0)
    amplitude_ratio: float = Field(ge=0.0, le=1.0)
    carrier_band: Literal["krause_low", "krause_sweet", "pacinian_harmonic", "soothing_glide"]
    habituation_index: float = Field(ge=0.0, le=1.0, description="感受器疲劳脱敏指数 (越高说明脱敏越明显)")
    breathing_envelope_phase: float = Field(ge=0.0, le=1.0)
    bohlen_entrained: bool = False
    bohlen_rhythm_hz: float | None = None
    reason_codes: list[str] = Field(default_factory=list)


@dataclass
class DualControlEngine:
    """双控制模型 (SES / SIS1 / SIS2) 状态机引擎。"""

    gamma_ses: float = 0.94  # SES 维持半衰记忆系数
    gamma_sis: float = 0.86  # SIS 缓解恢复系数 (确认安全后平缓回落)
    ses_current: float = 0.20
    sis1_current: float = 0.08  # 威胁/疼痛中枢抑制
    sis2_current: float = 0.10  # 分心/节奏负荷抑制
    phase: PhaseType = "exploration"

    def step(
        self,
        explicit_feedback: str,
        active_behavior: str,
        pressure_trend: str,
        autonomic_stress: float = 0.0,
        rhythm_coherence: float = 0.0,
    ) -> DualControlState:
        reasons: list[str] = []

        # 1. 细分估算抑制信号 (SIS1: 威胁与疼痛防御 vs SIS2: 分心与负荷过大)
        # SIS1: 强防御信号 ("pause", "dislike", 极高心率应激突变)
        sis1_input = 0.0
        if explicit_feedback == "pause":
            sis1_input = max(sis1_input, 0.95)
            reasons.append("sis1_verbal_pause")
        elif explicit_feedback == "dislike":
            sis1_input = max(sis1_input, 0.90)
            reasons.append("sis1_verbal_dislike")

        if active_behavior == "paused":
            sis1_input = max(sis1_input, 0.85)
        if autonomic_stress >= 0.70:
            sis1_input = max(sis1_input, 0.80)
            reasons.append("sis1_autonomic_acute_stress")

        # SIS2: 轻柔调整信号 ("slow_down", "lowered", "skipped", 中度心率波动)
        sis2_input = 0.0
        if explicit_feedback == "slow_down":
            sis2_input = max(sis2_input, 0.65)
            reasons.append("sis2_verbal_slow_down")
        if active_behavior == "lowered":
            sis2_input = max(sis2_input, 0.55)
        elif active_behavior == "skipped":
            sis2_input = max(sis2_input, 0.40)
        if 0.40 <= autonomic_stress < 0.70:
            sis2_input = max(sis2_input, 0.45)

        # 递推 SIS1 (威胁踩刹车极快，跳跃因子 0.55)
        if sis1_input > self.sis1_current:
            self.sis1_current = self.sis1_current + 0.55 * (sis1_input - self.sis1_current)
        else:
            self.sis1_current = self.gamma_sis * self.sis1_current + (1.0 - self.gamma_sis) * sis1_input
        self.sis1_current = max(0.0, min(1.0, self.sis1_current))

        # 递推 SIS2 (分心柔性调节，跳跃因子 0.35)
        if sis2_input > self.sis2_current:
            self.sis2_current = self.sis2_current + 0.35 * (sis2_input - self.sis2_current)
        else:
            self.sis2_current = self.gamma_sis * self.sis2_current + (1.0 - self.gamma_sis) * sis2_input
        self.sis2_current = max(0.0, min(1.0, self.sis2_current))

        # 综合 SIS 指数
        sis_composite = max(0.0, min(1.0, self.sis1_current + 0.65 * self.sis2_current))

        # 2. 估算兴奋信号 (SES 促发因子)
        ses_verbal = {
            "comfortable": 0.85,
            "keep": 0.88,
            "unknown": 0.40,
            "slow_down": 0.15,
            "dislike": 0.0,
            "pause": 0.0,
        }.get(explicit_feedback, 0.40)

        ses_behavior = {
            "advanced": 0.88,
            "continued": 0.76,
            "unknown": 0.40,
            "lowered": 0.20,
            "paused": 0.0,
            "skipped": 0.0,
        }.get(active_behavior, 0.40)

        ses_pressure = {
            "rising": 0.72,
            "steady": 0.78,
            "variable": 0.48,
            "falling": 0.25,
            "unknown": 0.40,
        }.get(pressure_trend, 0.40)

        instant_ses = (
            0.35 * ses_verbal
            + 0.25 * ses_behavior
            + 0.20 * ses_pressure
            + 0.20 * rhythm_coherence
        )

        # Bancroft 刹车效应门控：高 SIS 会强力阻断 SES 的产生与保持
        brake_factor = 1.0 / (1.0 + math.exp(14.0 * (sis_composite - 0.38)))
        if self.sis1_current >= 0.40:
            reasons.append("sis1_hard_brake_active")
            self.ses_current = max(0.04, self.ses_current * 0.75)
        elif self.sis2_current >= 0.25 or sis2_input >= 0.50:
            reasons.append("sis2_soft_brake_active")
            self.ses_current = max(0.10, self.ses_current * 0.90)
        else:
            self.ses_current = (
                self.gamma_ses * self.ses_current
                + (1.0 - self.gamma_ses) * instant_ses * brake_factor
            )
        self.ses_current = max(0.0, min(1.0, self.ses_current))

        # 3. 计算净愉悦接受度 (Net Arousal Receptivity, NAR)
        net_arousal = max(0.0, self.ses_current - 1.35 * ((self.sis1_current + 0.60 * self.sis2_current) ** 1.7))

        # 4. 状态机阶段跃迁
        inhibition_braked = self.sis1_current >= 0.40 or sis_composite >= 0.50
        if inhibition_braked:
            self.phase = "inhibition_alert"
            reasons.append("phase_inhibition_alert")
        elif explicit_feedback in {"pause", "dislike"} and self.ses_current < 0.22:
            self.phase = "aftercare"
            reasons.append("phase_aftercare")
        elif net_arousal >= 0.68 and rhythm_coherence >= 0.55:
            self.phase = "plateau"
            reasons.append("phase_plateau_resonance")
        elif net_arousal >= 0.32:
            self.phase = "building"
            reasons.append("phase_building")
        else:
            self.phase = "exploration"
            reasons.append("phase_exploration")

        return DualControlState(
            ses_score=round(self.ses_current, 4),
            sis_score=round(sis_composite, 4),
            sis1_score=round(self.sis1_current, 4),
            sis2_score=round(self.sis2_current, 4),
            net_arousal=round(net_arousal, 4),
            phase=self.phase,
            inhibition_braked=inhibition_braked,
            reason_codes=reasons,
        )


@dataclass
class AntiHabituationModulator:
    """机械感受器感觉抗疲劳与随机共振调频器。

    科学文献基础：
    - Qi & Ginty (Nature 2024): Krause corpuscles (40-80Hz 最优区间)
    - Leung & Bensmaia (J Neurophysiol 2005): 触觉适应与恢复双时间常数模型
    - Collins et al. (Nature 1995): 粉红噪声随机共振
    - Schultz (1998): 多巴胺间歇强化与微重音预期调制
    - Stevens (1957) & Verrillo (1985): 韦伯-费希纳压摆平滑限制
    """

    tau_adapt_s: float = 24.0  # 适应时间常数 ~24s
    tau_recover_s: float = 10.0  # 恢复时间常数 ~10s
    habituation_index: float = 0.0  # 0.0 (敏感) ~ 1.0 (严重脱敏)
    last_freq_hz: float = 48.0
    last_amp: float = 0.30
    elapsed_total_s: float = 0.0
    breathing_period_s: float = 22.0  # 呼吸包络潮汐周期 ~22秒
    max_freq_slew_hz_per_s: float = 6.0  # 正常频移压摆上限 6Hz/s (符合触觉 JND)
    max_amp_slew_per_s: float = 0.15  # 正常幅值压摆上限 0.15/s
    last_dopamine_accent_s: float = 0.0  # 上次多巴胺微重音触发时间

    def step(
        self,
        dt_s: float,
        dual_state: DualControlState,
        bohlen_active: bool = False,
    ) -> AdaptiveRhythmOutput:
        reasons: list[str] = []
        dt_s = max(0.05, min(10.0, dt_s))
        self.elapsed_total_s += dt_s

        # 1. 计算理论理想基频 (Base Carrier Frequency)
        if dual_state.phase == "inhibition_alert":
            ideal_freq = 40.0
            ideal_amp = 0.20
            carrier_band = "soothing_glide"
            reasons.append("soothing_glide_mode")
        elif dual_state.phase == "aftercare":
            ideal_freq = 38.0
            ideal_amp = 0.16
            carrier_band = "soothing_glide"
            reasons.append("aftercare_glide")
        elif dual_state.phase == "exploration":
            # 探索期：严格锁定在克劳斯小体高敏柔和带 (45-56 Hz)
            ideal_freq = 46.0 + 12.0 * dual_state.ses_score
            ideal_amp = 0.32 + 0.18 * dual_state.ses_score
            carrier_band = "krause_low"
        elif dual_state.phase == "building":
            # 构建期：克劳斯小体黄金共振带 (55-75 Hz)
            ideal_freq = 55.0 + 26.0 * max(0.0, dual_state.ses_score - 0.25)
            ideal_amp = 0.50 + 0.28 * dual_state.ses_score
            carrier_band = "krause_sweet"
        else:  # plateau
            # 平台共振期：克劳斯与帕西尼小体 (160-220 Hz) 谐波加成
            ideal_freq = 75.0 + 135.0 * max(0.0, dual_state.net_arousal - 0.55)
            ideal_freq = min(220.0, max(65.0, ideal_freq))
            ideal_amp = 0.72 + 0.22 * dual_state.net_arousal
            carrier_band = "pacinian_harmonic"
            reasons.append("pacinian_harmonic_engaged")

        # 2. 韦伯-费希纳 JND 压摆平滑限制 (Slew-Rate Limiting)
        # 抑制硬制动时允许超快速降频 (30Hz/s)，其他常态平缓平滑
        slew_freq_limit = 35.0 if dual_state.inhibition_braked else self.max_freq_slew_hz_per_s
        freq_diff = ideal_freq - self.last_freq_hz
        max_delta_f = slew_freq_limit * dt_s
        if abs(freq_diff) > max_delta_f:
            base_freq = self.last_freq_hz + math.copysign(max_delta_f, freq_diff)
        else:
            base_freq = ideal_freq

        # 幅值压摆平滑
        slew_amp_limit = 0.60 if dual_state.inhibition_braked else self.max_amp_slew_per_s
        amp_diff = ideal_amp - self.last_amp
        max_delta_a = slew_amp_limit * dt_s
        if abs(amp_diff) > max_delta_a:
            base_amp = self.last_amp + math.copysign(max_delta_a, amp_diff)
        else:
            base_amp = ideal_amp

        # 3. 仿生呼吸包络潮汐流 (Respiratory Envelope Modulation)
        envelope_phase = (self.elapsed_total_s % self.breathing_period_s) / self.breathing_period_s
        # 呼吸波形谷值下降约 18% 以促成机械感受器被囊弹性回弹
        tide_dip = 0.18 * 0.5 * (1.0 - math.cos(2.0 * math.pi * envelope_phase))
        is_in_trough = tide_dip > 0.12

        # 4. 感觉神经疲劳微分动力学 (Leung & Bensmaia 2005 双时间常数微分积分)
        freq_is_static = abs(base_freq - self.last_freq_hz) < 1.5 and not bohlen_active
        if freq_is_static and not is_in_trough and base_amp > 0.25:
            # 适应期：囊体受压侧向滑移，动作电位衰减
            dh = ((1.0 - self.habituation_index) / self.tau_adapt_s) * dt_s
            self.habituation_index = min(1.0, self.habituation_index + dh)
        else:
            # 恢复期：潮汐波谷或动态调频重置机械门控通道
            dh = (self.habituation_index / self.tau_recover_s) * dt_s
            self.habituation_index = max(0.0, self.habituation_index - dh)

        # 5. 随机共振粉红噪声微抖动 (Collins Nature 1995)
        if self.habituation_index > 0.28:
            reasons.append("anti_habituation_jitter")
            jitter_sigma = 0.040 * (0.8 + 0.5 * self.habituation_index)
            jitter = random.gauss(0.0, jitter_sigma)
            jitter = max(-0.06, min(0.06, jitter))
        else:
            jitter = 0.0

        # 6. 多巴胺间歇强化微重音 (Schultz 1998 预期预测误差调制)
        dopamine_boost = 0.0
        time_since_accent = self.elapsed_total_s - self.last_dopamine_accent_s
        if dual_state.phase in {"building", "plateau"} and time_since_accent > 18.0:
            # 随机概率触发 1.5 秒的微型潮涌微重音 (+4% ~ +6%)
            if random.random() < 0.25:
                self.last_dopamine_accent_s = self.elapsed_total_s
                dopamine_boost = 0.05
                reasons.append("dopaminergic_anticipation_accent")

        target_freq = round(base_freq * (1.0 + jitter) * (1.0 + dopamine_boost * 0.5), 2)
        target_freq = max(25.0, min(240.0, target_freq))
        self.last_freq_hz = target_freq

        # 7. 综合振幅输出计算 (包含潮汐回弹与疲劳保护)
        fatigue_decay = 1.0 - 0.22 * self.habituation_index
        target_amp = base_amp * (1.0 - tide_dip) * fatigue_decay * (1.0 + dopamine_boost)
        target_amp = max(0.05, min(1.0, target_amp))
        self.last_amp = target_amp

        return AdaptiveRhythmOutput(
            target_frequency_hz=target_freq,
            amplitude_ratio=round(target_amp, 4),
            carrier_band=carrier_band,
            habituation_index=round(self.habituation_index, 4),
            breathing_envelope_phase=round(envelope_phase, 4),
            bohlen_entrained=bohlen_active,
            bohlen_rhythm_hz=None,
            reason_codes=reasons,
        )


@dataclass
class ResonanceEntrainmentFilter:
    """盆底肌收缩节律分析与锁相环 (Bohlen et al. 1982 & Kuramoto 1975)。

    提取 0.8 Hz ~ 2.0 Hz 骨盆收缩微颤动，并测量与设备节律的一致性及线性延展律。
    """

    sampling_rate_hz: float = 12.0  # 硬件 FSR 采样率 ~12Hz
    buffer_capacity: int = 48  # 4秒滚动缓冲
    buffer: list[float] = field(default_factory=list)
    detected_intervals: list[float] = field(default_factory=list)

    def feed_sample(self, raw_fsr: float) -> tuple[float, bool, float | None]:
        """送入压力采样点，返回 (相干度 0~1, 是否启动 Bohlen 锁相, 瞬时节律频率 Hz)。"""
        self.buffer.append(raw_fsr)
        if len(self.buffer) > self.buffer_capacity:
            self.buffer.pop(0)

        if len(self.buffer) < 20:
            return 0.0, False, None

        # 1. 消除直流基线 (DC Detrending)
        dc_mean = sum(self.buffer) / len(self.buffer)
        detrended = [x - dc_mean for x in self.buffer]

        # 2. 统计过零点与极值点，寻找 0.8Hz ~ 2.0Hz (周期 0.5s ~ 1.35s) 的骨盆收缩
        peaks: list[int] = []
        for i in range(1, len(detrended) - 1):
            # 引入动态不应期 (Refractory Period)：连续峰值间隔至少 5 个采样点 (约 0.42 秒)
            if detrended[i] > 0.04 and detrended[i] > detrended[i - 1] and detrended[i] >= detrended[i + 1]:
                if not peaks or (i - peaks[-1]) >= 5:
                    peaks.append(i)

        if len(peaks) < 3:
            return 0.10, False, None

        # 峰值间间隔 (秒)
        dt_samples = [peaks[j] - peaks[j - 1] for j in range(1, len(peaks))]
        dt_seconds = [s / self.sampling_rate_hz for s in dt_samples]

        # 筛选处于 Bohlen 骨盆收缩生理窗口 (0.50s ~ 1.35s, 对应 0.74Hz ~ 2.0Hz) 内的周期
        valid_intervals = [t for t in dt_seconds if 0.50 <= t <= 1.35]
        if len(valid_intervals) < 2:
            return 0.20, False, None

        mean_interval = sum(valid_intervals) / len(valid_intervals)
        rhythm_hz = round(1.0 / mean_interval, 2)

        # 3. 计算藏本相位一致性 (Kuramoto Order Parameter Approximation)
        # 标准差打分
        variance = sum((t - mean_interval) ** 2 for t in valid_intervals) / len(valid_intervals)
        std_dev = math.sqrt(variance)
        coherence = max(0.0, min(1.0, 1.0 - (std_dev / 0.22)))

        # 4. Bohlen 间期线性递增规律检测 (每周期递增 ~0.06 ~ 0.14s)
        is_lengthening = False
        if len(valid_intervals) >= 3:
            diffs = [valid_intervals[k] - valid_intervals[k - 1] for k in range(1, len(valid_intervals))]
            if all(d >= -0.05 for d in diffs) and sum(diffs) > 0.06:
                is_lengthening = True

        bohlen_active = coherence >= 0.62 or (coherence >= 0.48 and is_lengthening)

        return round(coherence, 4), bohlen_active, rhythm_hz


class EnhancedIRPIResult(IRPIResult):
    """扩展版 IRPI v2.0 计算结果，保留对 v1.0 字段的完全契约兼容。"""

    model_config = ConfigDict(extra="forbid")
    dual_control: DualControlState
    rhythm_output: AdaptiveRhythmOutput


class AdaptivePreferenceRequest(BaseModel):
    """自适应偏好观察请求，携带生物反馈辅助流。"""

    model_config = ConfigDict(extra="forbid")
    observation: PreferenceObservation
    dt_s: float = Field(default=2.0, ge=0.05, le=60.0)
    autonomic_stress: float = Field(default=0.0, ge=0.0, le=1.0)
    fsr_samples: list[float] = Field(default_factory=list)


class AdaptivePreferenceRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: EnhancedIRPIResult
    snapshot: PreferenceSnapshot | None = None


_adaptive_sessions: dict[
    tuple[str, str],
    tuple[DualControlEngine, AntiHabituationModulator, ResonanceEntrainmentFilter],
] = {}


def get_or_create_adaptive_session(
    user_id: str, persona_id: str
) -> tuple[DualControlEngine, AntiHabituationModulator, ResonanceEntrainmentFilter]:
    key = (user_id, persona_id)
    if key not in _adaptive_sessions:
        _adaptive_sessions[key] = (
            DualControlEngine(),
            AntiHabituationModulator(),
            ResonanceEntrainmentFilter(),
        )
    return _adaptive_sessions[key]


def reset_adaptive_session(user_id: str, persona_id: str | None = None) -> int:
    keys = [k for k in _adaptive_sessions if k[0] == user_id and (persona_id is None or k[1] == persona_id)]
    for k in keys:
        del _adaptive_sessions[k]
    return len(keys)


def calculate_adaptive_irpi(
    observation: PreferenceObservation,
    dual_engine: DualControlEngine,
    modulator: AntiHabituationModulator,
    dt_s: float = 2.0,
    autonomic_stress: float = 0.0,
    rhythm_coherence: float = 0.0,
    bohlen_active: bool = False,
    bohlen_hz: float | None = None,
) -> EnhancedIRPIResult:
    """根据 Bancroft 双控制模型、Basson 非线性循环与抗适应调谐计算 IRPI V2.0。"""
    if observation.safety_event:
        reasons = ["safety_event"]
        dual_engine.sis1_current = 1.0
        dual_state = DualControlState(
            ses_score=0.0,
            sis_score=1.0,
            sis1_score=1.0,
            sis2_score=0.5,
            net_arousal=0.0,
            phase="inhibition_alert",
            inhibition_braked=True,
            reason_codes=["safety_event_braked"],
        )
        rhythm_out = modulator.step(dt_s, dual_state, bohlen_active=False)
        return EnhancedIRPIResult(
            score=0.0,
            quality_gate=0.0,
            accepted=False,
            weighted_components={},
            reason_codes=reasons,
            dual_control=dual_state,
            rhythm_output=rhythm_out,
        )

    if observation.consent_state != "confirmed":
        reasons = ["consent_not_confirmed"]
        dual_engine.sis1_current = 0.90
        dual_state = DualControlState(
            ses_score=0.0,
            sis_score=0.90,
            sis1_score=0.90,
            sis2_score=0.40,
            net_arousal=0.0,
            phase="inhibition_alert",
            inhibition_braked=True,
            reason_codes=["consent_withdrawn_braked"],
        )
        rhythm_out = modulator.step(dt_s, dual_state, bohlen_active=False)
        return EnhancedIRPIResult(
            score=0.0,
            quality_gate=0.0,
            accepted=False,
            weighted_components={},
            reason_codes=reasons,
            dual_control=dual_state,
            rhythm_output=rhythm_out,
        )

    reasons: list[str] = []
    quality = _quality_gate(observation, reasons)

    # 1. 执行双控制状态机演进 (SES / SIS1 / SIS2)
    dual_state = dual_engine.step(
        explicit_feedback=observation.explicit_feedback,
        active_behavior=observation.active_behavior,
        pressure_trend=observation.pressure_trend,
        autonomic_stress=autonomic_stress,
        rhythm_coherence=rhythm_coherence,
    )
    reasons.extend(dual_state.reason_codes)

    # 2. 执行抗感觉适应与生物共振调频
    rhythm_out = modulator.step(dt_s, dual_state, bohlen_active=bohlen_active)
    if bohlen_active and bohlen_hz is not None:
        rhythm_out.bohlen_rhythm_hz = bohlen_hz
        reasons.append("bohlen_entrained")
    reasons.extend(rhythm_out.reason_codes)

    # 3. 动态平滑混合权重计算 (Continuous Soft Blended Dynamic Weights)
    blended_weights = compute_blended_weights(
        phase=dual_state.phase,
        ses_score=dual_state.ses_score,
        sis_score=dual_state.sis_score,
        net_arousal=dual_state.net_arousal,
        rhythm_coherence=rhythm_coherence,
    )

    # 组件分值转换
    values = {
        "explicit": {
            "unknown": 0.50,
            "comfortable": 0.88,
            "keep": 0.82,
            "slow_down": 0.30,
            "pause": 0.00,
            "dislike": 0.05,
        }[observation.explicit_feedback],
        "behavior": {
            "unknown": 0.50,
            "continued": 0.78,
            "advanced": 0.85,
            "lowered": 0.28,
            "paused": 0.08,
            "skipped": 0.12,
        }[observation.active_behavior],
        "pressure": {
            "unknown": 0.50,
            "rising": 0.65,
            "steady": 0.80,
            "variable": 0.55,
            "falling": 0.30,
        }[observation.pressure_trend],
        "temperature": {
            "unknown": 0.50,
            "warming": 0.65,
            "stable": 0.75,
            "cooling": 0.35,
        }[observation.temperature_trend],
        "context": max(0.0, min(1.0, 0.4 * observation.context_fit + 0.6 * rhythm_coherence)),
    }

    weighted = {k: round(blended_weights[k] * values[k], 4) for k in blended_weights}
    raw_score = sum(weighted.values())

    # 抑制因子扣除与质量门控
    if dual_state.inhibition_braked:
        score = 0.0
        accepted = False
        reasons.append("inhibition_braked")
    else:
        # 疲劳自适应补偿：抗疲劳微抖动保护下的净得分
        score = max(0.0, min(1.0, quality * raw_score * (1.0 - 0.20 * rhythm_out.habituation_index)))
        accepted = quality >= 0.50 and observation.explicit_feedback not in {"pause", "dislike"}

    if not accepted and "inhibition_braked" not in reasons:
        reasons.append("quality_below_threshold" if quality < 0.50 else "negative_feedback")

    return EnhancedIRPIResult(
        score=round(score, 4),
        quality_gate=round(quality, 4),
        accepted=accepted,
        weighted_components=weighted,
        reason_codes=list(dict.fromkeys(reasons)),
        dual_control=dual_state,
        rhythm_output=rhythm_out,
    )
