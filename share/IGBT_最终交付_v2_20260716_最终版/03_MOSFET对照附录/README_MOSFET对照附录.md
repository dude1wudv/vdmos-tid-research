# MOSFET 对照附录

MOSFET 是与 IGBT 冻结历史模型匹配的派生对照，不是商用 SJ MOSFET 证明，也不改变 IGBT 主交付口径。它不计入 7 个 IGBT 正式事实源。

- [2.1 ns MOSFET 数值行](data/MOSFET_T298_V550_L15_2ns.csv)
- [MOSFET 图数据](data/MOSFET_2ns_figure_data.csv)
- [track-refined 网格门](data/MOSFET_track_refined_mesh_gate.csv)
- [track-refined 网格 JSON](data/MOSFET_track_refined_mesh_gate.json)
- [SVisual 晶格温度图](figures/mosfet_lattice_temperature_post2ns_svisual.png)
- [IGBT/MOSFET 数值比较图](figures/campaign_2ns_numerical_comparison.png)
- [IGBT/MOSFET 空间场对照](figures/lattice_temperature_post2ns_svisual_comparison.png)

热点距离来自 sidecar 数值计算，不从图像估计。不得外推为所有 MOSFET 热点更近/更远氧化层，也不得外推为 TID 永久损伤。
