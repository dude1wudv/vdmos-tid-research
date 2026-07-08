# 四篇种子论文知识点总结：VDMOS / Trench Power MOSFET 与 TID 实验路线

## 0. 四篇论文各自解决什么问题

| 序号 | 论文 | 在本项目中的作用 | 读完应获得的能力 |
|---|---|---|---|
| 1 | Williams et al., 2017, *The Trench Power MOSFET-Part I: History, Technology, and Prospects* | 器件背景：为什么 trench VDMOS 能取代 planar VDMOS / VMOS，以及结构、工艺、导通电阻、栅漏工程、可靠性之间的权衡 | 看懂 trench VDMOS 的结构参数：沟槽、栅氧、p-body、n-epi、deep p+、TBOX、split gate、superjunction / RSO 等 |
| 2 | Williams et al., 2017, *The Trench Power MOSFET-Part II: Application Specific VDMOS, LDMOS, Packaging, and Reliability* | 应用与可靠性：封装、应用场景、开关损耗、雪崩、硬换流、FB-SOA 等如何决定器件设计 | 明白实验指标不能只看阈值，还要看 RON、BVDSS、IDSS、QG/QGD、UIS、热/封装寄生 |
| 3 | Oldham & McLean, 2003, *Total Ionizing Dose Effects in MOS Oxides and Devices* | TID 物理基础：辐照在 SiO2/MOS 中如何产生电荷、陷阱、退火、反弹、漏电 | 能把 TID 损伤拆成 Not、Nit、border traps、field oxide leakage，并知道测试/退火为什么这样设计 |
| 4 | Gao et al., 2012, *Research on the total dose effects for domestic VDMOS devices used in satellite*（国产星用 VDMOS 总剂量辐射损伤效应研究） | VDMOS TID 实验模板：给出国产星用 n 型 VDMOS 的 Co-60 总剂量、偏置、退火、参数测试和结果解释 | 能把论文实验搬到 TCAD：剂量点、偏置条件、Vth/BVDSS/RON/IDSS 提取、Not/Nit 参数扫描 |

四篇论文的逻辑不是并列的，而是递进的：

```text
功率 MOSFET 为什么长成 VDMOS / trench VDMOS
  -> 哪些结构和工艺决定 RON、BVDSS、QG、可靠性
  -> MOS 氧化层在 TID 下产生哪些电荷和陷阱
  -> VDMOS 中这些损伤如何表现为 Vth、漏电、击穿、导通电阻变化
  -> 在 Sentaurus 里用固定氧化层电荷、界面陷阱、偏置和退火参数复现实验趋势
```

---

## 1. 器件背景：从 BJT、VMOS、planar VDMOS 到 trench VDMOS

### 1.1 功率开关为什么需要 MOSFET 化

Williams Part I 从功率器件历史讲起：早期 BJT 能做非锁存功率开关，但有三个核心缺点：

1. 需要基极驱动电流，驱动功耗大；
2. 开关速度受少子存储影响；
3. 并联困难，容易电流拥挤、热失控和二次击穿。

功率 MOSFET 的优势是：绝缘栅输入阻抗高、开关速度快、温度系数更利于并联，并且可以用单元阵列扩展电流能力。代价是：高压器件需要漂移区，漂移区电阻会随击穿电压急剧上升。

### 1.2 VDMOS 的基本导电路径

VDMOS（vertical double-diffused MOSFET）利用垂直导电：

```text
source n+ -> p-body 表面反型沟道 -> n-epi 漂移区 -> n+ substrate / drain
```

关键结构含义：

- **double diffusion**：p-body 和 n+ source 由扩散形成，沟道长度由两次扩散的差决定，而不完全依赖光刻尺寸。
- **p-body**：控制阈值电压、沟道形成和体二极管。
- **n-epi 漂移区**：承受关断电压，是高压器件 RON 和 BVDSS 的核心权衡。
- **cell array**：大量单元并联获得低导通电阻。

论文把导通电阻近似拆成：

```text
RON = Rmetal + Rcontact + Rsource + Rch + Racc + Rjfet + Repi + Rsub + Rpkg
```

实际仿真时不能只盯沟道：低压 trench VDMOS 可能由沟道/封装/金属主导，高压 VDMOS 常由漂移区主导。

### 1.3 “硅极限”：击穿电压与漂移区电阻的矛盾

Williams Part I 提到，单极硅功率器件漂移区电阻近似随击穿电压按幂律上升：

```text
Repi ∝ V(br)^n, n 约为 2.5-2.6
```

