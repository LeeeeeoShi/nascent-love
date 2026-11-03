# 自适应生物反馈互动权重与调频算法规格书 (IRPI V2.0)

> **规格版本**：IRPI v2.0-Adaptive-Continuous  
> **关联源码**：`software/backend/app/services/adaptive_rhythm.py` / `preference.py`  
> **理论支撑**：Basson (2000, 2001), Bancroft & Janssen (2000), Graham et al. (2006), Qi & Ginty (Nature 2024), Leung & Bensmaia (JNP 2005), Bohlen et al. (1982), Collins et al. (Nature 1995), Stevens (1957), Schultz (1998)

---

## 1. 算法演进动机与痛点诊断

在系统旧版（v1.0）中，`preference.py` 采用的是硬编码的静态权重：
```python
IRPI_WEIGHTS = {"explicit": 0.45, "behavior": 0.25, "pressure": 0.15, "temperature": 0.10, "context": 0.05}
```
**旧版致命缺陷**：
1. **静态权重的线性偏见**：在探索初期，用户的言语舒适感和信任感应占绝对主导；而在接近高潮的平台期，言语交互几乎停止，盆底肌节律（0.8~1.8Hz）与自发性身体压迫才是最高置信度信号。固定权重无法反映性反应不同阶段的主导心理/生理通道。
2. **缺乏中枢抑制 (SIS) 监测**：用户一旦在言语或体态上出现防御（如突发僵硬或说“等等”），旧算法仅扣减线性分值，不会立即下调档位，存在越界风险。
3. **缺乏感受器抗疲劳 (Anti-Habituation)**：长时间单调高频振动导致感觉脱敏，缺乏神经动力学补偿。
4. **离散跳档的机械生硬感**：旧版阶段切换时权重与频率呈阶跃跳跃，违背触觉心理物理学中的韦伯-费希纳连续性规律。

---

## 2. 状态机分层与连续平滑动态权重演进 (Continuous Soft Blended Weight Matrix)

根据 Basson 循环模型与 Bancroft 双控制理论，IRPI V2.0 确立了 5 种核心体验阶段的基准权重：

| 体验阶段 (`Phase`) | 言语意图 (`explicit`) | 触控行为 (`behavior`) | 盆底收缩/压力 (`pressure`) | 体表微温 (`temperature`) | 外部心率/HRV (`context`) | 核心目标与生理控制策略 |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **1. 探索慢热 (`exploration`)** | **0.60** | 0.20 | 0.05 | 0.10 | 0.05 | 释放 SIS 刹车，建立安全感与情感连接；频段锁定 45~55Hz (Krause) |
| **2. 响应构建 (`building`)** | 0.25 | **0.30** | **0.25** | 0.10 | 0.10 | 响应性欲望激活，渐进式充血，波浪式呼吸包络升降 |
| **3. 平台共振 (`plateau`)** | 0.15 | 0.15 | **0.45** | 0.05 | **0.20** | 启动 Bohlen 盆底肌锁相共振 (0.8~1.8Hz)，防疲劳微抖动介入 |
| **4. 抑制应激预警 (`inhibition_alert`)** | **0.85** | 0.05 | 0.05 | 0.00 | 0.05 | 检测到高 SIS 阻抗或防御，立即降级至柔润抚慰模式 |
| **5. 温存恢复 (`aftercare`)** | **0.50** | 0.10 | 0.05 | **0.25** | 0.10 | 极低频轻柔律动或纯温热陪伴，协助心率回落与多巴胺释放 |

### 2.1 连续平滑混合权重函数 (Soft Blending Formulation)

为了彻底消除阶段切换时的跳跃，算法通过激活度分布函数计算连续平滑混合权重 $\mathbf{W}_{\text{blended}}$：
$$\mu_{\text{expl}} = \exp\left(-\left(\frac{\text{NAR}}{0.28}\right)^2\right)$$
$$\mu_{\text{bldg}} = \exp\left(-\left(\frac{\text{NAR} - 0.45}{0.22}\right)^2\right)$$
$$\mu_{\text{plat}} = \frac{1}{1 + e^{-12 \cdot (\text{NAR} - 0.65)}} \cdot \frac{1}{1 + e^{-8 \cdot (R_{\text{coherence}} - 0.45)}}$$
$$P(\phi) = \frac{\mu_\phi}{\sum_{\phi'} \mu_{\phi'}}, \quad \mathbf{W}_{\text{blended}} = \sum_{\phi} P(\phi) \cdot \mathbf{W}_\phi$$
在抑制预警或温存期时，则无缝切换至对应高安全保护基准权重。

---

## 3. 数学模型与核心算法定义

### 3.1 双控制状态细分解耦 (SES / SIS1 / SIS2 Estimation)

