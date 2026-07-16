# LET 热态对照扫描：诊断汇总

## 范围与结论边界

- 范围固定为 `VCE=2500 V`、`y=3.5 µm`、60 ns 观察窗；本支线为既有数据复盘，标记为 `diagnostic_only` 与 `MESH_SENSITIVE`。
- 本文只记录单次轨迹在锁定模型、网格和边界下的数值诊断；不判定 SEB、不推导 SEB 阈值，也不将电流、温度的同步或差异解释为热机制因果关系。
- 本支线不改写 `2026-07-14-igbt-mosfet-seb-paper-simulation` 的固定 `LET=15、2.1 ns` 正式矩阵结论。

## 低 LET 运行与恢复证据

所有执行均经自动核心租约、`Threads=1` 与 CPU 亲和性记录；四条最终序列均以 `exit_code=0` 覆盖至 60 ns。

| LET | 初始态 | 完整/恢复 run ID | 说明 |
|---:|---|---|---|
| 0.015 | thermal-steady | `A01_v2500_let0p015_y3p5_thermal__recovery40p7to60_v1__20260715T062738672Z__8838285d` | 原始 transient 约 40.608 ns 数值失败；经 40.0–40.7 ns 门控恢复后，从 40.7 ns 续跑至 60 ns。 |
| 0.015 | cold300 | `A01_v2500_let0p015_y3p5_cold300__recovery40p7to60_v1__20260715T062739251Z__2fc62e6b` | 原始 transient 约 40.521 ns 数值失败；采用相同独立 recovery variant 后续跑至 60 ns。 |
| 0.15 | thermal-steady | `A01_v2500_let0p15_y3p5_thermal__transient_to60_v1__20260715T084034904Z__63d298c2` | 原始完整 transient 成功至 60 ns。 |
| 0.15 | cold300 | `A01_v2500_let0p15_y3p5_cold300__recovery50to60_v1__20260715T102616671Z__a569c139` | 原始 transient 在约 51.180 ns 数值失败并保留精确 50 ns restart；从该检查点独立续跑至 60 ns。 |

`LET=0.015` 的 40–40.7 ns 恢复门控使用最大步长 50 ps，越过原失败点后写出 40.7 ns restart；最终续跑最大步长为 0.5 ns。上述求解失败仅为数值事件，未作物理 SEB 解释。

## 提取、拼接与可复核性

- 使用 Sentaurus Visual 的只读 PLT API 提取九段数据，统一为 `time_s`、`collector_inner_voltage_v`、`collector_total_current_a_um`、`tmax_k`；提取不重采样。
- 合并审计见 [`data/low_let_extraction_manifest.json`](data/low_let_extraction_manifest.json)。四条输出 CSV 均记录源段 SHA-256、选择行数、时间范围与接缝。
- `LET=0.015` 热/冷两案的真实接缝均为 `40.000 ns → 40.001 ns` 与 `40.700 ns → 40.710 ns`；`LET=0.15 cold300` 接缝为 `50.000 ns → 50.010 ns`。未伪造 40 ns 或 50 ns 之后的采样点。
- 五档汇总验证见 [`data/let_scan_validation.json`](data/let_scan_validation.json)：`records=1593`、`series=10`、`fixed_time_rows=15`；固定时刻不是原始节点时，显式标记为 `interpolated`。

## 图件与数据产品

- 五档综合：[`figures/five_let_thermal_timing_abc.png`](figures/five_let_thermal_timing_abc.png)、[`figures/five_let_thermal_timing_abc.svg`](figures/five_let_thermal_timing_abc.svg)、[`figures/let_scan_summary.png`](figures/let_scan_summary.png)。
- 低 LET 独立对照：[`figures/let0p015_thermal_timing_abc.png`](figures/let0p015_thermal_timing_abc.png)、[`figures/let0p15_thermal_timing_abc.png`](figures/let0p15_thermal_timing_abc.png)，均有对应 SVG。
- 固定时刻表：[`data/let_scan_fixed_time_summary.csv`](data/let_scan_fixed_time_summary.csv)；系列配置：[`data/let0p015_series_config.json`](data/let0p015_series_config.json)、[`data/let0p15_series_config.json`](data/let0p15_series_config.json)。

## 固定时刻对比

| LET | 时间 | Ic热/冷 | log10比 | Tmax热-冷 (K) | ΔT热-冷 (K) |
|---:|---:|---:|---:|---:|---:|
| 0.015 | 10 ns | 1.007 | 0.002862 | 24.63 | -0.003195 |
| 0.015 | 40 ns | 0.9592 | -0.01808 | 24.62 | -0.01239 |
| 0.015 | 60 ns | 0.9594 | -0.018 | 24.61 | -0.02427 |
| 0.15 | 10 ns | 0.8904 | -0.0504 | 24.62 | -0.01135 |
| 0.15 | 40 ns | 1 | 9.328e-05 | 24.56 | -0.07783 |
| 0.15 | 60 ns | 0.03472 | -1.459 | 24.47 | -0.1596 |
| 1.5 | 10 ns | 0.9038 | -0.04391 | 24.62 | -0.01176 |
| 1.5 | 40 ns | 0.8725 | -0.05922 | 17.38 | -7.249 |
| 1.5 | 60 ns | 0.9426 | -0.02568 | 11.97 | -12.67 |
| 15 | 10 ns | 0.9017 | -0.04494 | 24.6 | -0.0286 |
| 15 | 40 ns | 0.8101 | -0.09146 | 19.82 | -4.813 |
| 15 | 60 ns | 0.7609 | -0.1187 | -2.747 | -27.38 |
| 150 | 10 ns | 0.8996 | -0.04595 | 24.36 | -0.2767 |
| 150 | 40 ns | 0.8447 | -0.07329 | 22.6 | -2.03 |
| 150 | 60 ns | 0.7722 | -0.1123 | 14.65 | -9.988 |

## 诊断结论

在 10/40/60 ns 的共同 60 ns 窗口内，五档 LET 的热态与冷态差异已被量化。`LET=0.15 cold300` 在 60 ns 的电流差异仅是该单条轨迹的诊断记录；网格、模型和单次轨迹均未作收敛性外推，因此不支持普适机制、热因果或阈值结论。