含义：

- 低压器件（特别是 60 V 以下）：沟道电阻、单元密度、封装寄生很重要；
- 中高压器件：漂移区厚度和掺杂决定击穿和导通电阻，单纯增加 cell density 收益有限；
- 要突破传统折中，需要 superjunction、RESURF、field plate、TBOX、split gate 等场工程。

### 1.4 planar VDMOS 的瓶颈与 trench 的价值

Planar VDMOS 的 p-body 之间存在 **JFET pinch resistance**。当 cell pitch 缩小时，沟道密度虽然提高，但 JFET 区变窄，电流扩展变差，RON 会出现 U 形最小值：继续缩小单元反而使 RON 增大。

Trench VDMOS 把沟道转到垂直沟槽侧壁，去掉或显著减弱 planar 单元中的 JFET 瓶颈，使 cell density 增加时 RON 能继续下降。因此 trench 对低压大电流应用特别重要。

---

## 2. Trench VDMOS 的结构、工艺和可靠性知识点

### 2.1 沟槽回填与平坦化：可量产 trench 的前提

Williams Part I 强调，trench VDMOS 成功的第一步不是电学公式，而是可制造性。关键工艺是：

1. 刻蚀窄沟槽；
2. 沟槽内生长栅氧；
3. 用掺磷多晶硅完全填充沟槽；
4. 多晶硅 etchback，使多晶硅栅顶低于硅表面但仍覆盖 source；
5. 再氧化封口，避免金属接触和表面台阶问题。

这个设计把早期 VMOS / rectangular-groove MOSFET 的台阶覆盖问题变成近似平面工艺问题，是量产可靠性的基础。

### 2.2 沟槽底部电场：TBOX、deep p+ 和场屏蔽

Trench gate 的风险是：沟槽底角附近电场集中，雪崩或热载流子靠近栅氧，会造成栅氧破裂、IGSS 增大、阈值漂移。

论文列出的保护思路：

- **TBOX（thick bottom oxide）**：沟槽底部使用厚氧化层，把高场从薄栅氧处移开；
- **deep p+ unit-cell clamp**：每个单元中加入深 p+ 区，屏蔽 trench gate，钳位雪崩位置；
- **field shaping**：通过沟槽底部厚氧、侧壁厚氧、外延掺杂梯度、局部注入等方式移动峰值电场；
- **edge termination**：芯片边缘也需要场板、场环或 trench termination，否则边缘先击穿。

对 TCAD 的启发：TID 实验不应只看沟道处栅氧；终端/场氧/沟槽底部的电荷会显著影响 IDSS 和 BVDSS。

### 2.3 沟槽刻蚀和栅氧质量

沟槽刻蚀可靠性的要点：

- 沟槽应沿合适晶向，避免 <111> 面引起粗糙界面、高界面电荷和低迁移率；
- 刻蚀底部要圆角化，避免尖角电场集中；
- 刻蚀后不能长时间暴露或接触有机残留，否则会导致栅漏、阈值不稳定、HTRB / HTGB 失效；
- sacrificial oxidation / cleaning 用于修复刻蚀损伤、降低界面态。

这和 TID 直接相关：辐照前已有的界面质量、氧空位、氢相关缺陷，会决定辐照后 Not/Nit 的生成速度和退火行为。

### 2.4 栅漏工程：降低 QGD / QG 与开关损耗

Trench VDMOS 追求低 RON 后，另一个瓶颈是栅电荷，尤其是 **Miller 电荷 QGD**。Williams Part I 讨论了：

- **field plate trench**：场板帮助屏蔽栅漏，但若场板接 gate，会增加反馈电容；
- **split-gate / shielded-gate trench**：下部 buried field plate 接地，不接 gate，能显著降低 CGD、QGD 和 QG；
- **superjunction / charge balance trench**：用 p/n 柱电荷平衡提高漂移区掺杂，降低漂移电阻；
- **RSO（RESURF stepped oxide）**：用阶梯氧化层/场板诱导耗尽，实现类 charge balance。

实验关联：如果你的 TCAD 结构是普通 trench VDMOS，不能直接套用 split-gate / RSO 的 QG 优势；但 TID 研究中应借鉴“电场位置决定可靠性”的思想。

### 2.5 RON 与 QG 的 FOM

Williams Part I 用 `QG * RDS(on)` 作为开关性能指标：

```text
[QG RDS] = [RDSA] * [QG/A]
```

含义：

