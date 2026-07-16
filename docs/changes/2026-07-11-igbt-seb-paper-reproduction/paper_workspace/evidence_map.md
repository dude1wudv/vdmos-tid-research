# 主张—证据映射

## 1. 使用规则

本文把材料分为四类：

- **参考论文事实**：Peng 等（2024）明确给出的器件参数、入射条件、锚点和机理描述。
- **项目固定假设**：为把论文描述映射到 Sentaurus 而设置、但未由论文完整披露的参数。
- **本项目直接证据**：case/event 账本、CSV、PLT/TDR 派生结果、日志和哈希。
- **解释或建议**：由直接证据推导的有限解释，不能冒充已验证物理事实。

证据等级：

| 等级 | 含义 | 典型材料 |
|---|---|---|
| E1 | 当前、可机读、可定位到具体 attempt 的直接证据 | `case_summary.csv`、`codex_events.csv` |
| E2 | 可复核的派生产物或冻结原始产物索引 | 图件、artifact manifest、deck/mesh SHA-256 |
| E3 | 阶段性综合记录 | 预注册、逐次记录、中期检查、结果报告 |
| E4 | 外部参考事实 | 原论文正文及 DOI 元数据 |

发生状态冲突时，当前 E1 运行闭合记录优先于较早 E3 阶段叙述；参考论文事实与本项目结果不得互相替代。

## 2. 核心主张

| ID | 拟写主张 | 状态 | 证据 | 等级 | 使用边界 |
|---|---|---|---|---|---|
| C01 | SEB 案例在首次 HeavyIon 运行前冻结了环境、基线哈希、锚点顺序、分类规则、允许调整和停止条件 | 可写 | `../02-预注册与环境快照.md`；`../data/codex_events.csv` 的 E0001-E0003 | E1+E3 | 只能说明本项目完成了预注册，不等于第三方注册平台认证 |
| C02 | 公开事件账本记录了计划边界、失败恢复与范围决策 | 可写但需限定 | `../data/codex_events.csv`；`../05-Codex自动调优研究记录.md` | E1+E3 | 纠错性人工参数干预为 0；另有 1 次用户批准的有界范围决策，不能合并为“完全无人参与” |
| C03 | 100 V smoke 验证了 HeavyIon 语法、实际偏压、脉冲期非零生成率和约 0-49.08 µm 的入射轨迹 | 可写 | `case_summary.csv` 的 S00 attempt02；E0007；`../figures/smoke_heavy_ion_generation_100p2ps.png` | E1+E2 | smoke 不作任何 SEB 分类 |
| C04 | 仅增加 strike-time snapshot 能关闭第一次 smoke 错过脉冲的证据缺口 | 可写 | E0005-E0007；`tuning_steps.csv` 的 T0001 | E1 | 调整的是输出调度，不代表改变了物理响应 |
| C05 | 普通 Plot TDR 不能在本案例中替代一致的求解器 restart | 可写 | A01 attempt02；E0010-E0011；T0002 | E1 | 限定为当前热电耦合配置和该 Plot TDR 路径 |
| C06 | solver-native `Save/Load` 成功恢复 2500 V 状态并进入瞬态 | 可写 | A01 attempt03/04；E0012、E0015-E0018 | E1+E2 | “成功恢复”不等于物理锚点复现成功 |
| C07 | 8 线程在 A01 attempt03 后期出现负加速，回到单线程后早期单步更快 | 可写但不可作强因果比较 | `../03-逐次运行记录.md`；`../05-Codex自动调优研究记录.md`；T0003/T0004 | E1+E3 | 两组数据不处于完全相同的时间区间，不外推为通用线程规律 |
| C08 | A01 attempt04 在 81.933 ns 正常冻结并中断，因时间窗不足和数值刚性维持 `INDETERMINATE` | 可写 | `case_summary.csv` 最后一行；E0018 | E1 | 不得改写为 `NO_SEB`、`SEB_ONSET` 或 `SEB_CONFIRMED` |
| C09 | A01 所有受控变体到 60 ns 均保持增长，与参考论文 2500 V、LET 15 峰后衰减描述不匹配 | 可写为偏差观察 | `../data/a01_wt_hi_sensitivity.csv`；`../data/a01_thermal_initial_state_sensitivity.csv`；`../data/a01_position_sensitivity.csv`；Peng 2024 图 9/正文 | E1+E4 | 不能断言论文错误，也不能把增长直接判为真实 SEB |
| C10 | 四温度 BV 数据只能作为回顾性结构与证据链 pilot | 可写 | `../../2026-07-10-igbt-four-temperature-bv/报告.md`；私有 `summary.csv` | E2+E3 | Collector 使用 `Rc=1e11`，外部 4500 V 不能当作统一器件内压 |
| C11 | 四个论文锚点已复现 | 不可写 | A01 为 `ANCHOR_MISMATCH`；A02-A04 未进入 | E1 | 当前锚点门已失败，不计算复现率 |
| C12 | 自动调优减少了总耗时或优于人工策略 | 不可写 | 无同条件对照、无人工基线、无重复实验 | 尚无 | 若保留效率主张，需另行预注册对照实验 |
| C13 | 已获得 SEB 阈值、正式位置效应或网格无关结论 | 不可写 | `../data/a01_diagnostic_gate_summary.csv` | E1 | A01 为 `MESH_SENSITIVE`；Y=3.4/3.6 µm 仅是局部诊断；扫描未进入 |
| C14 | A01 HeavyIon 完整脉冲电荷在三个 `Wt_hi` 下均通过 5% 门 | 可写 | `../data/heavyion_charge_audit.csv`；`../data/a01_wt_hi_sensitivity.csv`；E0020/E0033/E0035 | E1 | 仅关闭输入电荷明显错误，不证明局部沉积模型唯一正确 |
| C15 | 半步核心网格在 50/60 ns 端电流及局部雪崩证据上未收敛 | 可写 | `../data/a01_meshhalf_transient_comparison.csv`；`../data/a01_field_evidence.csv`；E0031 | E1 | 结论是 `MESH_SENSITIVE`，不是 SEB 分类 |
| C16 | `Wt_hi`、冷态与局部位置诊断改变晚时刻幅值但未恢复论文衰减 | 可写 | `../data/a01_wt_hi_sensitivity.csv`；`../data/a01_thermal_initial_state_sensitivity.csv`；`../data/a01_position_sensitivity.csv` | E1 | 不允许选择最接近论文的单一变体替换基准 |

