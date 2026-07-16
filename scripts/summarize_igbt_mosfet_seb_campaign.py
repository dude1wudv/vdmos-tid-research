#!/usr/bin/env python3
"""Publish the formal IGBT/MOSFET SEB comparison from extracted sidecars only.

The script reads seven IGBT main JSON sidecars and one MOSFET comparison sidecar,
their DC gate JSON sidecars, and the sidecar-derived mesh comparison CSV.  It
never reads TDR/PLT data and never invokes SDevice or SVisual.  It writes compact
publication tables, a numerical comparison figure (PNG and SVG), and the
Chinese result report.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = ROOT / "local_runtime/tcad_projects/igbt_mosfet_seb_paper_20260714"
DEFAULT_DOCS = ROOT / "docs/changes/2026-07-14-igbt-mosfet-seb-paper-simulation"

COMPARISON_FIELDS = [
    "case_id",
    "device_family",
    "run_class",
    "t_init_k",
    "bias_v",
    "source_time_ns",
    "transient_status",
    "dc_restart_status",
    "overall_status",
    "tmax_k",
    "hotspot_x_um",
    "hotspot_y_um",
    "hotspot_interface_distance_um",
    "hotspot_region",
    "nearest_interface_type",
    "terminal_baseline_current_a_um",
    "terminal_collected_charge_pc_um",
    "terminal_energy_j_um",
    "heavy_ion_nominal_charge_pc",
    "heavy_ion_integrated_charge_pc",
    "heavy_ion_closure_error_pct",
    "transient_sidecar_json",
    "dc_sidecar_json",
]


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT)).replace("\\", "/")


def status(dc: dict[str, object] | None, transient: dict[str, object] | None) -> str:
    dc_status = str(dc.get("status")) if dc else "NOT_RUN_DEPENDENCY"
    tr_status = str(transient.get("status")) if transient else "NOT_RUN_DEPENDENCY"
    if dc_status == tr_status == "PASS":
        return "PASS"
    if "FAIL" in (dc_status, tr_status):
        return "FAIL"
    return "NOT_RUN_DEPENDENCY"


def build_rows(project: Path) -> list[dict[str, object]]:
    matrix = read_csv(project / "inputs/case_matrix.csv")
    rows: list[dict[str, object]] = []
    for matrix_row in matrix:
        case_id = matrix_row["case_id"]
        transient_path = project / "extracts" / f"{case_id}_2ns.json"
        dc_path = project / "extracts" / f"{case_id}_dc_gate.json"
        transient = load_json(transient_path) if transient_path.exists() else None
        dc = load_json(dc_path) if dc_path.exists() else None
        hotspot = transient.get("hotspot", {}) if transient else {}
        terminal = transient.get("terminal_summary", {}) if transient else {}
        heavy_ion = transient.get("heavy_ion_charge", {}) if transient else {}
        dc_status = str(dc.get("status")) if dc else "NOT_RUN_DEPENDENCY"
        transient_status = str(transient.get("status")) if transient else "NOT_RUN_DEPENDENCY"
        rows.append({
            "case_id": case_id,
            "device_family": matrix_row["device_family"],
            "run_class": matrix_row["run_class"],
            "t_init_k": float(matrix_row["t_init_k"]),
            "bias_v": float(matrix_row["target_vce_v"]),
            "source_time_ns": float(transient.get("source_time_s", 0.0)) * 1e9 if transient else "NA",
            "transient_status": transient_status,
            "dc_restart_status": dc_status,
            "overall_status": status(dc, transient),
            "tmax_k": hotspot.get("temperature_k", "NA"),
            "hotspot_x_um": hotspot.get("x_um", "NA"),
            "hotspot_y_um": hotspot.get("y_um", "NA"),
            "hotspot_interface_distance_um": hotspot.get("distance_um", "NA"),
            "hotspot_region": hotspot.get("region", "NA"),
            "nearest_interface_type": hotspot.get("nearest_interface_type", "NA"),
            "terminal_baseline_current_a_um": terminal.get("baseline_current_a_um", "NA"),
            "terminal_collected_charge_pc_um": terminal.get("collected_charge_pc_um", "NA"),
            "terminal_energy_j_um": terminal.get("energy_j_um", "NA"),
            "heavy_ion_nominal_charge_pc": heavy_ion.get("nominal_charge_pc", "NA"),
            "heavy_ion_integrated_charge_pc": heavy_ion.get("integrated_charge_pc", "NA"),
            "heavy_ion_closure_error_pct": heavy_ion.get("closure_error_pct", "NA"),
            "transient_sidecar_json": relative(transient_path) if transient_path.exists() else "NA",
            "dc_sidecar_json": relative(dc_path) if dc_path.exists() else "NA",
        })
    return rows


def mesh_gate_percent(row: dict[str, str]) -> float:
    value = float(row["gate_value"])
    threshold = float(row["threshold"])
    return value / threshold * 100.0


def build_figure_data(rows: list[dict[str, object]], mesh_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    figure_rows: list[dict[str, object]] = []
    for row in rows:
        figure_rows.extend([
            {
                "panel": "temperature_or_bias_or_device", "series": row["device_family"],
                "case_id": row["case_id"], "x_temperature_k": row["t_init_k"],
                "x_bias_v": row["bias_v"], "metric": "tmax_k", "value": row["tmax_k"], "unit": "K",
            },
            {
                "panel": "device", "series": row["device_family"], "case_id": row["case_id"],
                "x_temperature_k": row["t_init_k"], "x_bias_v": row["bias_v"],
                "metric": "hotspot_interface_distance_um", "value": row["hotspot_interface_distance_um"], "unit": "um",
            },
        ])
    for row in mesh_rows:
        figure_rows.append({
            "panel": "mesh_convergence", "series": row["device_family"], "case_id": row["baseline_case_id"],
            "x_temperature_k": row["temperature_k"], "x_bias_v": row["bias_v"], "metric": row["metric"],
            "value": row["gate_value"], "unit": "% of gate" if row["metric"] != "hotspot_interface_distance_um" else "um of gate",
            "threshold": row["threshold"], "gate_utilization_pct": mesh_gate_percent(row),
        })
    return figure_rows


def draw_figure(rows: list[dict[str, object]], mesh_rows: list[dict[str, str]], output_png: Path, output_svg: Path) -> None:
    plt.rcParams.update({"font.size": 9, "svg.hashsalt": "igbt-mosfet-seb-p7"})
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.6), constrained_layout=True)
    color_igbt = "#1f77b4"
    color_mosfet = "#d62728"

    temperature_rows = sorted(
        (row for row in rows if row["device_family"] == "IGBT" and row["bias_v"] == 550.0),
        key=lambda row: float(row["t_init_k"]),
    )
    ax = axes[0, 0]
    ax.plot([row["t_init_k"] for row in temperature_rows], [row["tmax_k"] for row in temperature_rows], "o-", color=color_igbt)
    ax.set(title="(a) IGBT temperature line (550 V)", xlabel="Initial temperature (K)", ylabel="2.1 ns Tmax (K)")
    ax.grid(alpha=0.3)

    bias_rows = sorted(
        (row for row in rows if row["device_family"] == "IGBT" and row["t_init_k"] == 298.15),
        key=lambda row: float(row["bias_v"]),
    )
    ax = axes[0, 1]
    ax.plot([row["bias_v"] for row in bias_rows], [row["tmax_k"] for row in bias_rows], "o-", color=color_igbt)
    ax.set(title="(b) IGBT bias line (298.15 K)", xlabel="VCE (V)", ylabel="2.1 ns Tmax (K)")
    ax.grid(alpha=0.3)

    device_rows = [
        next(row for row in rows if row["case_id"] == "IGBT_T298_V550_L15"),
        next(row for row in rows if row["case_id"] == "MOSFET_T298_V550_L15"),
    ]
    labels = [str(row["device_family"]) for row in device_rows]
    x = list(range(len(device_rows)))
    ax = axes[1, 0]
    temp_bars = ax.bar(x, [row["tmax_k"] for row in device_rows], color=[color_igbt, color_mosfet], width=0.55, label="Tmax")
    ax.set(title="(c) Matched-device comparison (298.15 K, 550 V)", xticks=x, xticklabels=labels, ylabel="2.1 ns Tmax (K)")
    ax.grid(axis="y", alpha=0.3)
    for bar, row in zip(temp_bars, device_rows):
        ax.annotate(f"{float(row['tmax_k']):.3f}", (bar.get_x() + bar.get_width() / 2, bar.get_height()), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8)
    ax2 = ax.twinx()
    ax2.plot(x, [row["hotspot_interface_distance_um"] for row in device_rows], "ks--", label="Hotspot-interface distance")
    ax2.set_ylabel("Hotspot-interface distance (µm)")
    ax2.set_ylim(150, 190)
    ax.legend(loc="upper left")
    ax2.legend(loc="upper right")

    metric_labels = ["Tmax", "Qcollect", "Energy", "Emax", "Distance"]
    ax = axes[1, 1]
    width = 0.36
    for offset, device, color in ((-width / 2, "IGBT", color_igbt), (width / 2, "MOSFET", color_mosfet)):
        values = [mesh_gate_percent(row) for row in mesh_rows if row["device_family"] == device]
        bars = ax.bar([index + offset for index in range(len(metric_labels))], values, width=width, color=color, label=device)
        for bar, value in zip(bars, values):
            ax.annotate(f"{value:.2g}", (bar.get_x() + bar.get_width() / 2, bar.get_height()), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=7)
    ax.axhline(100, color="black", linewidth=1, linestyle="--", label="Gate")
    ax.set(title="(d) track_refined mesh convergence", xticks=range(len(metric_labels)), xticklabels=metric_labels, ylabel="Gate utilization (%)", ylim=(0, 120))
    ax.grid(axis="y", alpha=0.3)
    ax.legend(ncol=3, loc="upper left", fontsize=8)

    metadata = {
        "Title": "IGBT/MOSFET SEB extracted numerical comparisons",
        "Description": "Numerical comparison figure from JSON/CSV extraction sidecars only; not a spatial field rendering.",
        "Creator": "scripts/summarize_igbt_mosfet_seb_campaign.py",
    }
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=220, metadata=metadata)
    fig.savefig(output_svg, metadata=metadata)
    plt.close(fig)


def report_text(rows: list[dict[str, object]], mesh_rows: list[dict[str, str]]) -> str:
    pass_rows = [row for row in rows if row["overall_status"] == "PASS"]
    transient_pass = sum(row["transient_status"] == "PASS" for row in rows)
    dc_pass = sum(row["dc_restart_status"] == "PASS" for row in rows)
    temperatures = sorted((row for row in rows if row["device_family"] == "IGBT" and row["bias_v"] == 550.0), key=lambda row: float(row["t_init_k"]))
    biases = sorted((row for row in rows if row["device_family"] == "IGBT" and row["t_init_k"] == 298.15), key=lambda row: float(row["bias_v"]))
    igbt = next(row for row in rows if row["case_id"] == "IGBT_T298_V550_L15")
    mosfet = next(row for row in rows if row["case_id"] == "MOSFET_T298_V550_L15")
    mesh = {(row["device_family"], row["metric"]): row for row in mesh_rows}

    def mesh_value(device: str, metric: str) -> str:
        row = mesh[(device, metric)]
        return f"{float(row['gate_value']):.6f}{'%' if metric != 'hotspot_interface_distance_um' else ' µm'}"

    temperature_text = "；".join(f"{row['t_init_k']:.2f} K → {float(row['tmax_k']):.6f} K" for row in temperatures)
    bias_text = "；".join(f"{row['bias_v']:.0f} V → {float(row['tmax_k']):.6f} K" for row in biases)
    return f"""# 正式 IGBT/MOSFET SEB 仿真结果