- 低 RON 器件不一定是高频开关最优器件；
- motor control 可能偏向低 RON；
- 高频 Buck / dc-dc 可能更看重低 QG、低 QGD、低 Qrr；
- TID 后如果 Vth 漂移导致栅驱裕量下降，等效 RON 和开关损耗都会变化。

### 2.6 制造可靠性与应用可靠性要分开

Williams Part I/II 把可靠性分成两类：

1. **制造相关可靠性**：沟槽刻蚀、栅氧、沟槽顶部氧化/平坦化、接触孔刻蚀；常见失效是 IGSS、IDSS、HTRB、HTGB、阈值不稳定。
2. **应用相关可靠性**：UIS、重复雪崩、硬换流、体二极管反恢复、FB-SOA、热循环、封装金属疲劳。

TID 实验主要属于环境可靠性，但读数会和上述两类可靠性耦合：例如 TID 增加 IDSS，可能把 HTRB 或高温反偏下的漏电问题放大。

---

## 3. 应用和封装：为什么 VDMOS 实验不只测 Vth

### 3.1 封装寄生会吞掉低 RON 优势

Williams Part II 给出总体导通电阻表达：

```text
RDS(ON) = RDSA / A + (Rmetal + Rwire + Rpkg)
```

当器件本体从几十毫欧降到几毫欧时，bond wire、clip lead、顶层金属、封装电阻可能占总电阻 25%-40%。因此：

- TCAD 中的器件本体 RON 不是数据手册 RDS(on)；
- 实测 RON 变化很小，可能因为漂移区/封装主导，沟道 Vth 漂移贡献被稀释；
- 对低压大电流 VDMOS，封装和金属可靠性可能比沟道更先限制寿命。

### 3.2 应用特定 VDMOS

Part II 讨论的典型应用：

- **锂电池保护双向断开开关（BDS）**：两个 MOSFET 背靠背，要求低 RON、小封装、低栅压工作；
- **安全气囊 squib driver**：冗余串联开关，一个作恒流，一个作 PWM，需要避免误触发并支持诊断电流；
- **ABS / solenoid driver**：感性负载，重复雪崩和 UIS 能力重要；
- **同步整流 / Buck converter**：HSS 和 LSS 的 RON、QG、QGD、Qrr、体二极管反恢复共同决定效率；
- **motor drive**：高电流、并联、硬换流、短路/堵转故障、热和封装可靠性重要；
- **trench LDMOS / BCD 集成**：把 trench 思路引入横向器件和功率 IC。

实验启发：TID 后参数变化对不同应用的严重性不同。空间星用器件更关心长期偏置下的漏电、阈值、击穿和退火；汽车/电源器件还要关心雪崩和热循环。

### 3.3 开关损耗拆解

同步 Buck 中，HSS 和 LSS 的功耗包括：

- 导通损耗：`I^2 * RDS(on)`，与占空比有关；
- 栅驱损耗：与 QG 和开关频率有关；
- Miller / 交叉损耗：高电压和高电流短时重叠；
- 体二极管反恢复损耗：与 Qrr、硬换流有关。

Part II 给出面积配比思想：对于 Buck，LSS 导通时间约为 `1-D`，HSS 约为 `D=VOUT/VIN`，大降压比时 LSS 通常需要更低 RON/更大面积。

### 3.4 雪崩、硬换流和 FB-SOA

- **UIS（unclamped inductive switching）**：低边开关关断感性负载时，电感电流迫使体二极管雪崩吸收能量；
- **重复雪崩**：可能产生热载流子损伤、漏电/阈值漂移/输出电容漂移，也可能引发金属和接触热循环退化；
- **硬换流**：半桥中一个 MOSFET 的体二极管导通后，另一个 MOSFET 强行开通，少子反恢复导致高 dV/dt、EMI、过冲和损耗；
- **FB-SOA**：线性模式下同时有高电流和高电压，热稳定性和热点风险不能只靠“MOSFET 正温度系数”粗略判断。

TID 延申：辐照诱发的界面态会降低迁移率、改变 Vth 和 gm；在 FB-SOA 或电流源应用中，这会影响热稳定性和电流分布。

---

## 4. MOS 总剂量效应：从辐照到电学退化

Oldham & McLean 是本组论文的物理核心。它的主线是：

