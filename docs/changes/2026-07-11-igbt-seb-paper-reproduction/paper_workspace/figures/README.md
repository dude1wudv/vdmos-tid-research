# 图件登记

本目录只登记论文图件，不复制原始 PDF、TDR、PLT、完整日志或私有运行路径。当前公开图片位于上级项目的 `figures/`，正式排版前再按投稿格式统一重绘。

## 当前图件

| 图件 ID | 当前文件 | 来源 | 当前可支持的结论 | 状态与限制 |
|---|---|---|---|---|
| F01 | [smoke_heavy_ion_generation_100p2ps.png](../../figures/smoke_heavy_ion_generation_100p2ps.png) | S00 attempt02；ART0002；E0007 | 100.2 ps 附近存在非零 HeavyIonGeneration，轨迹方向与位置符合首轮映射 | 可用于初稿；仅为输入链路 smoke，不作 SEB 分类 |
| F02 | [a01_partial_transients.png](../../figures/a01_partial_transients.png) | A01 attempt01/03；ART0003；E0014 | 两个早期 attempt 的部分 Ic/Tmax 演化 | 历史阶段图；不作为最终 A01 曲线 |
| F03 | [attempt_failure_recovery_funnel.png](../../figures/attempt_failure_recovery_funnel.png) | ART0004；生成于 E0015 附近 | 展示早期尝试、失败和恢复路径 | 历史工作流示意，不代表 28 个运行数据行的最终统计 |
| F04 | [tuning_outcomes.png](../../figures/tuning_outcomes.png) | ART0005；T0001-T0004 | 展示早期调优快照 | 图内旧 `PENDING` 已被当前账本闭合；不得作最终调优统计 |
| F05 | [heavyion_charge_closure.png](../../figures/heavyion_charge_closure.png) | ART0006；E0020 | 基准 `Wt_hi=0.1 µm` 的完整脉冲电荷通过 5% 门 | 可用于输入守恒结果 |
| F06 | [a01_solver_variant_physics.png](../../figures/a01_solver_variant_physics.png) | ART0007；E0025 | solver 候选保持同一增长趋势 | 必须与性能图共同解释 |
| F07 | [a01_solver_variant_performance.png](../../figures/a01_solver_variant_performance.png) | ART0008；E0025 | B1/B2/B3 均未达到接受门 | 不外推为通用 Sentaurus 性能规律 |
| F08 | [a01_mesh_sensitivity.png](../../figures/a01_mesh_sensitivity.png) | ART0018；E0031 | 50/60 ns Ic 未收敛 | 结论为 `MESH_SENSITIVE` |
| F09 | [a01_field_evidence.png](../../figures/a01_field_evidence.png) | ART0021；E0031 | 40/60 ns 局部雪崩与电势代理分叉 | 不作 SEB 分类 |
| F10 | [a01_wt_hi_sensitivity.png](../../figures/a01_wt_hi_sensitivity.png) | ART0019；E0035 | 展宽改变幅值但未逆转增长 | 三个宽度完整展示，禁止选择性报告 |
| F11 | [a01_physical_diagnostics.png](../../figures/a01_physical_diagnostics.png) | ART0020；E0039 | 冷态与局部位置诊断未恢复论文衰减 | Y=3.4/3.6 µm 不等于正式位置扫描 |

## 初稿采用

`manuscript.md` 当前仅嵌入 F01。F02-F04 作为候选图登记，不在数据状态闭合前承担最终定量结论。

## 待生成图件

| 计划 ID | 图件 | 进入条件 | 最低数据要求 |
|---|---|---|---|
| P01 | 闭合后的尝试谱系与失败恢复流程图 | 同步 E0018 与 tuning closure | event ID、parent run、状态、决策理由、wall time |
| P02 | A01 全 attempt 的 Ic(t)/Tmax(t) 对比 | A01 诊断阶段关闭 | 统一时间轴、实际 VCE、完整状态和停止原因 |
| P03 | 四锚点 Ic(t)/Tmax(t) 对比 | A01-A04 均结束 | 四锚点完整曲线、1680/2500 K 穿越时间、分类 |
| P04 | 关键时刻机理图 | 至少一个有效 SEB 与一个有效 NO_SEB case | ElectricField、SpaceCharge、Potential、ImpactIonization、p-body/n+ emitter 电势差 |
| P05 | `VCE × LET` 状态图 | 四锚点关系通过 | 离散扫描结果与 `SCREENED_NOT_RUN` 标记 |
| P06 | 三位置对照图 | 阈值稳定 | Y=3.05/3.5/4.2 µm 同条件数据 |
| P07 | 网格复核图 | A03 主结果完成 | 基准网格与轨迹核心半步网格的同时间点比较 |

## 图注规则

1. 图注必须写明 `case_id`、`attempt_id`、实际 VCE、LET、轨迹位置和状态。
2. 阶段图必须显式标注 `PARTIAL` 或 `INDETERMINATE`。
3. 数值失败、时间窗不足和物理温度终止使用不同视觉编码。
4. 每张发布图必须能追溯到公开 CSV 和 `artifact_manifest.csv`；私有原件只登记哈希。
5. 四锚点未通过前，不绘制会暗示阈值已确定的热图或相边界。