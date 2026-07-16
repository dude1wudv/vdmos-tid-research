#!/usr/bin/env python3
"""Plot a Figure 9-style IGBT-SEB transient from the existing A01 data."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT
    / "local_runtime"
    / "igbt_seb_full_20260712_035027"
    / "cases"
    / "A01_v2500_let15_y3p5__attempt04"
    / "transient.csv"
)
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "docs"
    / "changes"
    / "2026-07-13-igbt-seb-现有数据复盘"
)
SOURCE_RELATIVE = DEFAULT_INPUT.relative_to(ROOT).as_posix()


def read_transient(path: Path) -> list[dict[str, float]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "time_s",
            "collector_inner_v",
            "collector_current_a_um",
            "power_w_um",
            "tmax_k",
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Unexpected transient schema: {path}")
        rows = [
            {name: float(row[name]) for name in required}
            for row in reader
        ]
    if not rows:
        raise ValueError(f"Transient data is empty: {path}")
    if any(row["time_s"] <= 0 or row["collector_current_a_um"] <= 0 for row in rows):
        raise ValueError("Log-scale plot requires positive time and collector current")
    return rows


def write_figure_data(path: Path, rows: list[dict[str, float]]) -> None:
    header = [
        "bias_v",
        "let_mev_cm2_mg",
        "time_s",
        "collector_current_a_um",
        "tmax_k",
        "power_w_um",
        "source_path",
        "classification_scope",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "bias_v": f"{row['collector_inner_v']:.1f}",
                    "let_mev_cm2_mg": "15",
                    "time_s": f"{row['time_s']:.12g}",
                    "collector_current_a_um": f"{row['collector_current_a_um']:.12g}",
                    "tmax_k": f"{row['tmax_k']:.12g}",
                    "power_w_um": f"{row['power_w_um']:.12g}",
                    "source_path": SOURCE_RELATIVE,
                    "classification_scope": "A01_INDETERMINATE_existing_data_only",
                }
            )


def decade_bounds(values: list[float]) -> tuple[float, float]:
    lower = 10 ** math.floor(math.log10(min(values)))
    upper = 10 ** math.ceil(math.log10(max(values)))
    return lower, upper


def plot_figure(path: Path, rows: list[dict[str, float]]) -> None:
    times = [row["time_s"] for row in rows]
    currents = [row["collector_current_a_um"] for row in rows]
    temperatures = [row["tmax_k"] for row in rows]
    current_min, current_max = decade_bounds(currents)
    time_min, time_max = decade_bounds(times)

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.labelsize": 11,
            "axes.titlesize": 12,
            "legend.fontsize": 9,
        }
    )
    figure, current_axis = plt.subplots(figsize=(8.8, 5.8))
    temperature_axis = current_axis.twinx()

    current_line = current_axis.plot(
        times,
        currents,
        color="#111111",
        linewidth=1.8,
        label="Collector current, 2500 V",
        zorder=3,
    )[0]
    temperature_line = temperature_axis.plot(
        times,
        temperatures,
        color="#D55E00",
        linewidth=1.8,
        linestyle="--",
        label=r"$T_{max}$, 2500 V",
        zorder=2,
    )[0]

    current_axis.set_xscale("log")
    current_axis.set_yscale("log")
    current_axis.set_xlim(time_min, time_max)
    current_axis.set_ylim(current_min, current_max)
    temperature_axis.set_ylim(300, max(420, math.ceil(max(temperatures) / 20) * 20 + 20))

    current_axis.set_xlabel("Time (s)")
    current_axis.set_ylabel("Collector transient current (A/µm)")
    temperature_axis.set_ylabel(r"Maximum lattice temperature $T_{max}$ (K)", color="#A33F00")
    temperature_axis.tick_params(axis="y", colors="#A33F00")

    current_axis.grid(True, which="major", linestyle="--", linewidth=0.7, alpha=0.45)
    current_axis.grid(True, which="minor", linestyle=":", linewidth=0.45, alpha=0.25)
    current_axis.axvline(1e-10, color="#777777", linewidth=1.0, linestyle=":")
    current_axis.text(
        1e-10,
        current_max / 1.5,
        "Ion strike\n100 ps",
        ha="center",
        va="top",
        fontsize=8.5,
        color="#555555",
    )

    final = rows[-1]
    temperature_axis.annotate(
        f"{final['tmax_k']:.1f} K at {final['time_s'] * 1e9:.1f} ns",
        xy=(final["time_s"], final["tmax_k"]),
        xytext=(-138, 28),
        textcoords="offset points",
        arrowprops={"arrowstyle": "->", "color": "#A33F00", "lw": 1.0},
        color="#A33F00",
        fontsize=8.5,
    )

    current_axis.legend(
        handles=[current_line, temperature_line],
        loc="upper left",
        frameon=True,
        framealpha=0.92,
    )
    current_axis.text(
        0.98,
        0.05,
        "Available simulation: 2500 V only\n3000 V and 3200 V: NOT ENTERED",
        transform=current_axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=8.5,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#888888", "alpha": 0.92},
    )

    current_axis.set_title(
        "Simulated collector transient current and maximum lattice temperature\n"
        "LET = 15 MeV·cm²·mg⁻¹ — existing A01 simulation data"
    )
    figure.text(
        0.5,
        0.012,
        "A01 remains INDETERMINATE and MESH_SENSITIVE; the curve is not a confirmed SEB/NO-SEB classification.",
        ha="center",
        fontsize=8.2,
        color="#444444",
    )
    figure.tight_layout(rect=(0.03, 0.045, 0.98, 0.98))
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=300, bbox_inches="tight")
    figure.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(figure)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_transient(args.input)
    figure_path = args.output_dir / "figures" / "figure9_existing_2500v_let15.png"
    data_path = args.output_dir / "data" / "figure9_existing_2500v_let15.csv"
    write_figure_data(data_path, rows)
    plot_figure(figure_path, rows)
    print(
        f"figure built: rows={len(rows)}, time_end_ns={rows[-1]['time_s'] * 1e9:.6f}, "
        f"tmax_k={rows[-1]['tmax_k']:.6f}, output={figure_path}"
    )


if __name__ == "__main__":
    main()