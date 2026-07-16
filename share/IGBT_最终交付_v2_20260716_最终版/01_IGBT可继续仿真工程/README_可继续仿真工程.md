# IGBT 可继续仿真工程

本目录包含已生成并验证的 `IGBT_SEB_20260714_Final_Continuation.gzp`，以及 2026-07-14 7 个正式 IGBT 主案和 1 个 IGBT track-refined validation 的脱敏输入层。该 GZP 已通过 `swbpack`、全新目录 `swbunpack`、Workbench W-2024.09 可编辑打开、SVisual 查看和提取探针；打包后未重新执行 SDevice。

- [输入说明](inputs/case_matrix.csv)
- [GZP 验证记录](../00_交付说明/GZP验证记录.md)
- [正式结果](../02_正式结果/正式仿真结果报告.md)
- [最小复现说明](../05_最小复现材料/README_最小复现材料.md)

## 打开与继续仿真

1. 在合法授权的 Sentaurus W-2024.09 环境执行 `swbunpack -d <新目录> IGBT_SEB_20260714_Final_Continuation.gzp`；
2. 用 Workbench 打开解包后的 `IGBT_SEB_20260714_Final_Continuation` 工程；
3. 先核对内嵌 `delivery_metadata/package_manifest.json`、7 案 run index 和输入哈希；
4. 后续新运行必须使用新 attempt ID，按网格 → DC restart → transient 串行，SDevice 一线程并经自动核心租约；
5. 不把低 LET diagnostic_only 数据、MOSFET 对照或 650 V PENDING redesign 混入正式 IGBT 矩阵。

“可继续仿真”表示工程已可解包、可编辑打开并带有结构、热 restart、HeavyIon 与 SVisual 节点及冻结参考产物；本次交付收口未额外重跑 SDevice。