```text
ionizing radiation
  -> SiO2 中产生 electron-hole pairs
  -> 电子快速扫出，空穴部分复合、部分输运
  -> 空穴在氧化层/界面附近深陷阱被俘获，形成 oxide trapped charge Not
  -> 氢相关过程生成 Si/SiO2 interface traps Nit
  -> Vth、mobility、subthreshold、leakage、field oxide parasitic channel 变化
  -> 随时间、温度、偏置发生退火、补偿、反弹 rebound
```

### 4.1 电子-空穴对产生与初始空穴产额

辐照在 SiO2 中沉积能量，产生电子-空穴对。论文给出 SiO2 中电子-空穴对产生能约为 18 eV。电子迁移率远高于空穴，通常在皮秒量级被扫出；空穴移动慢，且会经历复合、输运和俘获。

初始空穴产额取决于：

- 电场强度：电场越强，越能分离电子/空穴，复合越少；
- 入射粒子 LET / 线性能量沉积：高 LET 轨迹中电荷对更密集，复合更强；
- 辐照源类型：Co-60 gamma、电子、质子、alpha、X-ray 的等效损伤不能只按总剂量粗暴比较。

模型：

- **geminate recombination**：孤立电子-空穴对复合；
- **columnar recombination**：高 LET 轨迹中柱状密集电荷复合。

实验启发：如果以后把 Co-60 结果换成 X-ray 或质子辐照，要重新考虑 dose enhancement 和 charge yield，而不是只用 Gy(Si) 数值平移。

### 4.2 空穴输运：慢、分散、强依赖场/温度/厚度

Oldham & McLean 总结的空穴输运特征：

1. 时间跨度很宽，呈强分散输运；
2. log-time 上有“形状相似”的 universal recovery；
3. 电场激活；
4. 约 140 K 以上强温度激活，低温下温度激活弱；
5. 输运时间对氧化层厚度有超线性依赖。

常用解释是 **continuous-time random walk（CTRW）小极化子 hopping**：空穴在非晶 SiO2 中随机浅陷阱之间跳跃。

TCAD 简化：Sentaurus 中通常不会完整模拟 CTRW；工程上常把结果折算成固定氧化层电荷 `Not` 随剂量/退火变化的参数扫描。

### 4.3 氧化层陷阱 Not：正电荷、退火和 border traps

深空穴陷阱通常与 Si/SiO2 过渡区的氧空位、E' center 等缺陷相关。Not 对 nMOS / nVDMOS 的典型作用是：

- 正氧化层电荷吸引电子，使 n 沟道更容易开启；
- nMOS / nVDMOS 阈值电压负向漂移；
- 漏电可能增加，尤其当场氧/边缘区形成寄生沟道。

退火机制：

- **隧穿退火**：室温附近常重要；
- **热激发退火**：温度升高后显著；
- **补偿而非真正消失**：一些“退火”的正电荷可在反向偏置下重新出现，说明电子补偿和陷阱结构转换都可能参与。

**Border traps**：靠近界面的氧化层陷阱可与硅交换电荷，表现得像慢界面态，会造成频率/时间依赖的阈值和噪声变化。

### 4.4 界面态 Nit：Si-H 断键、质子输运和迁移率退化

辐照诱发界面态通常对应 Si/SiO2 界面的三价 Si dangling bond。主流模型是两阶段过程：

1. 辐照空穴参与释放氢，形成质子 H+；
2. H+ 在氧化层中 hopping 迁移到界面，打断 Si-H 键，产生界面态。

Nit 的电学后果：

- nMOS 中界面态可带负电，与 Not 的正电效应相反；
- 会造成阈值“反弹”或 super-recovery；
- 降低沟道迁移率，恶化 gm、亚阈值摆幅和噪声；
- 对偏置、温度、氢含量和工艺强依赖。

### 4.5 Rebound：为什么 168 h / 100 °C 退火很重要

Oldham & McLean 重点讨论 rebound：辐照结束时，nMOS 的阈值漂移可能由正 Not 和负 Nit 部分抵消；退火时 Not 较快减少，但 Nit 保留，于是最终阈值可能向正方向漂移并导致失效。

标准测试 1019.4 采用 `100 °C / 168 h` 退火来筛查 rebound。国产 VDMOS 论文采用的 `168 h, 100 °C` 高温退火与这一思想一致。

实验启发：

- 不能只测“辐照后立刻”的参数；
- 至少需要 dose 点、辐照后、退火后三个阶段；
- TCAD 中可用 `Not` 下降、`Nit` 持平或继续增加来模拟退火后趋势。

### 4.6 剂量率、非线性和剂量增强

