#!/usr/bin/env python3
"""Analyze A01 current-temperature timing using log-scaled delta temperature."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "local_runtime" / "igbt_seb_full_20260712_035027" / "cases"
OUTPUT_DIR = ROOT / "docs" / "changes" / "2026-07-13-igbt-seb-现有数据复盘"
STRIKE_TIME_S = 1e-10
PRESTRIKE_CUTOFF_S = 9e-11
PLOT_LET_LABEL = "15"

SERIES = [
    {
        "series_id": "thermal_steady",
        "label": "Thermal-steady baseline",
        "color": "#111111",
        "temperature_color": "#D55E00",
        "path": CASES / "A01_v2500_let15_y3p5__attempt04" / "transient.csv",
    },
    {
        "series_id": "cold300_nonsteady",
        "label": "300 K cold initial state",
        "color": "#0072B2",
        "temperature_color": "#E69F00",
        "path": CASES / "A01_v2500_let15_y3p5__attempt24_cold300_transient_to60" / "transient.csv",
    },
]

TIMING_HEADER = [
    "series_id",
    "time_s",
    "time_ns",
    "vce_v",
    "ic_a_um",
    "tmax_k",
    "tpre_k",
    "delta_t_k",
    "delta_t_log_eligible",
    "power_w_um",
    "cumulative_electrical_energy_j_um",
    "d_log_ic_dt_s_inv",
    "d_delta_t_dt_k_s",
    "phase",
    "source_path",
    "source_row",
    "classification_scope",
]
KEY_HEADER = [
    "series_id",
    "key_id",
    "time_s",
    "ic_a_um",
    "tmax_k",
    "delta_t_k",
    "power_w_um",
    "cumulative_electrical_energy_j_um",
    "source_path",
    "source_row",
]


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def read_rows(path: Path) -> list[dict[str, object]]:
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        for source_row, row in enumerate(reader, start=2):
            vce_key = next((key for key in ("collector_inner_v", "collector_inner_voltage_v", "vce_v") if key in row), None)
            current_key = next((key for key in ("collector_current_a_um", "collector_total_current_a_um", "ic_a_um") if key in row), None)
            if vce_key is None or current_key is None:
                raise ValueError(f"Missing voltage/current field in {path}")
            vce_v = float(row[vce_key])
            ic_a_um = float(row[current_key])
            rows.append(
                {
                    "time_s": float(row["time_s"]),
                    "vce_v": vce_v,
                    "ic_a_um": ic_a_um,
                    "tmax_k": float(row["tmax_k"]),
                    "power_w_um": float(row.get("power_w_um") or vce_v * ic_a_um),
                    "source_path": relative(path),
                    "source_row": source_row,
                }
            )
    if not rows:
        raise ValueError(f"Empty transient: {path}")
    return rows


def phase_for(time_s: float) -> str:
    if time_s < 9e-11:
        return "pre_strike"
    if time_s <= 1.2e-10:
        return "ion_pulse"
    if time_s < 3.15e-10:
        return "post_pulse_decay"
    if time_s < 1e-8:
        return "early_electrical_growth"
    if time_s < 4e-8:
        return "10_to_40ns"
    if time_s < 6e-8:
        return "40_to_60ns"
    return "after_60ns"


def central_derivative(values: list[float], times: list[float], index: int) -> float:
    if index == 0:
        left, right = 0, 1
    elif index == len(values) - 1:
        left, right = len(values) - 2, len(values) - 1
    else:
        left, right = index - 1, index + 1
    return (values[right] - values[left]) / (times[right] - times[left])


def analyze_series(spec: dict[str, object]) -> list[dict[str, object]]:
    raw = read_rows(spec["path"])
    prestrike = [row for row in raw if float(row["time_s"]) <= PRESTRIKE_CUTOFF_S]
    if not prestrike:
        raise ValueError(f"No pre-strike samples: {spec['path']}")
    tpre_k = float(prestrike[-1]["tmax_k"])
    times = [float(row["time_s"]) for row in raw]
    log_currents = [math.log(max(float(row["ic_a_um"]), 1e-300)) for row in raw]
    delta_temperatures = [float(row["tmax_k"]) - tpre_k for row in raw]

    cumulative_energy = [0.0]
    for index in range(1, len(raw)):
        dt = times[index] - times[index - 1]
        average_power = 0.5 * (
            float(raw[index - 1]["power_w_um"]) + float(raw[index]["power_w_um"])
        )
        cumulative_energy.append(cumulative_energy[-1] + average_power * dt)

    rows = []
    for index, row in enumerate(raw):
        delta_t_k = delta_temperatures[index]
        rows.append(
            {
                "series_id": spec["series_id"],
                "time_s": row["time_s"],
                "time_ns": float(row["time_s"]) * 1e9,
                "vce_v": row["vce_v"],
                "ic_a_um": row["ic_a_um"],
                "tmax_k": row["tmax_k"],
                "tpre_k": tpre_k,
                "delta_t_k": delta_t_k,
                "delta_t_log_eligible": "true" if delta_t_k > 0 else "false",
                "power_w_um": row["power_w_um"],
                "cumulative_electrical_energy_j_um": cumulative_energy[index],
                "d_log_ic_dt_s_inv": central_derivative(log_currents, times, index),
                "d_delta_t_dt_k_s": central_derivative(delta_temperatures, times, index),
                "phase": phase_for(float(row["time_s"])),
                "source_path": row["source_path"],
                "source_row": row["source_row"],
                "classification_scope": "diagnostic_only",
            }
        )
    return rows


def closest(rows: list[dict[str, object]], target_s: float) -> dict[str, object]:
    return min(rows, key=lambda row: abs(float(row["time_s"]) - target_s))


def build_key_rows(all_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output = []
    for spec in SERIES:
        rows = [row for row in all_rows if row["series_id"] == spec["series_id"]]
        pulse = [row for row in rows if 9e-11 <= float(row["time_s"]) <= 1.2e-10]
        decay = [row for row in rows if 1.2e-10 <= float(row["time_s"]) <= 1e-9]
        events = [
            ("pulse_local_max", max(pulse, key=lambda row: float(row["ic_a_um"]))),
            ("post_pulse_sample_min", min(decay, key=lambda row: float(row["ic_a_um"]))),
            ("time_10ns", closest(rows, 1e-8)),
            ("time_40ns", closest(rows, 4e-8)),
            ("time_50ns", closest(rows, 5e-8)),
            ("time_60ns", closest(rows, 6e-8)),
            ("available_window_end", rows[-1]),
        ]
        for key_id, row in events:
            output.append(
                {
                    "series_id": spec["series_id"],
                    "key_id": key_id,
                    "time_s": row["time_s"],
                    "ic_a_um": row["ic_a_um"],
                    "tmax_k": row["tmax_k"],
                    "delta_t_k": row["delta_t_k"],
                    "power_w_um": row["power_w_um"],
                    "cumulative_electrical_energy_j_um": row["cumulative_electrical_energy_j_um"],
                    "source_path": row["source_path"],
                    "source_row": row["source_row"],
                }
            )
    return output


def write_csv(path: Path, header: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "NA") for name in header})


def marker_stride(count: int) -> int:
    return max(1, math.ceil(count / 45))


def plot_log_timing(all_rows: list[dict[str, object]], output: Path) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.labelsize": 11,
            "axes.titlesize": 12,
            "legend.fontsize": 9,
        }
    )
    figure, (current_axis, temperature_axis, rise_axis) = plt.subplots(
        3,
        1,
        figsize=(11.2, 10.2),
        sharex=True,
        gridspec_kw={"height_ratios": (1.15, 1.0, 1.0), "hspace": 0.14},
    )

    scenario_handles = []
    for spec in SERIES:
        rows = [row for row in all_rows if row["series_id"] == spec["series_id"]]
        times_ns = [float(row["time_s"]) * 1e9 for row in rows]
        currents = [float(row["ic_a_um"]) for row in rows]
        temperatures = [float(row["tmax_k"]) for row in rows]
        color = spec["color"]
        tpre_k = float(rows[0]["tpre_k"])

        current_axis.plot(
            times_ns,
            currents,
            color=color,
            linewidth=1.7,
            marker="o",
            markevery=marker_stride(len(rows)),
            markersize=2.8,
        )
        temperature_axis.plot(times_ns, temperatures, color=color, linewidth=1.8)

        eligible = [row for row in rows if float(row["delta_t_k"]) > 0]
        rise_axis.plot(
            [float(row["time_s"]) * 1e9 for row in eligible],
            [float(row["delta_t_k"]) for row in eligible],
            color=color,
            linewidth=1.6,
            linestyle="--",
            marker="^",
            markevery=marker_stride(len(eligible)),
            markersize=3.0,
            label=f"{spec['label']}: rise above {tpre_k:.3f} K",
        )
        scenario_handles.append(
            Line2D([0], [0], color=color, linewidth=2.2, label=spec["label"])
        )

    for axis in (current_axis, temperature_axis, rise_axis):
        axis.set_xscale("log")
        axis.set_xlim(1e-4, 1e2)
        axis.grid(True, which="major", linestyle="--", linewidth=0.7, alpha=0.38)
        axis.grid(True, which="minor", linestyle=":", linewidth=0.45, alpha=0.22)
        axis.axvline(STRIKE_TIME_S * 1e9, color="#666666", linestyle=":", linewidth=1.1)

    current_axis.set_yscale("log")
    current_axis.set_ylim(1e-8, 1e-2)
    current_axis.set_ylabel("Collector current\n$ I_C$ (A/µm)")
    current_axis.set_title("A. Electrical response — compare when current starts to grow", loc="left", fontweight="bold")

    temperature_axis.set_ylim(295, 405)
    temperature_axis.set_ylabel("Absolute device\n$T_{max}$ (K)")
    temperature_axis.set_title("B. Absolute temperature — use this panel to decide which device is hotter", loc="left", fontweight="bold")

    steady_rows = [row for row in all_rows if row["series_id"] == "thermal_steady"]
    cold_rows = [row for row in all_rows if row["series_id"] == "cold300_nonsteady"]
    steady_pre = float(steady_rows[0]["tpre_k"])
    cold_pre = float(cold_rows[0]["tpre_k"])
    temperature_axis.axhline(steady_pre, color=SERIES[0]["color"], linestyle=":", linewidth=1.0, alpha=0.8)
    temperature_axis.axhline(cold_pre, color=SERIES[1]["color"], linestyle=":", linewidth=1.0, alpha=0.8)
    temperature_axis.text(1.4e-4, steady_pre + 1.5, f"Thermal-steady starts at {steady_pre:.3f} K", color=SERIES[0]["color"], fontsize=8.5)
    temperature_axis.text(1.4e-4, cold_pre + 1.5, f"Cold run starts at {cold_pre:.3f} K", color=SERIES[1]["color"], fontsize=8.5)

    rise_axis.set_yscale("log")
    rise_axis.set_ylim(1e-8, 1e2)
    rise_axis.set_ylabel("Rise above own start\n$\Delta T=T_{max}-T_{pre}$ (K)")
    rise_axis.set_xlabel("Time after transient start (ns, logarithmic scale)")
    rise_axis.set_title("C. Incremental heating — compare timing only; the two zero points are different", loc="left", fontweight="bold")
    rise_axis.legend(loc="upper left", frameon=True, framealpha=0.94)

    steady_10ns = closest(steady_rows, 1e-8)
    cold_10ns = closest(cold_rows, 1e-8)
    current_axis.annotate(
        "At 10 ns current is already elevated",
        xy=(10, float(steady_10ns["ic_a_um"])),
        xytext=(2.0, 2.5e-5),
        fontsize=8.5,
        arrowprops={"arrowstyle": "->", "color": "#444444", "lw": 0.9},
        bbox={"boxstyle": "round,pad=0.22", "facecolor": "white", "edgecolor": "#888888", "alpha": 0.94},
    )
    temperature_axis.scatter(
        [10, 10],
        [float(steady_10ns["tmax_k"]), float(cold_10ns["tmax_k"])],
        s=30,
        facecolors="white",
        edgecolors=[SERIES[0]["color"], SERIES[1]["color"]],
        zorder=5,
    )
    temperature_axis.annotate(
        f"10 ns absolute temperatures:\n{float(steady_10ns['tmax_k']):.3f} K vs {float(cold_10ns['tmax_k']):.3f} K",
        xy=(10, float(steady_10ns["tmax_k"])),
        xytext=(0.9, 354),
        fontsize=8.5,
        arrowprops={"arrowstyle": "->", "color": "#444444", "lw": 0.9},
        bbox={"boxstyle": "round,pad=0.24", "facecolor": "white", "edgecolor": "#888888", "alpha": 0.94},
    )
    rise_axis.annotate(
        f"10 ns: +{float(steady_10ns['delta_t_k']):.3f} K above {steady_pre:.3f} K",
        xy=(10, float(steady_10ns["delta_t_k"])),
        xytext=(0.42, 4e-3),
        fontsize=8.2,
        color=SERIES[0]["color"],
        arrowprops={"arrowstyle": "->", "color": SERIES[0]["color"], "lw": 0.9},
    )
    rise_axis.annotate(
        f"10 ns: +{float(cold_10ns['delta_t_k']):.3f} K above {cold_pre:.3f} K",
        xy=(10, float(cold_10ns["delta_t_k"])),
        xytext=(0.42, 0.35),
        fontsize=8.2,
        color=SERIES[1]["color"],
        arrowprops={"arrowstyle": "->", "color": SERIES[1]["color"], "lw": 0.9},
    )

    current_axis.text(
        STRIKE_TIME_S * 1e9,
        1.35e-8,
        "Ion strike\n0.1 ns",
        ha="center",
        va="bottom",
        fontsize=8.4,
    )
    figure.legend(
        handles=scenario_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.946),
        ncol=2,
        frameon=False,
    )
    figure.suptitle(
        "A01 current and thermal response: separate absolute temperature from temperature rise\n"
        "VCE = 2500 V; LET = " + PLOT_LET_LABEL + " MeV·cm²·mg⁻¹",
        y=0.992,
        fontsize=14,
        fontweight="bold",
    )
    figure.text(
        0.5,
        0.014,
        "Read B for actual temperature; read C only for heating timing. Timing correlation does not prove thermal causality. "
        "A01 remains INDETERMINATE and MESH_SENSITIVE.",
        ha="center",
        fontsize=8.5,
        color="#333333",
    )
    figure.subplots_adjust(left=0.105, right=0.975, top=0.89, bottom=0.075)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=300, bbox_inches="tight")
    figure.savefig(output.with_suffix(".svg"), bbox_inches="tight")
    plt.close(figure)


def plot_raw_temperature(all_rows: list[dict[str, object]], output: Path) -> None:
    figure, axis = plt.subplots(figsize=(9.6, 5.5))
    for spec in SERIES:
        rows = [row for row in all_rows if row["series_id"] == spec["series_id"]]
        axis.plot(
            [float(row["time_s"]) for row in rows],
            [float(row["tmax_k"]) for row in rows],
            color=spec["temperature_color"],
            linewidth=1.5,
            label=f"Tmax | {spec['label']}",
        )
    axis.set_xscale("log")
    axis.set_xlim(1e-13, 1e-7)
    axis.set_xlabel("Time (s)")
    axis.set_ylabel("Absolute Tmax (K)")
    axis.grid(True, which="both", linestyle="--", alpha=0.32)
    axis.legend(frameon=False)
    axis.set_title("Absolute Tmax retained as a linear-scale companion")
    figure.tight_layout()
    figure.savefig(output, dpi=260, bbox_inches="tight")
    figure.savefig(output.with_suffix(".svg"), bbox_inches="tight")
    plt.close(figure)


def validate(all_rows: list[dict[str, object]], key_rows: list[dict[str, object]]) -> None:
    counts = {
        series_id: sum(row["series_id"] == series_id for row in all_rows)
        for series_id in ("thermal_steady", "cold300_nonsteady")
    }
    if any(row["classification_scope"] != "diagnostic_only" for row in all_rows):
        raise ValueError("Non-diagnostic data entered analysis")
    for series_id in counts:
        rows = [row for row in all_rows if row["series_id"] == series_id]
        if not rows or any(float(rows[index]["time_s"]) <= float(rows[index - 1]["time_s"]) for index in range(1, len(rows))):
            raise ValueError(f"Series must have strictly increasing time: {series_id}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--series-config", type=Path, help="JSON list with series_id, label, color, temperature_color, path")
    parser.add_argument("--let-label", default="15", help="LET label used in plot title")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    global SERIES, PLOT_LET_LABEL
    PLOT_LET_LABEL = args.let_label
    if args.series_config:
        import json
        config = json.loads(args.series_config.read_text(encoding="utf-8"))
        SERIES = [{**item, "path": ROOT / item["path"]} for item in config]
    all_rows = []
    for spec in SERIES:
        all_rows.extend(analyze_series(spec))
    all_rows.sort(key=lambda row: (str(row["series_id"]), float(row["time_s"])))
    key_rows = build_key_rows(all_rows)
    validate(all_rows, key_rows)

    data_dir = args.output_dir / "data"
    figures_dir = args.output_dir / "figures"
    write_csv(data_dir / "thermal_timing_diagnostic.csv", TIMING_HEADER, all_rows)
    write_csv(data_dir / "thermal_timing_key_points.csv", KEY_HEADER, key_rows)
    plot_log_timing(all_rows, figures_dir / "thermal_timing_diagnostic.png")
    plot_raw_temperature(all_rows, figures_dir / "thermal_timing_tmax_linear.png")
    print(
        f"thermal timing built: points={len(all_rows)}, keys={len(key_rows)}, "
        f"output={figures_dir / 'thermal_timing_diagnostic.png'}"
    )


if __name__ == "__main__":
    main()