## 当前完成度与发布证据

- 正式 IGBT 主案例：7 个唯一案；热稳态 sidecar 通过 **{sum(row['device_family'] == 'IGBT' and row['dc_restart_status'] == 'PASS' for row in rows)}/7**；精确 2.1 ns 瞬态 sidecar 通过 **{sum(row['device_family'] == 'IGBT' and row['transient_status'] == 'PASS' for row in rows)}/7**（`data/case_acceptance.csv` 的 IGBT 行）。MOSFET 仅保留 1 个结构匹配派生对照，归入比较附录，不计入 IGBT 正式事实源。
- 额外网格 validation（不计入上述 7 个 IGBT 主案例）：`VAL_IGBT_T298_V550_L15_track_refined` 和 `VAL_MOSFET_T298_V550_L15_track_refined` 的 2.1 ns SVisual 提取均为 **PASS**。两案字段完整且有限、终点精确为 2.1 ns，HeavyIon 闭合误差均为 **3.655629% ≤ 5%**。
- 发布图为**提取数值比较图**：7 个 IGBT 主案与 1 个 MOSFET 附录的 JSON sidecar 是主线和器件对照的唯一数值源，`data/mesh_track_refined_comparison.csv` 是网格面板的唯一数值源；`data/campaign_2ns_comparison.csv` 与 `data/campaign_2ns_numerical_comparison_figure_data.csv` 是其可发布的图数据副本。未生成或发布统一 SVisual 空间场渲染脚本/产物，图不表示电场、温度或载流子空间分布截图。

