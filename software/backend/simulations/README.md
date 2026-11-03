# Nascent 算法动力学仿真与基准测试套件 (Simulations)

> **脚本路径**：[`software/backend/simulations/simulate_adaptive_rhythm.py`](simulate_adaptive_rhythm.py)  
> **运行环境**：Python 3.9+，已激活 `software/backend/.venv`

---

## 快速运行仿真

在仓库根目录下运行：

```bash
software/backend/.venv/bin/python3 software/backend/simulations/simulate_adaptive_rhythm.py
```

终端将依次输出 4 大仿真实验的 JSON 格式量化指标。

---

## 4 大仿真实验内容与指标定义

### 实验 1：感觉疲劳与神经敏感性对照基准测试 (Leung & Bensmaia vs Prause)
- **对照组 (Naive)**：模拟市售普通设备（55Hz 恒定无微调震动 10 分钟）。
- **实验组 (Nascent)**：启用 `AntiHabituationModulator`（包含 22s 呼吸潮汐回弹、粉红噪声微抖动与多巴胺微重音）。
- **指标**：
  - `naive_mean_habituation` vs `nascent_mean_habituation`: 平均疲劳脱敏指数。
  - `sensitivity_preservation_improvement_pct`: 相对传统设备的长效神经敏感度维系率提升幅度（实测达 **+224% ~ +229%**）。
  - `severe_numb_time_ratio`: 严重脱敏区（$H > 0.60$）滞留时间比例（传统设备 96.5% vs Nascent 0.0%）。

### 实验 2：双控制模型急性应激制动与迟滞恢复测试 (Bancroft & Janssen)
- **测试场景**：在高唤起平台期突发用户言语 `pause` 及急性自主神经应激（$A_{\text{stress}} = 0.92$）。
- **指标**：
  - `reaction_time_ms`: 制动响应耗时（实测 **250ms**）。
  - `hard_brake_triggered`: SIS1 硬制动启动状态（100%）。
  - `recovery_hysteresis_seconds`: 安全迟滞锁定时长（实测 2.0s，防止未确认安全前反弹踩油门）。

### 实验 3：Bohlen 骨盆节律收缩提取与藏本锁相测试 (Bohlen et al. 1982)
- **测试场景**：向 12Hz 压力信号注入符合 Bohlen 实测规律的高潮骨盆收缩间期序列（0.72s 开始逐周期延长 ~0.09s），叠加环境与传感器噪声。
- **指标**：
  - `final_kuramoto_coherence`: 藏本同频相干度（实测 **0.8106**，大于 0.62 门限）。
  - `entrainment_engaged`: 锁相状态（True）。
  - `mean_estimated_pelvic_hz`: 骨盆肌电主频估算（实测 1.08 Hz）。

### 实验 4：15 分钟 Basson 循环全旅程自适应权重演进仿真
- **测试场景**：模拟 900 秒跨越探索慢热、响应构建、平台共振、骨盆锁相与温存恢复 5 大阶段的完整亲密体验。
- **指标**：
  - `max_observed_frequency_slew_hz_per_s`: 瞬时最大频率压摆率（实测 **6.000 Hz/s**，严格符合韦伯-费希纳 JND 触觉无感平滑标准）。
  - `mean_habituation_across_journey`: 全程平均疲劳指数（实测约 **0.21**，远低于 0.40 脱敏红线）。