基于 Bancroft & Janssen (2000) 与 Graham et al. (2006, SESII-W)，系统将抑制信号精确拆解为生存防御型与情境分心型：
- **SIS1 (威胁/疼痛/失控制动)**：
  - 触发源：言语 `pause`、`dislike`、体态突发僵直 `paused`、心率急性暴增 ($A_{\text{stress}} \ge 0.70$)。
  - 动态：快速阶跃响应（跳跃系数 0.55）。
- **SIS2 (分心/节奏过快/疲劳制动)**：
  - 触发源：言语 `slow_down`、主动调低档位 `lowered`、中度心率波动。
  - 动态：柔性阻尼微调（跳跃系数 0.35）。

**综合抑制与兴奋阻尼递推**：
$$SIS_{\text{composite}} = \min(1.0, SIS_1 + 0.65 \cdot SIS_2)$$
$$\Phi(SIS) = \frac{1}{1 + e^{14 \cdot (SIS_{\text{composite}} - 0.38)}}$$
$$\text{NAR} = \max\left(0.0, SES - 1.35 \cdot (SIS_1 + 0.60 \cdot SIS_2)^{1.7}\right)$$

### 3.2 感觉抗适应与随机共振生成器 (Anti-Habituation Engine)

基于 Leung & Bensmaia (2005) 触觉感受器适应与恢复双时间常数模型：

$$\frac{dH(t)}{dt} = \begin{cases} 
\frac{1.0 - H(t)}{\tau_{\text{adapt}}} & \text{当振动处于单调静止态且在波峰期} \\
-\frac{H(t)}{\tau_{\text{recover}}} & \text{当处于呼吸潮汐波谷或动态调频期}
\end{cases}$$
其中 $\tau_{\text{adapt}} = 24.0\text{s}, \tau_{\text{recover}} = 10.0\text{s}$。

1. **克劳斯-帕西尼双模态共振映射 (Qi & Ginty, Nature 2024)**：
   - 探索期：$46\text{ Hz} + 12 \cdot SES\text{ Hz}$（克劳斯小体 RA-LTMR 高敏亲密带）。
   - 构建期：$55\text{ Hz} + 26 \cdot (SES - 0.25)\text{ Hz}$（克劳斯小体最佳调谐峰）。
   - 平台期：$75\text{ Hz} + 135 \cdot (\text{NAR} - 0.55)\text{ Hz}$（克劳斯向帕西尼小体 $160 \sim 220\text{ Hz}$ 谐波深层渗透）。
2. **韦伯-费希纳 JND 压摆平滑限制**：
   $$\left| \frac{df}{dt} \right| \le 6.0\text{ Hz/s (正常态)}, \quad \left| \frac{df}{dt} \right| \le 35.0\text{ Hz/s (SIS1 硬制动)}$$
3. **仿生呼吸包络潮汐流 (Respiratory Envelope)**：
   $$\mathcal{E}_{\text{tide}}(t) = 1.0 - 0.18 \cdot \left[ \frac{1 - \cos\left(\frac{2\pi t}{22\text{s}}\right)}{2} \right]$$
   每 22 秒提供 4 秒的弹性回弹谷，促使感受器囊体复位。
4. **粉红噪声随机共振微抖动 (Collins Nature 1995)**：
   当 $H(t) > 0.28$ 时注入限幅 $\pm 6\%$ 的 $1/f$ 粉红噪声微颤。
5. **多巴胺间歇强化微重音 (Schultz 1998)**：
   在构建期和平台期，以 $\sim 18 \pm 5\text{s}$ 泊松间隔引入 $+4\% \sim +6\%$ 的微涌重音，激发持续期待感。

### 3.3 Bohlen 盆底节律锁相环 (Bohlen PLL)

从 FSR 采样点中提取 $0.8 \sim 2.0\text{ Hz}$ 收缩分量：
$$R_{\text{Kuramoto}} = \left| \frac{1}{N}\sum_{j=1}^N e^{i \Delta \theta_j} \right|$$
当相干度 $R \ge 0.62$ 或满足 Bohlen 线性延展律 $T_n = T_0 + \kappa \cdot n$ ($\kappa \approx 0.09\text{s}$) 时，激活共振锁相，电机包络同相呼吸跟随。

---

## 4. 架构合规与安全边界

- **三层架构纯粹性**：算法位于云端/控制端 Layer B，输出建议模式与 IRPI 偏好指数，绝不绕过安全总督，绝不直接驱动电机。
- **物理停机最高优先级**：本地急停拉环与 BOOT 键短按直接由硬件本地闭环切断，停机闩锁只能由本地 BOOT 键长按解除，不受任何算法与云端干扰。