## 主案例数值对照（2.1 ns）

- 温度主线（IGBT，550 V）：{temperature_text}。
- 偏压主线（IGBT，298.15 K）：{bias_text}。
- 器件对照（298.15 K / 550 V）：IGBT `Tmax={float(igbt['tmax_k']):.6f} K`、收集电荷 `{float(igbt['terminal_collected_charge_pc_um']):.9f} pC/µm`、端能量 `{float(igbt['terminal_energy_j_um']):.6e} J/µm`；结构匹配 MOSFET 分别为 `{float(mosfet['tmax_k']):.6f} K`、`{float(mosfet['terminal_collected_charge_pc_um']):.9f} pC/µm`、`{float(mosfet['terminal_energy_j_um']):.6e} J/µm`。
- 同一匹配模型、同一工况下，MOSFET 热点-界面距离为 **177.248549 µm**，大于 IGBT 的 **167.550144 µm**；因此**不支持“MOSFET 热点更靠近氧化层”这一假设**。

## 298.15 K / 550 V track_refined 网格门

唯一发布数值源为 SVisual JSON/CSV sidecar；未从截图、TDR 或 PLT 估算。相对差定义为 `abs(refined-baseline)/abs(baseline)*100`；热点距离使用绝对差。

| 器件 | Tmax（门 ≤5%） | 收集电荷（门 ≤5%） | 端能量（门 ≤5%） | Emax（门 ≤10%） | 热点距离差（门 ≤0.01 µm） | 结论 |
|---|---:|---:|---:|---:|---:|---|
| IGBT | {mesh_value('IGBT', 'tmax_k')} | {mesh_value('IGBT', 'terminal_collected_charge_pc_um')} | {mesh_value('IGBT', 'terminal_energy_j_um')} | {mesh_value('IGBT', 'emax_v_cm')} | {mesh_value('IGBT', 'hotspot_interface_distance_um')} | PASS |
| MOSFET | {mesh_value('MOSFET', 'tmax_k')} | {mesh_value('MOSFET', 'terminal_collected_charge_pc_um')} | {mesh_value('MOSFET', 'terminal_energy_j_um')} | {mesh_value('MOSFET', 'emax_v_cm')} | {mesh_value('MOSFET', 'hotspot_interface_distance_um')} | PASS |

