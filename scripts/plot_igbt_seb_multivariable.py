#!/usr/bin/env python3
"""Plot all admissible A01 diagnostics in a Figure 9-style single panel."""

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
RUN = ROOT / "local_runtime" / "igbt_seb_full_20260712_035027"
CASES = RUN / "cases"
PUBLIC_DATA = ROOT / "docs" / "changes" / "2026-07-11-igbt-seb-paper-reproduction" / "data"
OUTPUT_DIR = ROOT / "docs" / "changes" / "2026-07-13-igbt-seb-现有数据复盘"

POINT_HEADER = [
    "series_id",
    "variant_axis",
    "variant_value",
    "series_label",
    "bias_v",
    "let_mev_cm2_mg",
    "time_s",
    "ic_a_um",
    "tmax_k",
    "power_w_um",
    "sample_kind",
    "source_path",
    "source_row",
    "classification_scope",
]
KEY_HEADER = [
    "key_id",
    "series_id",
    "time_s",
    "ic_a_um",
    "tmax_k",
    "meaning",
    "source_path",
    "source_row",
]

FULL_SERIES = [
    {
        "series_id": "baseline",
        "variant_axis": "reference",
        "variant_value": "thermal_steady_Wt0.1_Y3.5_baseline_mesh",
        "series_label": "Reference A01 | Wt=0.1 µm | thermal steady",
        "path": CASES / "A01_v2500_let15_y3p5__attempt04" / "transient.csv",
        "color": "#1A1A1A",
        "marker": "s",
    },
    {
        "series_id": "meshhalf",
        "variant_axis": "mesh",
        "variant_value": "track_core_half",
        "series_label": "Track-core half mesh",
        "path": CASES / "A01_v2500_let15_y3p5__attempt18_meshhalf_transient_to60" / "transient.csv",
        "color": "#7B3294",
        "marker": "D",
    },
    {
        "series_id": "wt_0p2",
        "variant_axis": "wt_hi",
        "variant_value": "0.2_um",
        "series_label": "Wt_hi = 0.2 µm",
        "path": CASES / "A01_v2500_let15_y3p5__attempt19_wt0p2_transient_to60" / "transient.csv",
        "color": "#D55E00",
        "marker": "o",
    },
    {
        "series_id": "wt_0p5",
        "variant_axis": "wt_hi",
        "variant_value": "0.5_um",
        "series_label": "Wt_hi = 0.5 µm",
        "path": CASES / "A01_v2500_let15_y3p5__attempt21_wt0p5_transient_to60" / "transient.csv",
        "color": "#0072B2",
        "marker": "^",
    },
    {
        "series_id": "cold300",
        "variant_axis": "initial_temperature_state",
        "variant_value": "cold300_nonsteady",
        "series_label": "300 K cold initial state",
        "path": CASES / "A01_v2500_let15_y3p5__attempt24_cold300_transient_to60" / "transient.csv",
        "color": "#E69F00",
        "marker": "v",
    },
]

SPARSE_SERIES = [
    {
        "series_id": "position_y3p4",
        "variant_axis": "position",
        "variant_value": "Y3.4_um",
        "series_label": "Strike Y = 3.4 µm | local diagnostic",
        "path": CASES / "A01_v2500_let15_y3p4__attempt25_position_transient_to60" / "common_time_summary.csv",
        "color": "#009E73",
        "marker": "P",
        "sample_kind": "exact_checkpoint",
    },
    {
        "series_id": "position_y3p5",
        "variant_axis": "position",
        "variant_value": "Y3.5_um",
        "series_label": "Strike Y = 3.5 µm | derived reference",
        "path": CASES / "A01_v2500_let15_y3p5__attempt07_A40_60" / "baseline_common_time_summary.csv",
        "color": "#666666",
        "marker": "o",
        "sample_kind": "derived_interpolated",
    },
    {
        "series_id": "position_y3p6",
        "variant_axis": "position",
        "variant_value": "Y3.6_um",
        "series_label": "Strike Y = 3.6 µm | local diagnostic",
        "path": CASES / "A01_v2500_let15_y3p6__attempt26_position_transient_to60" / "common_time_summary.csv",
        "color": "#56B4E9",
        "marker": "X",
        "sample_kind": "exact_checkpoint",
    },
]


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def read_csv_with_rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        return [(line_number, row) for line_number, row in enumerate(reader, start=2)]


