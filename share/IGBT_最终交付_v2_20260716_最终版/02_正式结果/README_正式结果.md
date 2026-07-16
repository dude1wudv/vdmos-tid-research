# 2026-07-14 正式 IGBT 结果

正式事实源是 7 个 IGBT 唯一案例：四温度线 4 案与 298.15 K 下 500/525/550/575 V 偏压线 4 案共享 T298/V550，因此唯一案数为 7。每个 IGBT 案的热稳态/DC restart 与精确 2.1 ns sidecar 均 PASS（7/7）。

MOSFET 只有 1 个结构匹配派生对照，已移至 `03_MOSFET对照附录/`；它不计入 IGBT 正式事实源，也不代表商用 SJ MOSFET。

交付口径：四温度/多偏压案例跑通，且 298.15 K/550 V 下 baseline 与一次 track-refined 网格的 Tmax、端量、Emax、热点距离通过预设门。这里的通过不是严格全局收敛、普适阈值或商用 650 V 证明。

- [正式结果报告](正式仿真结果报告.md)
- [7 案验收表](data/case_acceptance.csv)
- [2.1 ns IGBT 数值比较](data/campaign_2ns_comparison.csv)
- [局部 track-refined IGBT 网格门](data/mesh_track_refined_comparison.csv)
- [IGBT SVisual 晶格温度图](figures/igbt_lattice_temperature_post2ns_svisual.png)
