# IGBT Heavy-Ion/SEB 论文复现计划

## 当前状态

1. **已完成：IGBT 四温度关断态 BV 基线。** 已冻结首轮 deck、网格、曲线和汇总证据，详见 [`docs/changes/2026-07-10-igbt-four-temperature-bv/报告.md`](docs/changes/2026-07-10-igbt-four-temperature-bv/报告.md)。
2. **A01 已完成有界诊断并关闭。** 实际 2500 V、轨迹和 HeavyIon 电荷门均通过；但基准与半步核心网格在 60 ns 的 Collector 电流相差约 15.2%，局部雪崩场也显著分叉，故 `mesh_assessment=MESH_SENSITIVE`。
3. **低 LET 五档复盘支线已完成。** `LET=0.015/0.15` 的 thermal-steady/cold300 四条轨迹均覆盖至 60 ns；`0.015` 使用 40 ns 检查点和独立 recovery variant 越过原数值失败区，`0.15 cold300` 从 50 ns 检查点续跑。只读 PLT 提取、无重采样拼接、五档（共 10 条系列）汇总及图件均已完成，审计见 [`docs/changes/2026-07-13-igbt-seb-现有数据复盘/let_scan/LET扫描诊断报告.md`](docs/changes/2026-07-13-igbt-seb-现有数据复盘/let_scan/LET扫描诊断报告.md)。该支线固定为 `diagnostic_only`、`MESH_SENSITIVE`，不构成 SEB 阈值或因果结论。
4. **论文锚点未匹配。** `Wt_hi=0.1/0.2/0.5 µm`、300 K 冷态以及 Y=3.4/3.5/3.6 µm 对照均保持后期电流增长，未恢复论文 A01 约 10 ns 后衰减的趋势。A01 记为 `INDETERMINATE(time_window_short_and_mesh_sensitive)`，并附 `ANCHOR_MISMATCH`。
5. **A02 与完整扫描继续锁定。** 当前状态为 `NOT_ENTERED(anchor_gate_failed)`；若要比较 Avalanche 模型、`AnalyticTEP`、热边界或横向几何，需要新的明确批准，不能作为首次预注册锚点的静默修正。
6. **后续阶段：建立匹配 MOSFET。** 仅在 IGBT HeavyIon/SEB 阶段形成新的用户决策后，再建立受控 MOSFET 对照，开展静态场分布和必要的单粒子对比。

## 首轮基线边界

- 首轮 IGBT 四温度 BV 运行**未启用 HeavyIon**，不能作为 SEB 结果。
- 首轮 Collector 使用 `Rc=1e11`；外部目标 `4500 V` 不等于器件实际承压。
- 四个温度最终器件内压分别约为 `4410.60 / 1672.55 / 345.39 / 33.90 V`，因此不能把首轮最终 TDR 统一表述为“4.5 kV 内压结果”。

## 当前阶段入口与验收

- 完整技术规范：[`docs/changes/2026-07-11-igbt-seb-paper-reproduction/01-仿真计划.md`](docs/changes/2026-07-11-igbt-seb-paper-reproduction/01-仿真计划.md)
- 下一代理续接提示词：[`prompts/continue_igbt_seb.md`](prompts/continue_igbt_seb.md)
- 当前目标：A01 已以三字段门控关闭；A02–A04 继续锁定为 `NOT_ENTERED(anchor_gate_failed)`，等待新的阶段决策。
- 中期检查：[`docs/changes/2026-07-11-igbt-seb-paper-reproduction/06-中期检查报告.md`](docs/changes/2026-07-11-igbt-seb-paper-reproduction/06-中期检查报告.md)
- 剩余执行计划：[`docs/changes/2026-07-11-igbt-seb-paper-reproduction/07-剩余工作执行计划.md`](docs/changes/2026-07-11-igbt-seb-paper-reproduction/07-剩余工作执行计划.md)
- 当前禁止：立即建立 MOSFET、加入 TID `Not/Nit`、随意修改掺杂/几何、把普通数值失败解释为 SEB，或在 A01 未关闭时跳到后续锚点。

## 2026-07-15/16 最终交付冻结边界

- **2026-07-14 正式交付：**最终分享包以 IGBT 为主，MOSFET 仅为对照附录。准确口径是“四温度/多偏压案例跑通，且 298.15 K/550 V 下 baseline 与一次 track-refined 网格的 Tmax/端量/Emax/热点距离通过预设门”。这不是严格全局温度/网格收敛、普适阈值或商用 650 V 证明。
- **GZP：**最终包内含 `IGBT_SEB_20260714_Final_Continuation.gzp`，SHA-256 为 `30a49adba4b5e50b823e39d98f84915f4a02462044c33269f1280831bd0ffa2c`；由内嵌 7 案 run index、package manifest 和冻结产物哈希绑定 20260714 正式事实源。该工程已通过 `swbpack`、全新目录 `swbunpack`、Workbench W-2024.09 可编辑打开、SVisual 查看与提取探针。打包后未额外重跑 SDevice，因此只声明可作为后续获授权仿真的起点，不声明已完成打包后续跑。
- **低 LET：**只作 `diagnostic_only/MESH_SENSITIVE` 附录，不构成 SEB 阈值、热因果或普适机制结论。
- **650 V redesign：**2026-07-15 仍为 `PENDING`；新结构尚无有效静态/HeavyIon 数值，不能用旧 451.15 µm 结构替代商用 650 V 证据。
- **AI-assisted TCAD 材料：**定位为研究者约束下、有界自治且可审计的 AI-assisted/headless SSH TCAD 工作流；无人工基线、完整 token/tool-call 账本或重复实验，不宣称 AI 优于人工或完全自主。
- **交付资产：**最终版为 `share/IGBT_最终交付_v2_20260716_最终版/` 及同名 ZIP，包含唯一正式 IGBT GZP，由 `scripts/package_igbt_delivery_v2.py` 可重复生成，并由 `scripts/verify_delivery_v2.py` 完成清单、链接、ZIP CRC、解压后二次哈希和 GZP 结构验证；旧分享包与早期 v2 快照只读保留。
