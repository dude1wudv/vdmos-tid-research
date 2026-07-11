# IGBT Heavy-Ion/SEB 项目续接提示词

继续推进 `E:\VDMOS_TID_Research` 的 IGBT 单粒子烧毁项目。

开始前依次阅读：

1. `AGENTS.md`
2. `plan.md`
3. `docs/changes/2026-07-11-igbt-seb-paper-reproduction/01-仿真计划.md`
4. `docs/changes/2026-07-10-igbt-four-temperature-bv/报告.md`
5. `local_runtime/tcad_projects/igbt_seb_sst_39_8_085011/extracted/paper_text.txt`
6. `local_runtime/tcad_projects/igbt_seb_sst_39_8_085011/paper/sst_39_8_085011.pdf`
7. `local_runtime/igbt_bv_first_round_run/` 中的冻结 deck、网格和汇总文件

## 目标

在现有论文参数 IGBT 上加入 Sentaurus HeavyIon 模型，先完成论文四个锚点的可复算验证，再决定是否展开阈值扫描。不要立即建立 MOSFET，也不要加入 TID `Not/Nit`。

## 执行约束

- 使用 `sentaurus-vm-runner`，先 probe SSH、Sentaurus 和许可证状态。
- 不修改 `/home/tcad/STDB/VDMOS_TID_IGBT` 或 `/usr/synopsys` 下的官方工程。
- 在 `/home/tcad/codex_runs/igbt_seb_<timestamp>/` 创建隔离副本。
- 先做低偏压、短时长 HeavyIon 语法和单位 smoke。
- 正式结果使用 SEB 专用局部加密网格。
- 使用 `StartPoint=(0,3.5)`、`Direction=(1,0)`、`Length=50 um`、`Time=1e-10 s`。
- 使用 `Gaussian PicoCoulomb`、`Wt_hi=0.1 um`、`s_hi=2e-12 s`。
- LET 10 和 15 分别输入 `0.1037` 和 `0.1555 pC/um`。
- 温度使用 `300 K`；`Vg=0`、`Ve=0`。
- Collector 不沿用 `Rc=1e11`。先通过 DC ramp 让器件内压真实达到目标 VCE，再进入瞬态。
- 瞬态运行至 `1 us`，并保存计划列出的时间快照。
- 配置 `2500 K` 温度 break criterion，但烧毁确认阈值为 `1680 K` 加持续大电流/功率。
- 普通求解失败不得判定为 SEB。

## 必须按顺序运行

1. `2500 V + LET 15`：预期无 SEB。
2. `3000 V + LET 10`：预期无 SEB。
3. `3000 V + LET 15`：预期出现 SEB。
4. `3200 V + LET 15`：预期强 SEB，约 `200 ns` 时达到或超过 `2500 K`。

未重现以上定性关系前：

- 不批量运行 `VCE × LET` 矩阵。
- 不随意调整掺杂、层厚或漂移区。
- 先检查实际偏压、`HeavyIonGeneration` 积分、轨迹方向、时间步和网格。
- 论文未给出的 `Wt_hi`、`s_hi` 和热边界必须标记为“Sentaurus/项目假设”，不能写成论文参数。

## 每个有效 case 必须保存

- 实际运行 deck、参数、mesh/final TDR、PLT、LOG 和 stdout。
- `Ic(t)`、`Tmax(t)`、`HeavyIonGeneration` 积分。
- `ElectricField`、`TotalCurrentDensity`、`Temperature`、`JouleHeat`、`SpaceCharge`、`Potential` 和 `ImpactIonization` 分布。
- 沿离子轨迹的电场和势能剖面。
- case 汇总 CSV/JSON 和中文 Markdown 报告。

分类只允许：`SEB_CONFIRMED`、`NO_SEB`、`SEB_ONSET`、`INDETERMINATE`。

## 结束前

- 更新 `plan.md` 的阶段状态。
- 在 `docs/changes/2026-07-11-igbt-seb-paper-reproduction/` 下写运行报告。
- 检查原首轮报告不存在字符污染。
- 不提交 `local_runtime`、PDF、`tmp` 或大型 Sentaurus 原始文件。
- 将可公开的计划、报告、CSV 和必要图片提交并 push 到 `origin/main`。
- 最终回复给出远端运行目录、本地证据目录、四锚点结果、异常说明、commit SHA 和 push 验证。