def read_full_series(spec: dict[str, object]) -> list[dict[str, object]]:
    path = spec["path"]
    rows = []
    for line_number, row in read_csv_with_rows(path):
        vce_key = "collector_inner_v" if "collector_inner_v" in row else "vce_v"
        current_key = "collector_current_a_um" if "collector_current_a_um" in row else "ic_a_um"
        required = {"time_s", vce_key, current_key, "power_w_um", "tmax_k"}
        if not required.issubset(row):
            raise ValueError(f"Unexpected transient schema: {path}")
        rows.append(
            {
                "series_id": spec["series_id"],
                "variant_axis": spec["variant_axis"],
                "variant_value": spec["variant_value"],
                "series_label": spec["series_label"],
                "bias_v": float(row[vce_key]),
                "let_mev_cm2_mg": 15.0,
                "time_s": float(row["time_s"]),
                "ic_a_um": float(row[current_key]),
                "tmax_k": float(row["tmax_k"]),
                "power_w_um": float(row["power_w_um"]),
                "sample_kind": "raw_transient",
                "source_path": relative(path),
                "source_row": line_number,
                "classification_scope": "diagnostic_only",
            }
        )
    if not rows:
        raise ValueError(f"Empty transient: {path}")
    return rows


def read_sparse_series(spec: dict[str, object]) -> list[dict[str, object]]:
    path = spec["path"]
    rows = []
    for line_number, row in read_csv_with_rows(path):
        time_s = float(row["target_time_s"])
        rows.append(
            {
                "series_id": spec["series_id"],
                "variant_axis": spec["variant_axis"],
                "variant_value": spec["variant_value"],
                "series_label": spec["series_label"],
                "bias_v": float(row["vce_v"]),
                "let_mev_cm2_mg": 15.0,
                "time_s": time_s,
                "ic_a_um": float(row["ic_a_um"]),
                "tmax_k": float(row["tmax_k"]),
                "power_w_um": float(row["power_w_um"]),
                "sample_kind": spec["sample_kind"],
                "source_path": relative(path),
                "source_row": line_number,
                "classification_scope": "diagnostic_only",
            }
        )
    return rows


def write_csv(path: Path, header: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "NA") for name in header})


def rows_for(points: list[dict[str, object]], series_id: str) -> list[dict[str, object]]:
    return [point for point in points if point["series_id"] == series_id]


def closest(points: list[dict[str, object]], target_s: float) -> dict[str, object]:
    return min(points, key=lambda point: abs(float(point["time_s"]) - target_s))


def key_points(baseline: list[dict[str, object]]) -> list[dict[str, object]]:
    pulse_window = [point for point in baseline if 9e-11 <= float(point["time_s"]) <= 1.2e-10]
    decay_window = [point for point in baseline if 1.2e-10 <= float(point["time_s"]) <= 1e-9]
    events = [
        ("pulse_local_max", max(pulse_window, key=lambda point: float(point["ic_a_um"])), "recorded pulse local maximum"),
        ("post_pulse_sample_min", min(decay_window, key=lambda point: float(point["ic_a_um"])), "recorded post-pulse sample minimum; not recovered to pre-strike baseline"),
        ("time_10ns", closest(baseline, 1e-8), "closest raw point to 10 ns"),
        ("time_50ns", closest(baseline, 5e-8), "closest raw point to 50 ns"),
        ("time_60ns", closest(baseline, 6e-8), "closest raw point to 60 ns"),
        ("available_window_end", baseline[-1], "last available A01 point; not a recovery or classification point"),
    ]
    return [
        {
            "key_id": key_id,
            "series_id": point["series_id"],
            "time_s": point["time_s"],
            "ic_a_um": point["ic_a_um"],
            "tmax_k": point["tmax_k"],
            "meaning": meaning,
            "source_path": point["source_path"],
            "source_row": point["source_row"],
        }
        for key_id, point, meaning in events
    ]


def marker_stride(point_count: int) -> int:
    return max(1, math.ceil(point_count / 40))