## 3. 关键数值索引

| 数值 | 当前值 | 来源 | 正文用途 |
|---|---:|---|---|
| S00 实际 VCE | 100.0 V | `case_summary.csv` S00 attempt02 | 输入链路验证 |
| S00 生成率峰值 | `6.8313e29 cm^-3 s^-1` | S00 attempt02、E0007 | smoke 结果 |
| S00 轨迹深度 | 约 `0-49.08 µm` | S00 attempt02、E0007 | 入射方向与长度核查 |
| 正式网格 | 31,769 points；62,720 elements | E0008、中期检查 | 案例实现 |
| A01 attempt04 实际 VCE | 2500 V | `case_summary.csv` | 偏压验收 |
| A01 attempt04 终止时间 | `81.933 ns` | `case_summary.csv`、E0018 | 最新阶段状态 |
| A01 attempt04 Tmax | `395.229 K` | `case_summary.csv`、E0018 | 未达到 1680 K |
| A01 attempt04 峰值 Ic | `3.172e-3 A/µm` | `case_summary.csv`、E0018 | 阶段趋势 |
| A01 attempt04 峰值功率 | `7.931 W/µm` | `case_summary.csv`、E0018 | 阶段趋势 |
| A01 attempt04 Newton 重试 | 876 | E0018 | 数值刚性 |
| A01 基准完整脉冲电荷 | `8.067321 pC`；`+3.7598%` | `heavyion_charge_audit.csv` | 输入守恒门通过 |
| 半步网格 50/60 ns Ic 差异 | `-6.19%/-15.23%` | `a01_meshhalf_transient_comparison.csv` | 网格敏感 |
| `Wt_hi=0.2/0.5 µm` 电荷偏差 | `+4.340%/+4.589%` | `a01_wt_hi_sensitivity.csv` | 均通过 5% 门 |
| A01 最终三字段 | `INDETERMINATE`；`ANCHOR_MISMATCH`；`MESH_SENSITIVE` | `a01_diagnostic_gate_summary.csv`；E0040 | A01 门控 |

## 4. 参考论文锚点

| 锚点 | 参考论文描述 | 本项目当前状态 |
|---|---|---|
| A01: 2500 V + LET 15 | 约 10 ns 达峰后衰减，无 SEB | `INDETERMINATE(time_window_short_and_mesh_sensitive)`；`ANCHOR_MISMATCH`；`MESH_SENSITIVE` |
| A02: 3000 V + LET 10 | 不导致 SEB | `NOT_ENTERED(anchor_gate_failed)` |
| A03: 3000 V + LET 15 | 持续电流与温升，导致 SEB | `NOT_ENTERED(anchor_gate_failed)` |
| A04: 3200 V + LET 15 | 约 200 ns 时 Tmax 超过 2500 K | `NOT_ENTERED(anchor_gate_failed)` |

参考来源：Peng et al. (2024), figures 9-11, DOI `10.1088/1361-6641/ad634c`。

## 5. 待补证据

1. A02–A04 未进入；若重开锚点链，必须有新的阶段决策并继续严格串行。
2. 当前没有有效 SEB 与 NO_SEB 配对，不能形成发布级机理对照或阈值图。
3. Avalanche、迁移率、`AnalyticTEP`、热边界与横向几何属于新的模型偏离研究，需另行预注册。
4. 若主张效率收益，增加同机器、同时间窗、同产物门槛的固定策略或人工审计对照。

## 6. 历史账本差异的闭合

- 早期 `78.304 ns` 与 `PENDING` 叙述保留为阶段快照；当前 case/tuning/event 账本已分别闭合到 28 个运行数据行、T0016 与 E0044。
- PA01 的并行探索仅是历史提案，未启动 A02/A04；当前严格串行事实不变。
- 基准 50 ns 值已从 attempt07 自身 PLT 相邻点重新插值，旧 `4.473384%` 差异被更正为 `-6.18748%`；场证据已提取，最终评估为 `MESH_SENSITIVE`。