论文强调：许多 CMOS TID 响应没有真正 dose-rate dependence，但实验上会出现 apparent dose-rate effects，因为不同剂量率意味着不同曝光时间，退火时间不同。

还要注意：

- response 对 dose 可能非线性，陷阱饱和、空间电荷和退火都会破坏线性叠加；
- 10 keV X-ray 在多层材料中存在 dose enhancement，不同氧化层实际吸收剂量不同；
- Co-60 gamma 更接近均匀剂量沉积。

### 4.7 缩放后的 TID 主战场：场氧和隔离结构

薄栅氧中 Not 随氧化层变薄显著下降，甚至被隧穿退火消除；但厚场氧、LOCOS bird's beak、trench isolation 等仍会积累大量正电荷，形成寄生漏电路径。

这对 VDMOS 特别重要：

- VDMOS 有 gate oxide，也有 field oxide、termination oxide、沟槽底部/侧壁氧化层；
- IDSS 增大往往来自边缘/场氧/终端寄生通道，而不一定来自主沟道 Vth 漂移；
- 只在主沟道界面加 `Not/Nit`，可能无法复现实测漏电变化。

---

## 5. 国产星用 VDMOS TID 论文：可直接转化为实验流程

### 5.1 研究对象和指标

论文研究两种国产星用 n 型 VDMOS，封装为 SMD。主要初始指标：

| 器件 | VGS(th) | BVDSS | RON | IDSS |
|---|---:|---:|---:|---:|
| A | 2-4 V | 400 V | 0.55 Ω | 2.5e-5 A |
| B | 2-4 V | 500 V | 0.55 Ω | 2.5e-5 A |

辐照后指标要求：

| 器件 | VGS(th) | BVDSS | RON | IDSS |
|---|---:|---:|---:|---:|
| A | 1.25-4.5 V | ≥300 V | ≤0.55 Ω | ≤5e-5 A |
| B | 1.25-4 V | ≥400 V | ≤0.55 Ω | ≤5e-5 A |

这些指标对应四类实验观测量：

- **VGS(th)**：沟道开启能力，最直接反映 gate oxide / interface traps；
- **BVDSS**：终端、漂移区、体二极管击穿能力；
- **RON**：沟道 + 漂移区 + JFET/扩展电阻的综合；
- **IDSS**：关断漏电，对场氧/边缘寄生通道敏感。

### 5.2 辐照与退火条件

论文实验条件：

- 辐照源：北京师范大学 Co-60 gamma；
- 总剂量：`2e3 Gy(Si)`；
- 中间测试：若 50% 剂量 `1e3 Gy(Si)` 后参数合格，继续加剂量；
- 剂量率：`5e-1 Gy(Si)/s`；
- 温度：室温辐照；
- 退火：`168 h, 100 °C`；
- 标准：GJB128A-97 1019；
- 测试仪：TESEC 3620；
- 测试时间：每次测试不超过 2 h。

偏置条件：

| 偏置模式 | 条件 | 物理意义 |
|---|---|---|
| 栅偏置 | `VG = 12 V`，D/S 端短接或同电位 | 强化栅氧/沟道附近电场，考察 gate-bias TID |
| 漏偏置 A | `VD = 320 V`，G/S 端短接或同电位 | 关断高漏压，考察漂移区/终端/场氧电场 |
| 漏偏置 B | `VD = 400 V`，G/S 端短接或同电位 | 更高关断高漏压，接近高压工作环境 |

### 5.3 参数测试条件

| 参数 | 论文测试条件 | TCAD 对应提取 |
|---|---|---|
| VGS(th) | `VDS = VGS`, `ID = 1.0 mA` | 用恒流法在 Id-Vg 曲线中找 Vg |
| BVDSS | `VGS = 0 V`, `ID = 1.0 mA` | Vd 扫描，找 Id 达到 1 mA 的 Vd |
| RON | A：`VGS=12 V, ID=6 A`；B：`VGS=10 V, ID=4.8 A` | 开态低 VDS 或指定 ID 下求 `dV/dI` / `VDS/ID` |
| IDSS | A：`VDS=320 V, VGS=0`；B：`VDS=400 V, VGS=0` | 关断高漏压下读 drain leakage |

### 5.4 主要实验结果

论文结论可概括为：

