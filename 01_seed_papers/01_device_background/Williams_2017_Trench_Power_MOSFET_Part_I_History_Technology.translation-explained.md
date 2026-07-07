# The Trench Power MOSFET: Part I—History, Technology, and Prospects 中文精读工作稿

> 用途：逐段保存“原文摘录 → 中文翻译 → 解释稿 → 术语”。
> 注意：为便于学习，原文只保留当前阅读段落的必要摘录，不替代 PDF 原文。

## 进度
- PDF: `Williams_2017_Trench_Power_MOSFET_Part_I_History_Technology.pdf`
- 当前进度：第 1 页，标题/摘要/关键词/Introduction 开头

## 01 — 标题、摘要、关键词、引言开头

### 原文摘录
The Trench Power MOSFET: Part I—History, Technology, and Prospects

Abstract — The historical and technological development of the ubiquitous trench power MOSFET (or vertical trench VDMOS) is described. Overcoming the deficiencies of VMOS and planar VDMOS, trench VDMOS innovations include pioneering efforts in reactive ion etching and oxidation of the silicon trench gate, polysilicon fill and recessed etchback, unit cell and distributed voltage clamping to protect the trench gate, and scaling active cells to high densities using deep submicron fabrication. Thereafter, gate–drain engineered trench VDMOS improved high-frequency switching capability with lower gate charge utilizing nonuniform gate oxides, field shaping, and charge balancing (superjunction, RSO) methods. The recent adaptation of trench gates in wide bandgap unipolar devices is also described.

Index Terms — Avalanche breakdown, bipolar, bipolar junction transistor (BJT), cell density, charge balance, channel density A/W, deep p+, double diffusion, epitaxial layer, gate charge (QG, QGD), parasitic JFET, planar, power device packaging, power dissipation, power MOSFET, power transistor, punchthrough, reach-through, RSO, silicon, specific on-resistance (RDSA), split trench gate, super junction, stepped gate, trench etch, trench thick bottom oxide (TBOX), trench VDMOS, V(br), VMOS, voltage clamping, wide bandgap (WBG).

AGAINST all expectations in its technological development and commercialization, the trench power MOSFET ultimately emerged as one of the world’s most ubiquitous semiconductor devices.

### 中文翻译
**沟槽功率 MOSFET：第一部分——历史、技术与前景**

**摘要**——本文描述了应用极其广泛的沟槽功率 MOSFET（也称垂直沟槽 VDMOS）的历史和技术发展。为克服 VMOS 与平面 VDMOS 的缺陷，沟槽 VDMOS 的创新包括：硅沟槽栅的反应离子刻蚀与氧化工艺探索；多晶硅填充与回刻凹陷；用单元级和分布式电压钳位保护沟槽栅；以及利用深亚微米制造工艺把有源单元缩放到高密度。随后，通过栅—漏工程化设计，沟槽 VDMOS 利用非均匀栅氧、场形调控和电荷平衡方法（如超结、RSO）降低栅电荷，并提升高频开关能力。文章还介绍了沟槽栅在宽禁带单极器件中的近期应用。

**关键词**——雪崩击穿、双极型、双极结型晶体管（BJT）、单元密度、电荷平衡、沟道密度 A/W、深 p+、双扩散、外延层、栅电荷（QG、QGD）、寄生 JFET、平面结构、功率器件封装、功耗、功率 MOSFET、功率晶体管、穿通、reach-through、RSO、硅、比导通电阻（RDSA）、分裂沟槽栅、超结、阶梯栅、沟槽刻蚀、沟槽厚底氧（TBOX）、沟槽 VDMOS、击穿电压 V(br)、VMOS、电压钳位、宽禁带（WBG）。

**引言开头**——尽管在技术发展和商业化过程中曾经不被看好，沟槽功率 MOSFET 最终仍成为世界上最普遍使用的半导体器件之一。

### 解释稿
这篇文章不是单纯介绍某一个器件结构，而是在回答一个历史问题：**沟槽功率 MOSFET 为什么能成为主流功率器件？**

摘要里已经给出全文主线：

1. **先有问题**：早期 VMOS 和平面 VDMOS 有结构或性能缺陷。
2. **再有工艺突破**：沟槽刻蚀、沟槽氧化、多晶硅填充、回刻，这些让“在垂直沟槽侧壁上做可靠 MOS 栅”成为可能。
3. **然后解决可靠性**：沟槽栅容易被高电场损伤，所以需要电压钳位、单元设计和分布式保护。
4. **再继续性能优化**：降低 `QG` / `QGD`，提高高频开关能力，方法包括非均匀栅氧、场板/场形调控、超结和 RSO。
5. **最后扩展材料体系**：沟槽栅技术也被迁移到 SiC、GaN 等宽禁带器件。

对你的 VDMOS/TID 研究而言，这篇的价值主要是建立“器件结构—工艺—电场—可靠性—性能指标”的背景框架。后面读到辐照、氧化层陷阱、电荷累积、阈值漂移时，这些结构背景会很有用。

### 术语速记
- **Trench Power MOSFET / vertical trench VDMOS**：沟槽功率 MOSFET，电流主要垂直流动，栅位于刻蚀出的沟槽侧壁。
- **VMOS**：早期 V 形槽功率 MOSFET，是沟槽 VDMOS 的前身之一。
- **Planar VDMOS**：平面栅垂直双扩散 MOSFET，栅在硅片表面。
- **RIE, reactive ion etching**：反应离子刻蚀，用于形成陡直沟槽。
- **Gate charge QG / QGD**：栅电荷 / 栅漏电荷，影响开关速度与驱动损耗。
- **Specific on-resistance RDSA**：比导通电阻，通常用于比较单位面积导通能力。
- **WBG**：wide bandgap，宽禁带半导体，如 SiC、GaN。

### 本段要抓住的问题
- 为什么早期大家怀疑沟槽栅 MOSFET 不可靠？
- 沟槽结构相比平面 VDMOS 到底改善了什么？
- 这些改进是否以新的可靠性问题为代价？