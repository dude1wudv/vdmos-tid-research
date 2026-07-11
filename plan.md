# IGBT Heavy-Ion/SEB 论文复现计划

## 当前状态

1. **已完成：IGBT 四温度关断态 BV 基线。** 已冻结首轮 deck、网格、曲线和汇总证据，详见 [`docs/changes/2026-07-10-igbt-four-temperature-bv/报告.md`](docs/changes/2026-07-10-igbt-four-temperature-bv/报告.md)。
2. **当前阶段：论文 HeavyIon/SEB 锚点复现。** 先完成低偏压语法 smoke，再依次验证四个论文锚点；未通过前不展开批量扫描。
3. **下一阶段：受控 VCE、LET 和入射位置阈值研究。** 仅在锚点定性关系复现后执行离散阈值搜索、位置对照和关键点网格复核。
4. **后续阶段：建立匹配 MOSFET。** 在 IGBT HeavyIon/SEB 阶段完成后，再建立受控 MOSFET 对照，开展静态场分布和必要的单粒子对比。

## 首轮基线边界

- 首轮 IGBT 四温度 BV 运行**未启用 HeavyIon**，不能作为 SEB 结果。
- 首轮 Collector 使用 `Rc=1e11`；外部目标 `4500 V` 不等于器件实际承压。
- 四个温度最终器件内压分别约为 `4410.60 / 1672.55 / 345.39 / 33.90 V`，因此不能把首轮最终 TDR 统一表述为“4.5 kV 内压结果”。

## 当前阶段入口与验收

- 完整技术规范：[`docs/changes/2026-07-11-igbt-seb-paper-reproduction/01-仿真计划.md`](docs/changes/2026-07-11-igbt-seb-paper-reproduction/01-仿真计划.md)
- 下一代理续接提示词：[`prompts/continue_igbt_seb.md`](prompts/continue_igbt_seb.md)
- 当前目标：在冻结 IGBT 基线上加入 Sentaurus HeavyIon，按顺序复现 `2500 V + LET 15`、`3000 V + LET 10`、`3000 V + LET 15`、`3200 V + LET 15` 四个锚点。
- 当前禁止：立即建立 MOSFET、加入 TID `Not/Nit`、随意修改掺杂/几何、把普通数值失败解释为 SEB。