- 网格图将每项门值归一化为门限占用率；它仍是数值门比较，不是空间场图。两器件各项均小于门限。
- 热点位置按 Silicon 域温度 argmax 到冻结 Si/SiO2 界面段的最短欧氏距离计算，不使用截图估计。

## 可复算发布

```powershell
python scripts\\summarize_igbt_mosfet_seb_campaign.py
```

命令只读取 `local_runtime/tcad_projects/igbt_mosfet_seb_paper_20260714/extracts/` 的 JSON sidecar 和已发布的网格 CSV，重建 `data/case_acceptance.csv`、`data/dc_thermal_restart_summary.csv`、`data/campaign_2ns_comparison.csv`、`data/campaign_2ns_numerical_comparison_figure_data.csv`、`figures/campaign_2ns_numerical_comparison.png/.svg` 及本报告；不运行 SDevice、不读取 raw TDR/PLT，也不将其放入 `docs/`。

## 严格结论边界

- 仅支持本冻结二维结构、模型、LET 15、轨迹、2.1 ns 和所列偏压/初温下的相对数值对照；历史 2500 V A01 只作诊断参考。
- MOSFET 是结构匹配的派生对照，不代表所有商用 MOSFET；上述热点距离不能泛化到商用器件。
- 本工作未模拟或验证 TID 永久损伤、氧化层电荷/界面态演化或其退火，不能将本瞬态热点距离解释为 TID 永久损伤结论。
- 网格门仅验证此冻结结构在 298.15 K / 550 V、LET 15、固定轨迹和二维归一化下的数值稳定性；不构成普适 SEB 阈值、器件失效或封装烧毁能量结论。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--docs-root", type=Path, default=DEFAULT_DOCS)
    args = parser.parse_args()
    project = args.project_root.resolve()
    docs = args.docs_root.resolve()
    data = docs / "data"
    figures = docs / "figures"

    rows = build_rows(project)
    mesh_rows = read_csv(data / "mesh_track_refined_comparison.csv")
    main_rows = [row for row in rows if row["device_family"] == "IGBT" and row["run_class"] == "paper_main"]
    appendix_rows = [row for row in rows if row["device_family"] == "MOSFET" and row["run_class"] == "comparison_appendix"]
    if len(rows) != 8 or len(main_rows) != 7 or len(appendix_rows) != 1 or any(row["overall_status"] != "PASS" for row in rows):
        raise RuntimeError("publication requires exactly seven PASS IGBT main cases plus one PASS MOSFET appendix case")
    if len(mesh_rows) != 10 or any(row["status"] != "PASS" for row in mesh_rows):
        raise RuntimeError("publication requires ten PASS mesh gate rows")

    write_csv(data / "campaign_2ns_comparison.csv", rows, COMPARISON_FIELDS)
    figure_data = build_figure_data(rows, mesh_rows)
    write_csv(
        data / "campaign_2ns_numerical_comparison_figure_data.csv",
        figure_data,
        [
            "panel", "series", "case_id", "x_temperature_k", "x_bias_v", "metric", "value", "unit",
            "threshold", "gate_utilization_pct",
        ],
    )
    write_csv(
        data / "case_acceptance.csv",
        [{**row, "transient_2ns_status": row["transient_status"]} for row in rows],
        ["case_id", "run_class", "dc_restart_status", "transient_2ns_status", "overall_status"],
    )
    write_csv(
        data / "dc_thermal_restart_summary.csv",
        rows,
        [
            "case_id", "device_family", "t_init_k", "bias_v", "dc_restart_status",
            "transient_status", "overall_status", "dc_sidecar_json",
        ],
    )
    draw_figure(rows, mesh_rows, figures / "campaign_2ns_numerical_comparison.png", figures / "campaign_2ns_numerical_comparison.svg")
    (docs / "正式仿真结果报告.md").write_text(report_text(rows, mesh_rows), encoding="utf-8")
    print(f"PUBLISH PASS igbt_main={len(main_rows)}/7 mosfet_appendix={len(appendix_rows)}/1 mesh={len(mesh_rows)}/10 docs={docs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())