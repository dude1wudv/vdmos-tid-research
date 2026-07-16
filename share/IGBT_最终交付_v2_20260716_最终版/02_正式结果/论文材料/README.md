# AI 助理操作计算机完成 TCAD 仿真：论文材料包

## 定位与范围

本材料包支持一篇**方法学案例研究**：研究者预先冻结目标、物理模型边界、可调整项与停止规则；Codex 在该边界内通过无界面 SSH 调度 Sentaurus、记录诊断、保存失败与执行门；研究者保留范围批准、物理解释和最终责任。本包不把案例描述为“完全自主”、不主张 AI 独立复现 SEB、无人参与或优于人工。

**交付边界（冻结）：**2026-07-14 正式结果的准确口径是“四温度/多偏压案例跑通，且 298.15 K/550 V 下 baseline 与一次 track-refined 网格的 Tmax/端量/Emax/热点距离通过预设门”。这不是严格全局温度/网格收敛、普适阈值或商用 650 V 证明。低 LET 支线只作 `diagnostic_only/MESH_SENSITIVE` 附录；2026-07-15 650 V redesign 仍为 `PENDING`。

两段证据必须分开解释：

- **2026-07-11**：单个 2500 V/LET 15 IGBT 锚点的有界诊断。28 个尝试均已结束；最终是 `INDETERMINATE + ANCHOR_MISMATCH + MESH_SENSITIVE`，不是 SEB 成功复现。
- **2026-07-14**：冻结历史匹配结构的 7 个 IGBT 短瞬态生产主案，热稳态与 2.1 ns sidecar 均为 **7/7 PASS**；另有 1 个 MOSFET 派生对照，仅作附录，不计入 IGBT 正式事实源。该交付验收不改变前述 7/11 的 1 µs SEB 分类。

## 目录

- [manuscript/中文论文初稿.md](manuscript/中文论文初稿.md)：可编辑正文与作者待补内容。
- [manuscript/AI使用披露.md](manuscript/AI使用披露.md)：独立的 AI 角色、研究者约束和不声称边界。
- [evidence-map/证据链与主张审计.md](evidence-map/证据链与主张审计.md)：主张、证据等级和禁止外推。
- [dataset-codebook/数据字典.md](dataset-codebook/数据字典.md)：公开数据模式、枚举、外键、来源及隐私边界。
- [data-public/](data-public/)：脱敏且小型的结构化数据；不含 TDR/PLT/SAV、原始会话或凭据。
  - [lineage.csv](data-public/lineage.csv)：把 event/attempt/run/artifact/SHA/claim 关系与阶段边界统一到一张表，缺失字段保留 `NA`。
- [figures/](figures/)：新绘制的流程与审计图（SVG）及图规格。
- [tables/](tables/)：论文表的可编辑 Markdown 规格。
- [environment/执行环境与资源边界.md](environment/执行环境与资源边界.md)：SSH、单写者、租约与 affinity 的证据范围。
- [private-restricted-index/受限材料索引.md](private-restricted-index/受限材料索引.md)：仅说明类别、访问级别和哈希/审计边界。

## 溯源来源

材料使用 2026-07-09 reference workflow 的顺序约束、2026-07-11 预注册/`codex_events`/`tuning_steps`/`case_summary` 账本、2026-07-14 正式矩阵和 `local_runtime/tcad_projects/igbt_mosfet_seb_paper_20260714` 的 sidecar；执行层对应 `scripts/run_igbt_seb_case.ps1`、自动核心租约策略、`codex-workflows` 与 `sentaurus-vm-runner`。上述来源并不补足人工基线、完整 token 账本或重复实验。

主链是 `event_id → attempt_id/run_id → artifact_id → sha256 → claim_id`。链接写入 [artifact-links.csv](data-public/artifact-links.csv)，而不同日期的阶段和验收口径由 [stage-evidence.csv](data-public/stage-evidence.csv) 显式区分。`run_registry.csv` 仅有一条 legacy 记录，不能据此估算完整运行数、租约合规率、并发度或 wall time 总体分布。

## 数据与版权

公开层仅转录小型 CSV/JSON 可验证事实与派生计数；路径均为相对或类别名。官方 Sentaurus 安装、手册、许可证信息、参考论文 PDF、TDR/PLT/SAV、完整 stdout/stderr 和会话轨迹均未再发布。引用计划见 [manuscript/citation-plan.md](manuscript/citation-plan.md)。

## 使用方法

以 CSV 为图表数值源，SVG 是可编辑的图形规格，不从截图反算数据。执行 [验证记录.md](验证记录.md) 的检查后可作为投稿材料起点；外部相关工作、作者身份、资助/伦理、研究者决策日志和独立复算仍须作者补齐。