def plot_series(
    current_axis,
    temperature_axis,
    points: list[dict[str, object]],
    spec: dict[str, object],
    sparse: bool,
) -> None:
    times = [float(point["time_s"]) for point in points]
    currents = [float(point["ic_a_um"]) for point in points]
    temperatures = [float(point["tmax_k"]) for point in points]
    color = str(spec["color"])
    marker = str(spec["marker"])
    marker_every = 1 if sparse else marker_stride(len(points))
    marker_face = "none" if points[0]["sample_kind"] == "derived_interpolated" else color
    line_style = "--" if sparse else "-"

    current_axis.plot(
        times,
        currents,
        color=color,
        linewidth=1.2 if sparse else 1.45,
        linestyle=line_style,
        marker=marker,
        markevery=marker_every,
        markersize=4.8 if sparse else 3.3,
        markerfacecolor=marker_face,
        markeredgecolor=color,
        alpha=0.96,
        zorder=4 if sparse else 3,
    )
    temperature_axis.plot(
        times,
        temperatures,
        color=color,
        linewidth=1.05,
        linestyle=(0, (4, 2)),
        marker=marker if sparse else None,
        markersize=3.5,
        markerfacecolor="none",
        markeredgecolor=color,
        alpha=0.62,
        zorder=2,
    )


def annotate_point(axis, point: dict[str, object], text: str, offset: tuple[int, int], color: str) -> None:
    axis.scatter(
        [float(point["time_s"])],
        [float(point["ic_a_um"])],
        s=38,
        facecolors="white",
        edgecolors=color,
        linewidths=1.3,
        zorder=7,
    )
    axis.annotate(
        text,
        xy=(float(point["time_s"]), float(point["ic_a_um"])),
        xytext=offset,
        textcoords="offset points",
        fontsize=8.1,
        color=color,
        arrowprops={"arrowstyle": "->", "color": color, "lw": 0.9},
        bbox={"boxstyle": "round,pad=0.22", "facecolor": "white", "edgecolor": color, "alpha": 0.9},
        zorder=8,
    )