1. **VGS(th)** 随累计剂量增加总体负向漂移，但漂移量在允许范围内；在 100 °C / 168 h 退火后，不同偏置下 Vth 有不同程度恢复，栅偏置下接近初值。
2. **漏偏置下 Vth 漂移大于栅偏置**。作者认为这与器件内部电场分布有关：漏偏置时 p/n 结附近空间电荷区更宽，氧化层/界面附近空穴俘获和界面陷阱生成更明显。
3. **BVDSS** 随剂量变化不明显，满剂量后约只有 3 V 量级变化；相较先前同类器件约 40 V 的击穿下降，改进后结构显著抑制 BVDSS 退化。
4. **RON** 随剂量和退火变化很小。解释是 RON 中漂移区 `Repi` 占主导，而 TID 引起的 `Rch` 变化占比小。
5. **IDSS** 相比初值有较明显变化，但仍满足设计指标；退火期间漏电没有像 Vth 那样简单恢复，可能与场氧/终端氧化层界面态继续增长有关。
6. 器件在目标总剂量下参数仍满足星用要求；实验对国产抗辐射 VDMOS 的结构和工艺优化有参考价值。

### 5.5 论文给出的机理解释

#### 5.5.1 阈值漂移

论文采用：

```text
ΔVth = ΔVot + ΔVit
```

其中：

- `ΔVot`：氧化层陷阱电荷引起的阈值漂移；
- `ΔVit`：界面陷阱电荷引起的阈值漂移。

对 n 型 VDMOS：

- 正氧化层陷阱电荷使 Vth 负向漂移；
- 界面陷阱带来的效应可抵消部分正电荷影响；
- 高剂量阶段界面态增多，可能让 Vth 变化变小甚至出现回漂。

#### 5.5.2 退火

100 °C 退火时，作者认为主要是氧化层陷阱电荷退火，界面态在该温度下不一定明显消退。因此不同偏置下退火恢复幅度相近，说明偏置差异主要来自界面陷阱数量差异。

#### 5.5.3 BVDSS 与 RON 的稳定

- BVDSS 受终端、漂移区和边缘场分布影响。通过结构改进、版图面积优化、终端设计、p 区注入等手段，击穿退化从约 40 V 降到约 3 V。
- RON 可写作 `Ron = Rch + Ra + Rj + Repi`。高压 VDMOS 中 `Repi` 占比大，TID 引起的沟道电阻变化不容易反映到总 RON。

#### 5.5.4 IDSS 的特殊性

IDSS 增加不只由主沟道 Vth 负漂造成。论文认为场氧化层/边缘氧化层中的陷阱电荷也会增加漏电；退火时场氧界面态可能继续增长，因此 IDSS 可继续变化。

---

## 6. 把论文转化成 VMware / Sentaurus 中的实验

仓库已有 VM/Sentaurus 说明：`docs/vm_setup/sentaurus_vm.md`。当前 trench VDMOS 示例的关键文件是：

- `sde_dvs.cmd`：几何、掺杂、接触、网格；
- `sdevice_des.cmd`：基线 Id-Vg；
- `TID_des.cmd`：用氧化层/界面电荷参数 `Not`、`Nit` 做 TID sweep；
- 现有主偏置流程：`Vd=0.1 V`，`Vg=-2 V -> 5 V` 扫描；
- 已观察现象：增大 `Not/Nit` 会让有效 Id-Vg 节点的表观阈值负向移动；`n18_des.log` 有 `Solve for t=0 does not converge`，不宜直接当物理证据。

### 6.1 最小可复现实验：先复现国产 VDMOS 论文四个参数

推荐先做一个小而完整的 sweep，不要一次做复杂剂量/热/可靠性全流程。

#### Step A：基线电学

1. Id-Vg：`Vd = 0.1 V` 或论文阈值定义中的 `VDS=VGS` 两种都可做；
2. Id-Vd / breakdown：`VGS=0`，扫 `VDS` 到接近击穿；
3. RON：高 `VGS` 下低 `VDS` 或指定电流点提取；
4. IDSS：`VGS=0`，高 `VDS` 下读漏电。

#### Step B：TID 等效参数

用 TCAD 中的固定电荷/界面陷阱代替真实辐照微观过程：

| 物理量 | TCAD 简化参数 | 预期趋势 |
|---|---|---|
| 正氧化层陷阱电荷 | `Not` 或 fixed oxide charge | nVDMOS Vth 负向漂移，IDSS 可能上升 |
| 界面态 | `Nit` / interface trap density | 迁移率/gm 下降，亚阈值变差，可抵消 Vth 负漂并导致 rebound |
| 退火 | 降低 `Not`，保持或增加 `Nit` | Vth 回漂；IDSS 未必恢复 |
| 场氧/终端电荷 | field oxide / termination 区域 fixed charge | IDSS 和 BVDSS 变化更明显 |

