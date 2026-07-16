#!/usr/bin/env python3
"""Merge the locked LET scan into auditable diagnostic-only CSV, plot, and report."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/changes/2026-07-13-igbt-seb-现有数据复盘"
OUT = BASE / "let_scan"
DATA = OUT / "data"
FIGURES = OUT / "figures"
LETS = (0.015, 0.15, 1.5, 15.0, 150.0)
LET_COLORS = {0.015: "#332288", 0.15: "#88CCEE", 1.5: "#0072B2", 15.0: "#D55E00", 150.0: "#009E73"}
SOURCES = (
    (0.015, "thermal-steady", "A01_v2500_let0p015_y3p5_thermal", DATA / "let0p015_thermal_raw.csv", "A01_v2500_let0p015_y3p5_thermal__recovery40p7to60_v1__20260715T062738672Z__8838285d"),
    (0.015, "cold300", "A01_v2500_let0p015_y3p5_cold300", DATA / "let0p015_cold300_raw.csv", "A01_v2500_let0p015_y3p5_cold300__recovery40p7to60_v1__20260715T062739251Z__2fc62e6b"),
    (0.15, "thermal-steady", "A01_v2500_let0p15_y3p5_thermal", DATA / "let0p15_thermal_raw.csv", "A01_v2500_let0p15_y3p5_thermal__transient_to60_v1__20260715T084034904Z__63d298c2"),
    (0.15, "cold300", "A01_v2500_let0p15_y3p5_cold300", DATA / "let0p15_cold300_raw.csv", "A01_v2500_let0p15_y3p5_cold300__recovery50to60_v1__20260715T102616671Z__a569c139"),
    (1.5, "thermal-steady", "A01_v2500_let1p5_y3p5_thermal", DATA / "let1p5_thermal_raw.csv", "A01_v2500_let1p5_y3p5_thermal__transient_to60__20260713T102222930Z__2438182a"),
    (1.5, "cold300", "A01_v2500_let1p5_y3p5_cold300", DATA / "let1p5_cold300_raw.csv", "A01_v2500_let1p5_y3p5_cold300__transient_to60_affinity_retry1__20260713T110749706Z__33338186"),
    (15.0, "thermal-steady", "A01_v2500_let15_y3p5_thermal", BASE / "data/r1_thermal_transient_long.csv", "A01_v2500_let15_y3p5_thermal__R1_thermo_coupled_to60__20260713T064449946Z__1d9cd23a"),
    (15.0, "cold300", "A01_v2500_let15_y3p5_cold300", BASE / "data/thermal_timing_diagnostic.csv", "attempt24_cold300_transient_to60"),
    (150.0, "thermal-steady", "A01_v2500_let150_y3p5_thermal", DATA / "let150_thermal_raw.csv", "A01_v2500_let150_y3p5_thermal__transient_to60_affinity_retry1__20260713T110749704Z__9e3892c2"),
    (150.0, "cold300", "A01_v2500_let150_y3p5_cold300", DATA / "let150_cold300_raw.csv", "A01_v2500_let150_y3p5_cold300__transient_to60_affinity_retry1__20260713T110749937Z__8c552664"),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(let: float, initial: str, case_id: str, path: Path, run_id: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for number, row in enumerate(csv.DictReader(handle), start=2):
            if path.name == "thermal_timing_diagnostic.csv":
                wanted = "thermal_steady" if initial == "thermal-steady" else "cold300_nonsteady"
                if row["series_id"] != wanted:
                    continue
            if path.name == "r1_thermal_transient_long.csv" and row["sample_kind"] != "raw_transient":
                continue
            time_s = float(row["time_s"])
            voltage = float(row.get("collector_inner_voltage_v") or row.get("vce_v"))
            current = float(row.get("collector_total_current_a_um") or row.get("ic_a_um"))
            tmax = float(row["tmax_k"])
            rows.append({"let_mev_cm2_mg": let, "initial_state": initial, "case_id": case_id, "run_id": run_id,
                         "time_s": time_s, "vce_v": voltage, "ic_a_um": current, "tmax_k": tmax,
                         "source_path": path.relative_to(ROOT).as_posix(), "source_sha256": digest(path), "source_row": number})
    rows.sort(key=lambda row: float(row["time_s"]))
    if not rows or any(float(rows[i]["time_s"]) <= float(rows[i - 1]["time_s"]) for i in range(1, len(rows))):
        raise ValueError(f"time is not strictly increasing: {path}")
    tpre = [row for row in rows if float(row["time_s"]) <= 9e-11][-1]["tmax_k"]
    for row in rows:
        row["tpre_k"] = tpre
        row["delta_t_k"] = float(row["tmax_k"]) - float(tpre)
        row["power_w_um"] = float(row["vce_v"]) * float(row["ic_a_um"])
    return rows


def at(rows: list[dict[str, object]], target: float) -> tuple[dict[str, float], str]:
    for row in rows:
        if float(row["time_s"]) == target:
            return {key: float(row[key]) for key in ("ic_a_um", "tmax_k", "delta_t_k", "power_w_um")}, "exact"
    for left, right in zip(rows, rows[1:]):
        a, b = float(left["time_s"]), float(right["time_s"])
        if a < target < b:
            weight = (target - a) / (b - a)
            return ({key: float(left[key]) + weight * (float(right[key]) - float(left[key])) for key in ("ic_a_um", "tmax_k", "delta_t_k", "power_w_um")}, "interpolated")
    raise ValueError(f"target outside available interval: {target}")


def plot_five_let_abc(grouped: dict[tuple[float, str], list[dict[str, object]]]) -> None:
    colors = LET_COLORS
    styles = {"thermal-steady": "-", "cold300": "--"}
    figure, axes = plt.subplots(
        3,
        1,
        figsize=(11.2, 10.2),
        sharex=True,
        gridspec_kw={"height_ratios": (1.15, 1.0, 1.0), "hspace": 0.14},
    )
    current_axis, temperature_axis, rise_axis = axes

    for let in LETS:
        for initial in ("thermal-steady", "cold300"):
            rows = grouped[(let, initial)]
            time_ns = [float(row["time_s"]) * 1e9 for row in rows]
            color = colors[let]
            style = styles[initial]
            current_axis.plot(
                time_ns,
                [float(row["ic_a_um"]) for row in rows],
                color=color,
                linestyle=style,
                linewidth=1.65,
                alpha=0.95,
            )
            temperature_axis.plot(
                time_ns,
                [float(row["tmax_k"]) for row in rows],
                color=color,
                linestyle=style,
                linewidth=1.7,
                alpha=0.95,
            )
            eligible = [row for row in rows if float(row["delta_t_k"]) > 0]
            rise_axis.plot(
                [float(row["time_s"]) * 1e9 for row in eligible],
                [float(row["delta_t_k"]) for row in eligible],
                color=color,
                linestyle=style,
                linewidth=1.65,
                alpha=0.95,
            )

    for axis in axes:
        axis.set_xscale("log")
        axis.set_xlim(1e-4, 1e2)
        axis.grid(True, which="major", linestyle="--", linewidth=0.7, alpha=0.38)
        axis.grid(True, which="minor", linestyle=":", linewidth=0.45, alpha=0.22)
        axis.axvline(0.1, color="#666666", linestyle=":", linewidth=1.0)

    current_axis.set_yscale("log")
    current_axis.set_ylim(1e-8, 1e-2)
    current_axis.set_ylabel("Collector current\n$ I_C$ (A/µm)")
    current_axis.set_title("A. Electrical response — compare LET and initial thermal state", loc="left", fontweight="bold")
    current_axis.text(0.1, 1.35e-8, "Ion strike\n0.1 ns", ha="center", va="bottom", fontsize=8.4)

    all_temperatures = [float(row["tmax_k"]) for rows in grouped.values() for row in rows]
    temperature_axis.set_ylim(min(295.0, min(all_temperatures) - 5), max(405.0, max(all_temperatures) + 5))
    temperature_axis.set_ylabel("Absolute device\n$T_{max}$ (K)")
    temperature_axis.set_title("B. Absolute temperature — compare how hot the device actually is", loc="left", fontweight="bold")

    rise_axis.set_yscale("log")
    rise_axis.set_ylim(1e-8, 1e2)
    rise_axis.set_ylabel("Rise above own start\n$\Delta T=T_{max}-T_{pre}$ (K)")
    rise_axis.set_xlabel("Time after transient start (ns, logarithmic scale)")
    rise_axis.set_title("C. Incremental heating — each curve is referenced to its own pre-strike temperature", loc="left", fontweight="bold")

    let_handles = [
        Line2D([0], [0], color=colors[let], linewidth=2.4, label=f"LET = {let:g} MeV·cm²·mg⁻¹")
        for let in LETS
    ]
    state_handles = [
        Line2D([0], [0], color="#333333", linestyle="-", linewidth=2.0, label="Thermal-steady initial state"),
        Line2D([0], [0], color="#333333", linestyle="--", linewidth=2.0, label="300 K cold initial state"),
    ]
    figure.legend(
        handles=let_handles + state_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.946),
        ncol=5,
        frameon=False,
        fontsize=8.8,
    )
    figure.suptitle(
        "A01 current and thermal response across five ion injection levels\n"
        "VCE = 2500 V; trajectory y = 3.5 µm",
        y=0.992,
        fontsize=14,
        fontweight="bold",
    )
    figure.text(
        0.5,
        0.014,
        "Color identifies LET; line style identifies initial thermal state. Read B for absolute temperature and C only for incremental heating. "
        "Diagnostic only; MESH_SENSITIVE.",
        ha="center",
        fontsize=8.4,
        color="#333333",
    )
    figure.subplots_adjust(left=0.105, right=0.975, top=0.89, bottom=0.075)
    figure.savefig(FIGURES / "five_let_thermal_timing_abc.png", dpi=300, bbox_inches="tight")
    figure.savefig(FIGURES / "five_let_thermal_timing_abc.svg", bbox_inches="tight")
    plt.close(figure)


def plot_single_let_abc(grouped: dict[tuple[float, str], list[dict[str, object]]], let: float) -> None:
    figure, axes = plt.subplots(3, 1, figsize=(10.2, 9.2), sharex=True, gridspec_kw={"hspace": 0.16})
    styles = {"thermal-steady": ("#111111", "-", "Thermal-steady initial state"), "cold300": ("#0072B2", "--", "300 K cold initial state")}
    for initial, (color, linestyle, label) in styles.items():
        rows = grouped[(let, initial)]
        time_ns = [float(row["time_s"]) * 1e9 for row in rows]
        axes[0].plot(time_ns, [float(row["ic_a_um"]) for row in rows], color=color, linestyle=linestyle, label=label)
        axes[1].plot(time_ns, [float(row["tmax_k"]) for row in rows], color=color, linestyle=linestyle, label=label)
        axes[2].plot(time_ns, [max(float(row["delta_t_k"]), 1e-8) for row in rows], color=color, linestyle=linestyle, label=label)
    for axis in axes:
        axis.set_xscale("log")
        axis.set_xlim(1e-4, 1e2)
        axis.grid(True, which="both", linestyle=":", alpha=0.35)
        axis.axvline(0.1, color="#666666", linestyle=":", linewidth=1)
    axes[0].set_yscale("log"); axes[0].set_ylabel("Collector current\n$ I_C$ (A/µm)")
    axes[1].set_ylabel("Absolute device\n$T_{max}$ (K)")
    axes[2].set_yscale("log"); axes[2].set_ylabel("Incremental heating\n$\Delta T$ (K)")
    axes[2].set_xlabel("Time after transient start (ns, logarithmic scale)")
    axes[0].legend(frameon=False, loc="best")
    figure.suptitle(f"A01 low-LET diagnostic ABC — LET = {let:g} MeV·cm²·mg⁻¹\nVCE = 2500 V; trajectory y = 3.5 µm; diagnostic only; MESH_SENSITIVE")
    figure.subplots_adjust(left=0.12, right=0.98, top=0.9, bottom=0.08, hspace=0.16)
    slug = f"let{let:g}".replace(".", "p")
    figure.savefig(FIGURES / f"{slug}_thermal_timing_abc.png", dpi=300, bbox_inches="tight")
    figure.savefig(FIGURES / f"{slug}_thermal_timing_abc.svg", bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    all_rows = [row for source in SOURCES for row in load(*source)]
    long_header = ["let_mev_cm2_mg", "initial_state", "case_id", "run_id", "time_s", "vce_v", "ic_a_um", "tmax_k", "tpre_k", "delta_t_k", "power_w_um", "source_path", "source_sha256", "source_row"]
    with (DATA / "let_scan_long.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=long_header); writer.writeheader(); writer.writerows(all_rows)
    grouped = {(float(row["let_mev_cm2_mg"]), str(row["initial_state"])): [] for row in all_rows}
    for row in all_rows: grouped[(float(row["let_mev_cm2_mg"]), str(row["initial_state"]))].append(row)
    plot_five_let_abc(grouped)
    plot_single_let_abc(grouped, 0.015)
    plot_single_let_abc(grouped, 0.15)
    times = (1e-8, 4e-8, 6e-8)
    summary = []
    for let in LETS:
        thermal, cold = grouped[(let, "thermal-steady")], grouped[(let, "cold300")]
        for time_s in times:
            tv, tm = at(thermal, time_s); cv, cm = at(cold, time_s)
            summary.append({"let_mev_cm2_mg": let, "time_s": time_s, "time_ns": time_s * 1e9,
                            "common_window_end_s": min(float(thermal[-1]["time_s"]), float(cold[-1]["time_s"])),
                            "thermal_sampling": tm, "cold_sampling": cm, "ic_thermal_a_um": tv["ic_a_um"], "ic_cold_a_um": cv["ic_a_um"],
                            "ic_ratio_thermal_over_cold": tv["ic_a_um"] / max(cv["ic_a_um"], 1e-300),
                            "log10_ic_ratio": math.log10(max(tv["ic_a_um"], 1e-300) / max(cv["ic_a_um"], 1e-300)),
                            "tmax_thermal_k": tv["tmax_k"], "tmax_cold_k": cv["tmax_k"], "absolute_tmax_difference_k": tv["tmax_k"] - cv["tmax_k"],
                            "delta_t_thermal_k": tv["delta_t_k"], "delta_t_cold_k": cv["delta_t_k"], "delta_t_difference_k": tv["delta_t_k"] - cv["delta_t_k"],
                            "diagnostic_only": "true", "mesh_sensitivity": "MESH_SENSITIVE"})
    header = list(summary[0])
    with (DATA / "let_scan_fixed_time_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header); writer.writeheader(); writer.writerows(summary)
    fig, axes = plt.subplots(3, 1, figsize=(9.5, 9), sharex=True)
    colors = {10.0: "#0072B2", 40.0: "#D55E00", 60.0: "#009E73"}
    measures = (("log10_ic_ratio", "log10(Ic thermal / Ic cold)"), ("absolute_tmax_difference_k", "Tmax thermal − cold (K)"), ("delta_t_difference_k", "ΔT thermal − cold (K)"))
    for axis, (key, label) in zip(axes, measures):
        for time_ns, color in colors.items():
            rows = [r for r in summary if r["time_ns"] == time_ns]
            axis.plot([r["let_mev_cm2_mg"] for r in rows], [r[key] for r in rows], marker="o", color=color, label=f"{time_ns:g} ns")
        axis.set_xscale("log"); axis.axhline(0, color="#777", linewidth=.8); axis.grid(True, which="both", alpha=.3); axis.set_ylabel(label); axis.legend(frameon=False)
    axes[-1].set_xlabel("LET (MeV·cm²·mg⁻¹)")
    fig.suptitle("LET scan: thermal-steady minus cold300 (diagnostic only; MESH_SENSITIVE)")
    fig.tight_layout(); fig.savefig(FIGURES / "let_scan_summary.png", dpi=260); fig.savefig(FIGURES / "let_scan_summary.svg"); plt.close(fig)
    report = [
        "# LET 热态对照扫描：诊断汇总", "",
        "## 范围与结论边界", "",
        "- 范围固定为 `VCE=2500 V`、`y=3.5 µm`、60 ns 观察窗；本支线为既有数据复盘，标记为 `diagnostic_only` 与 `MESH_SENSITIVE`。",
        "- 本文只记录单次轨迹在锁定模型、网格和边界下的数值诊断；不判定 SEB、不推导 SEB 阈值，也不将电流、温度的同步或差异解释为热机制因果关系。",
        "- 本支线不改写 `2026-07-14-igbt-mosfet-seb-paper-simulation` 的固定 `LET=15、2.1 ns` 正式矩阵结论。", "",
        "## 低 LET 运行与恢复证据", "",
        "所有执行均经自动核心租约、`Threads=1` 与 CPU 亲和性记录；四条最终序列均以 `exit_code=0` 覆盖至 60 ns。", "",
        "| LET | 初始态 | 完整/恢复 run ID | 说明 |", "|---:|---|---|---|",
        "| 0.015 | thermal-steady | `A01_v2500_let0p015_y3p5_thermal__recovery40p7to60_v1__20260715T062738672Z__8838285d` | 原始 transient 约 40.608 ns 数值失败；经 40.0–40.7 ns 门控恢复后，从 40.7 ns 续跑至 60 ns。 |",
        "| 0.015 | cold300 | `A01_v2500_let0p015_y3p5_cold300__recovery40p7to60_v1__20260715T062739251Z__2fc62e6b` | 原始 transient 约 40.521 ns 数值失败；采用相同独立 recovery variant 后续跑至 60 ns。 |",
        "| 0.15 | thermal-steady | `A01_v2500_let0p15_y3p5_thermal__transient_to60_v1__20260715T084034904Z__63d298c2` | 原始完整 transient 成功至 60 ns。 |",
        "| 0.15 | cold300 | `A01_v2500_let0p15_y3p5_cold300__recovery50to60_v1__20260715T102616671Z__a569c139` | 原始 transient 在约 51.180 ns 数值失败并保留精确 50 ns restart；从该检查点独立续跑至 60 ns。 |", "",
        "`LET=0.015` 的 40–40.7 ns 恢复门控使用最大步长 50 ps，越过原失败点后写出 40.7 ns restart；最终续跑最大步长为 0.5 ns。上述求解失败仅为数值事件，未作物理 SEB 解释。", "",
        "## 提取、拼接与可复核性", "",
        "- 使用 Sentaurus Visual 的只读 PLT API 提取九段数据，统一为 `time_s`、`collector_inner_voltage_v`、`collector_total_current_a_um`、`tmax_k`；提取不重采样。",
        "- 合并审计见 [`data/low_let_extraction_manifest.json`](data/low_let_extraction_manifest.json)。四条输出 CSV 均记录源段 SHA-256、选择行数、时间范围与接缝。",
        "- `LET=0.015` 热/冷两案的真实接缝均为 `40.000 ns → 40.001 ns` 与 `40.700 ns → 40.710 ns`；`LET=0.15 cold300` 接缝为 `50.000 ns → 50.010 ns`。未伪造 40 ns 或 50 ns 之后的采样点。",
        "- 五档汇总验证见 [`data/let_scan_validation.json`](data/let_scan_validation.json)：`records=1593`、`series=10`、`fixed_time_rows=15`；固定时刻不是原始节点时，显式标记为 `interpolated`。", "",
        "## 图件与数据产品", "",
        "- 五档综合：[`figures/five_let_thermal_timing_abc.png`](figures/five_let_thermal_timing_abc.png)、[`figures/five_let_thermal_timing_abc.svg`](figures/five_let_thermal_timing_abc.svg)、[`figures/let_scan_summary.png`](figures/let_scan_summary.png)。",
        "- 低 LET 独立对照：[`figures/let0p015_thermal_timing_abc.png`](figures/let0p015_thermal_timing_abc.png)、[`figures/let0p15_thermal_timing_abc.png`](figures/let0p15_thermal_timing_abc.png)，均有对应 SVG。",
        "- 固定时刻表：[`data/let_scan_fixed_time_summary.csv`](data/let_scan_fixed_time_summary.csv)；系列配置：[`data/let0p015_series_config.json`](data/let0p015_series_config.json)、[`data/let0p15_series_config.json`](data/let0p15_series_config.json)。", "",
        "## 固定时刻对比", "",
        "| LET | 时间 | Ic热/冷 | log10比 | Tmax热-冷 (K) | ΔT热-冷 (K) |", "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        report.append(f"| {row['let_mev_cm2_mg']:g} | {row['time_ns']:g} ns | {row['ic_ratio_thermal_over_cold']:.4g} | {row['log10_ic_ratio']:.4g} | {row['absolute_tmax_difference_k']:.4g} | {row['delta_t_difference_k']:.4g} |")
    report += [
        "", "## 诊断结论", "",
        "在 10/40/60 ns 的共同 60 ns 窗口内，五档 LET 的热态与冷态差异已被量化。`LET=0.15 cold300` 在 60 ns 的电流差异仅是该单条轨迹的诊断记录；网格、模型和单次轨迹均未作收敛性外推，因此不支持普适机制、热因果或阈值结论。",
    ]
    (OUT / "LET扫描诊断报告.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    audit = {"records": len(all_rows), "series": len(grouped), "fixed_time_rows": len(summary), "source_files": [{"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p)} for *_, p, _ in SOURCES]}
    (DATA / "let_scan_validation.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(f"LET scan summary built: records={len(all_rows)} fixed_points={len(summary)}")

if __name__ == "__main__":
    main()