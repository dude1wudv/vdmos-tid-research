# IGBT SEB 方法论文工作区

## 论文定位

本工作区用于撰写一篇以“预注册、有界自治、可审计的 TCAD 论文复现方法”为核心的中文方法案例论文。IGBT HeavyIon/SEB 仿真是验证案例，不是当前已经完成的物理复现结论。

暂定题目：

> 有界自治 TCAD 的预注册可审计复现方法：IGBT 重离子单粒子烧毁案例的阶段性验证与偏差诊断

- 当前版本：`v0.2-a01-diagnostic-closure`
- 证据截止事件：`E0044`
- 当前物理状态：A01 为 `INDETERMINATE(time_window_short_and_mesh_sensitive)`，并附 `ANCHOR_MISMATCH` 与 `MESH_SENSITIVE`；A02–A04 为 `NOT_ENTERED(anchor_gate_failed)`。

## 文件职责

| 文件 | 职责 |
|---|---|
| `manuscript.md` | 中文论文主稿；只写当前证据支持的内容，未完成结果保留占位 |
| `evidence_map.md` | 主张、证据、证据等级、使用边界和待补实验的映射 |
| `references.bib` | 已核验参考文献；不保存未经核验或仅凭记忆生成的条目 |
| `figures/README.md` | 图件来源、可用范围、时效性和替换条件登记 |

## 事实源优先级

若不同文档记录的运行状态冲突，按以下顺序取值：

1. 当前可机读账本：`../data/case_summary.csv`、`../data/codex_events.csv`。
2. 当前公开产物清单：`../data/artifact_manifest.csv`。
3. 冻结预注册：`../02-预注册与环境快照.md`。
4. 阶段报告：`../03-逐次运行记录.md` 至 `../06-中期检查报告.md`。
5. 初始计划与续接提示词。

因此，A01 当前使用 `data/a01_diagnostic_gate_summary.csv` 与事件 E0040 的三字段闭合：`INDETERMINATE(time_window_short_and_mesh_sensitive)`、`ANCHOR_MISMATCH`、`MESH_SENSITIVE`。Attempt04 的 `81.933 ns`、`395.229 K`、`3.172e-3 A/µm`、`7.931 W/µm` 和 876 次 Newton 重试仍是最长基准网格观察值；中期报告中的 `78.304 ns` 仅是更早的运行中快照。

`tuning_steps.csv` 已闭合到 T0016，`codex_events.csv` 已闭合到 E0044。历史阶段图中的 `PENDING` 标记不得作为最终调优统计。

## 当前允许的主张

- 工作流在预注册的物理参数与决策边界内保留了尝试谱系和负结果。
- 100 V smoke 验证了 HeavyIon 输入、实际偏压、瞬态生成率和轨迹方向。
- 工作流识别并拒绝了普通 Plot TDR restart，验证了 solver-native `Save/Load`。
- 本案例中的 8 线程运行出现负加速；该观察不外推为 Sentaurus 的一般性能规律。
- A01 以 `INDETERMINATE` 物理分类关闭，且已证明与参考论文的电流趋势不匹配。
- HeavyIon 完整脉冲电荷在 `Wt_hi=0.1/0.2/0.5 µm` 下均通过 5% 门。
- 半步核心网格在 50/60 ns 的端电流和局部雪崩场未收敛，因此网格评估为 `MESH_SENSITIVE`。
- `Wt_hi`、300 K 冷态和 Y=3.4/3.6 µm 对照改变幅值但均未逆转增长趋势。

## 当前禁止的主张

- 四个 SEB 锚点已经复现。
- A01 已被判定为 `NO_SEB`、`SEB_ONSET` 或 `SEB_CONFIRMED`。
- 已获得可发布的 `VCE × LET` 阈值、位置敏感性或网格无关性结论。
- Codex 普遍优于人工或其他代理。
- 自动调优已经证明减少总耗时或无效运行。
- 四温度 BV pilot 的外部 `4500 V` 等同于器件实际承受 `4.5 kV`。

## 更新规则

1. 新结果先写入 case/event/artifact 账本，再更新论文。
2. A01 已关闭但锚点门失败时，不填充 A02-A04 的结果占位。
3. 四锚点未通过时，不填充阈值扫描和位置敏感性结论。
4. 每个正文数值必须能回溯到公开 CSV、冻结 deck 哈希或阶段报告。
5. 原始 PDF、TDR、PLT、完整日志、许可证信息和私有运行路径不复制到本目录。