#### Step C：剂量点对应

不必强行把 Gy(Si) 精确换算成 `cm^-2` 电荷密度；先做趋势标定：

```text
dose = 0 -> Not0, Nit0
50% dose = 1e3 Gy(Si) -> Not1, Nit1
100% dose = 2e3 Gy(Si) -> Not2, Nit2
anneal 168 h / 100 °C -> NotA < Not2, NitA >= Nit2 或约等于 Nit2
```

当趋势与论文一致后，再用实测/文献数据拟合 Not/Nit 与剂量的映射。

### 6.2 两种偏置模式如何在 TCAD 中体现

| 论文偏置 | TCAD 边界条件 | 重点观察区 |
|---|---|---|
| 栅偏置 `VG=12 V`, D/S 同电位 | gate 加正压，drain/source/body 近似接地 | gate oxide、channel interface |
| 漏偏置 A/B：`VD=320/400 V`, G/S 同电位 | drain 高压，gate/source/body 接地 | drift region、junction edge、field oxide、termination |

如果只在沟道栅氧加 `Not/Nit`，漏偏置与栅偏置差异可能不明显。要复现论文中“漏偏置 Vth 漂移更大、IDSS 明显变化”，需要考虑器件内部电场分布：

- 沟槽底部/侧壁氧化层；
- p-body / n-epi 结边缘；
- 终端氧化层；
- 高压漏端附近 field oxide。

### 6.3 论文知识点到 Sentaurus 输出的映射

| 论文知识点 | Sentaurus 可观测量 | 判断标准 |
|---|---|---|
| Not 导致 nVDMOS Vth 负漂 | Id-Vg 曲线左移 | 恒流法 Vth 降低 |
| Nit 抵消/反弹 | 退火后 Vth 回漂或正漂，gm 下降 | `gm=max(dId/dVg)` 下降，SS 变差 |
| 场氧寄生漏电 | Off-state Id 增大 | `VGS=0, VDS=高压` 的 IDSS 增加 |
| BVDSS 稳定 | Breakdown 曲线变化小 | `Id=1 mA` 点 VDS 变化小 |
| RON 稳定 | 开态 Id-Vd 斜率变化小 | `VGS=10/12 V` 下 RON 变化小 |
| 电场重分布 | `ElectricField`, `ImpactIonization`, `eCurrentDensity` 分布 | 峰值是否靠近 trench gate / termination |

### 6.4 建议的最小实验矩阵

| 组别 | Not | Nit | 电荷位置 | 目的 |
|---|---:|---:|---|---|
| baseline | 0 | 0 | 无 | 得到未辐照 Id-Vg/RON/IDSS/BVDSS |
| oxide-only | low/med/high | 0 | gate oxide | 验证 Vth 负漂 |
| interface-only | 0 | low/med/high | channel interface | 验证 gm/SS 退化和 Vth 抵消 |
| combined | low/med/high | low/med/high | gate oxide + interface | 拟合论文 dose 趋势 |
| field-oxide | fixed | fixed | termination / field oxide | 验证 IDSS 和 BVDSS 敏感性 |
| anneal | Not 降低 | Nit 不降或略升 | 同上 | 模拟 100 °C / 168 h 后趋势 |

先跑这 6 组，比直接建立复杂辐射物理模型更稳。等趋势对了，再考虑 dose-rate、温度、时间常数。

---

## 7. 关键知识点层级图

```text
A. 器件结构层
   A1. vertical conduction: source -> channel -> drift -> drain
   A2. p-body / n-epi / n+ substrate 决定沟道、体二极管、击穿
   A3. trench gate 提高 channel density，降低低压 RON
   A4. deep p+ / TBOX / field plate 控制沟槽底部电场

B. 电学指标层
   B1. Vth: gate oxide + interface traps 最敏感
   B2. BVDSS: drift / termination / field distribution 主导
   B3. RON: Rch + Repi + Rjfet + package，TID 对总 RON 影响可能被稀释
   B4. IDSS: off-state leakage，常由 field oxide / edge parasitic path 放大
   B5. QG/QGD/Qrr: 决定高频开关与硬换流损耗

C. TID 物理层
   C1. 辐照产生 e-h pairs，电子快、空穴慢
   C2. 初始复合由 electric field 和 LET 决定
   C3. 空穴 hopping transport 后形成 oxide trapped charge Not
   C4. H+ transport / Si-H depassivation 形成 interface traps Nit
   C5. Not 与 Nit 在 nMOS 中方向相反，产生补偿和 rebound
   C6. 厚 field oxide 是现代 MOS TID 漏电主战场

D. 实验层
   D1. Co-60 gamma, 2e3 Gy(Si), 5e-1 Gy(Si)/s
   D2. gate-bias vs drain-bias 分别激励不同电场区域
   D3. 50% dose、full dose、168 h / 100 °C anneal 三阶段
   D4. 提取 Vth、BVDSS、RON、IDSS
   D5. 用 Not/Nit/field oxide charge sweep 对应 dose 和 anneal
```