def plot_figure(
    points: list[dict[str, object]],
    keys: list[dict[str, object]],
    output_path: Path,
) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.labelsize": 12,
            "axes.titlesize": 13,
            "legend.fontsize": 8.6,
        }
    )
    figure, current_axis = plt.subplots(figsize=(11.8, 7.8))
    temperature_axis = current_axis.twinx()

    for spec in FULL_SERIES:
        plot_series(current_axis, temperature_axis, rows_for(points, str(spec["series_id"])), spec, sparse=False)
    for spec in SPARSE_SERIES:
        plot_series(current_axis, temperature_axis, rows_for(points, str(spec["series_id"])), spec, sparse=True)

    current_axis.set_xscale("log")
    current_axis.set_yscale("log")
    current_axis.set_xlim(1e-14, 1e-6)
    current_axis.set_ylim(1e-8, 1e-2)
    temperature_axis.set_ylim(280, 430)
    current_axis.set_xlabel("Time (s)")
    current_axis.set_ylabel("Collector transient current (A/µm)")
    temperature_axis.set_ylabel(r"Maximum lattice temperature $T_{max}$ (K)")
    current_axis.grid(True, which="major", linestyle="--", linewidth=0.7, alpha=0.42)
    current_axis.grid(True, which="minor", linestyle=":", linewidth=0.45, alpha=0.25)

    current_axis.axvline(1e-10, color="#555555", linewidth=1.0, linestyle=":", zorder=1)
    current_axis.text(1e-10, 1.8e-8, "Ion strike\n100 ps", ha="center", va="bottom", fontsize=8.5, color="#444444")

    key_lookup = {point["key_id"]: point for point in keys}
    annotate_point(
        current_axis,
        key_lookup["pulse_local_max"],
        "Recorded pulse\nlocal maximum\n96.875 ps",
        (36, 24),
        "#222222",
    )
    annotate_point(
        current_axis,
        key_lookup["post_pulse_sample_min"],
        "Recorded post-pulse\nsample minimum\n253.957 ps",
        (42, -48),
        "#222222",
    )
    annotate_point(
        current_axis,
        key_lookup["available_window_end"],
        "Available-window end\n81.933 ns",
        (-130, 20),
        "#222222",
    )

    mesh = rows_for(points, "meshhalf")
    baseline = rows_for(points, "baseline")
    mesh_50 = closest(mesh, 5e-8)
    mesh_60 = closest(mesh, 6e-8)
    base_50 = closest(baseline, 5e-8)
    base_60 = closest(baseline, 6e-8)
    for point in (base_50, mesh_50, base_60, mesh_60):
        current_axis.scatter(
            [float(point["time_s"])],
            [float(point["ic_a_um"])],
            s=24,
            facecolors="white",
            edgecolors="#7B3294",
            linewidths=1.0,
            zorder=7,
        )
    current_axis.annotate(
        "mesh diagnostic\n50 ns: −6.19%\n60 ns: −15.23%",
        xy=(float(mesh_60["time_s"]), float(mesh_60["ic_a_um"])),
        xytext=(24, -52),
        textcoords="offset points",
        fontsize=8.0,
        color="#7B3294",
        arrowprops={"arrowstyle": "->", "color": "#7B3294", "lw": 0.9},
        bbox={"boxstyle": "round,pad=0.22", "facecolor": "white", "edgecolor": "#7B3294", "alpha": 0.9},
        zorder=8,
    )

    variable_handles = [
        Line2D([0], [0], color=spec["color"], marker=spec["marker"], linestyle="-", label=spec["series_label"])
        for spec in FULL_SERIES + SPARSE_SERIES
    ]
    variable_legend = current_axis.legend(
        handles=variable_handles,
        title="Actual 2500 V diagnostic variables",
        loc="upper left",
        frameon=True,
        framealpha=0.93,
        ncol=1,
    )
    current_axis.add_artist(variable_legend)
    quantity_handles = [
        Line2D([0], [0], color="#333333", linestyle="-", label="Collector current | raw points + guide-to-eye"),
        Line2D([0], [0], color="#333333", linestyle=(0, (4, 2)), label=r"$T_{max}$ | same series color"),
        Line2D([0], [0], color="#666666", marker="o", markerfacecolor="none", linestyle="--", label="derived/interpolated reference point"),
    ]
    current_axis.legend(handles=quantity_handles, loc="lower right", frameon=True, framealpha=0.93)

    current_axis.set_title(
        "Simulated collector transient current and maximum lattice temperature\n"
        "VCE = 2500 V; LET = 15 MeV·cm²·mg⁻¹; all series are diagnostic-only"
    )
    figure.text(
        0.5,
        0.013,
        "A01: INDETERMINATE, ANCHOR_MISMATCH, MESH_SENSITIVE. Lines connect existing points only; no fitted or extrapolated data.",
        ha="center",
        fontsize=8.5,
        color="#333333",
    )
    figure.tight_layout(rect=(0.025, 0.045, 0.985, 0.985))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    figure.savefig(output_path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(figure)


def validate(points: list[dict[str, object]], keys: list[dict[str, object]]) -> None:
    if not points or not keys:
        raise ValueError("No plot points or key points")
    if any(float(point["time_s"]) <= 0 or float(point["ic_a_um"]) <= 0 for point in points):
        raise ValueError("Non-positive log-scale point")
    if any(point["classification_scope"] != "diagnostic_only" for point in points):
        raise ValueError("Plot contains non-diagnostic scope")
    expected_counts = {
        "baseline": 1857,
        "meshhalf": 152,
        "wt_0p2": 159,
        "wt_0p5": 162,
        "cold300": 165,
        "position_y3p4": 4,
        "position_y3p5": 3,
        "position_y3p6": 4,
    }
    actual_counts = {series_id: len(rows_for(points, series_id)) for series_id in expected_counts}
    if actual_counts != expected_counts:
        raise ValueError(f"Unexpected series counts: {actual_counts}")
    lookup = {key["key_id"]: key for key in keys}
    if abs(float(lookup["available_window_end"]["time_s"]) - 8.19333762393e-08) > 1e-18:
        raise ValueError("Unexpected A01 end time")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    points = []
    for spec in FULL_SERIES:
        points.extend(read_full_series(spec))
    for spec in SPARSE_SERIES:
        points.extend(read_sparse_series(spec))
    points.sort(key=lambda point: (str(point["series_id"]), float(point["time_s"])))
    baseline = rows_for(points, "baseline")
    keys = key_points(baseline)
    validate(points, keys)

    data_path = args.output_dir / "data" / "figure9_multivariable_points.csv"
    key_path = args.output_dir / "data" / "figure9_multivariable_key_points.csv"
    figure_path = args.output_dir / "figures" / "figure9_multivariable_paper_style.png"
    write_csv(data_path, POINT_HEADER, points)
    write_csv(key_path, KEY_HEADER, keys)
    plot_figure(points, keys, figure_path)
    print(
        f"paper-style figure built: points={len(points)}, keys={len(keys)}, "
        f"output={figure_path}"
    )


if __name__ == "__main__":
    main()