---

## 8. 做实验时最容易踩的坑

1. **把 Vth 漂移当作全部 TID 损伤**：错误。IDSS 和 BVDSS 可能由 field oxide / termination 主导。
2. **只在主沟道加固定电荷**：只能解释 Id-Vg 左移，解释不了漏偏置和边缘漏电。
3. **忽略退火**：辐照后即时合格不代表长期合格，rebound 可能在退火/任务寿命中出现。
4. **把 RON 不变误解为器件无损伤**：高压 VDMOS 的 RON 可能由漂移区主导，沟道损伤被稀释。
5. **把 dose rate 当成独立物理量直接套用**：很多 apparent dose-rate effects 来自曝光时间和退火时间差异。
6. **忽略辐照源差异**：Co-60、X-ray、质子、alpha 的 charge yield / dose enhancement 不同。
7. **不检查收敛节点**：已有 `n18_des.log` 收敛警告，不能把异常节点画进趋势图当证据。
8. **过早做复杂模型**：先用固定 Not/Nit 复现实验趋势；趋势对不上时再加复杂陷阱动力学。

---

## 9. 术语速记

| 术语 | 含义 | 本项目中的用法 |
|---|---|---|
| VDMOS | vertical double-diffused MOSFET | 本项目核心器件 |
| trench VDMOS | 沟槽栅垂直 DMOS | VMware/Sentaurus 示例结构 |
| TID | total ionizing dose，总电离剂量 | 辐照损伤主线 |
| Not | oxide trapped charge，氧化层陷阱电荷 | TCAD 中用 fixed oxide charge 近似 |
| Nit | interface trap density，界面态密度 | TCAD 中用 interface traps 近似 |
| border traps | 可与硅交换电荷的近界面氧化层陷阱 | 慢阈值漂移、噪声、频率依赖 |
| rebound | Not 退火后 Nit 主导导致 Vth 反向/正向失效 | 100 °C / 168 h 退火筛查 |
| BVDSS | gate-source 短接时 drain-source 击穿电压 | 高压关断能力 |
| IDSS | gate-source 短接时 drain leakage | 场氧/终端漏电敏感指标 |
| RON / RDS(on) | 开态导通电阻 | 漂移区、沟道、封装共同决定 |
| QG / QGD | 总栅电荷 / Miller 电荷 | 开关损耗和栅漏工程指标 |
| TBOX | thick bottom oxide | 降低沟槽底部电场 |
| split gate / shielded gate | 接地 buried field plate 屏蔽 gate-drain 电容 | 降低 QGD/QG |
| superjunction | p/n 电荷平衡漂移区 | 降低漂移区电阻，突破硅极限 |
| RSO | RESURF stepped oxide | 用阶梯氧/场板实现类 charge balance |
| UIS | unclamped inductive switching | 感性负载关断雪崩能力 |
| FB-SOA | forward-bias safe operating area | 线性工作热安全区 |

---

## 10. 下一步最短实验路线

1. 用当前 `TID_des.cmd` 跑通并清理收敛异常节点，只保留可信 Id-Vg。
2. 写一个小脚本从 `.plt` 自动提取：Vth、gm、SS、RON、IDSS。
3. 做 `Not-only` 三点 sweep，确认 nVDMOS Vth 负漂。
4. 做 `Nit-only` 三点 sweep，观察 gm/SS 和 Vth 抵消。
5. 做 `Not+Nit` 组合，拟合 `0 / 1e3 / 2e3 Gy(Si)` 三个剂量点。
6. 把固定电荷从主栅氧扩展到 field oxide / termination，专门解释 IDSS。
7. 用 `Not 降低 + Nit 保持/增加` 模拟 `168 h, 100 °C` 退火。

这条路线足够覆盖四篇论文对当前 VDMOS TID 实验最有用的知识点；暂时不需要引入完整辐射输运或剂量率动力学模型。
