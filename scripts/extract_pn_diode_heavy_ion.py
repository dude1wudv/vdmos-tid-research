#!/usr/bin/env python3
"""Extract PN-diode baseline and HeavyIon electrical metrics from DF-ISE PLT files."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

FLOAT = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_dfise_plt(path: Path) -> list[dict[str, float]]:
    text = path.read_text(encoding="utf-8-sig")
    dataset_match = re.search(r"datasets\s*=\s*\[(.*?)\]\s*functions\s*=", text, re.DOTALL)
    data_match = re.search(r"\bData\s*\{(.*)\}\s*$", text, re.DOTALL)
    if dataset_match is None or data_match is None:
        raise ValueError(f"unsupported DF-ISE PLT: {path}")
    datasets = re.findall(r'"([^"]+)"', dataset_match.group(1))
    values = [float(token) for token in FLOAT.findall(data_match.group(1))]
    if not datasets or len(values) % len(datasets):
        raise ValueError(f"PLT cardinality mismatch: {path}")
    return [
        dict(zip(datasets, values[index:index + len(datasets)]))
        for index in range(0, len(values), len(datasets))
    ]


def trapz(y: list[float], x: list[float]) -> float:
    return sum((right_x - left_x) * (left_y + right_y) * 0.5 for left_x, right_x, left_y, right_y in zip(x, x[1:], y, y[1:]))


def linear_slope(x: list[float], y: list[float]) -> float:
    if len(x) < 2:
        return math.nan
    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)
    denominator = sum((value - x_mean) ** 2 for value in x)
    if denominator == 0:
        return math.nan
    return sum((xv - x_mean) * (yv - y_mean) for xv, yv in zip(x, y)) / denominator


def validate_run(manifest: dict) -> None:
    scheduling = manifest.get("scheduling_evidence", {})
    checks = (
        manifest.get("lifecycle") == "SUCCEEDED",
        str(manifest.get("exit_code")) == "0",
        manifest.get("sdevice_threads") == 1,
        scheduling.get("lease_acquired") is True,
        scheduling.get("lease_released") is True,
        scheduling.get("affinity_verification") == "VERIFIED",
    )
    if not all(checks):
        raise ValueError(f"run lacks success or scheduling evidence: {manifest.get('run_id')}")


def select_runs(root: Path) -> dict[str, tuple[Path, dict]]:
    selected: dict[str, tuple[Path, dict]] = {}
    for manifest_path in root.glob("*/run_manifest.json"):
        manifest = read_json(manifest_path)
        if manifest.get("lifecycle") != "SUCCEEDED":
            continue
        case_id = str(manifest["case_id"])
        previous = selected.get(case_id)
        if previous is None or str(manifest["ended_at"]) > str(previous[1]["ended_at"]):
            selected[case_id] = (manifest_path.parent, manifest)
    required = {"PN2D_FORWARD", "PN2D_REVERSE100", "PN2D_LET1", "PN2D_LET10", "PN2D_LET50"}
    missing = sorted(required - selected.keys())
    if missing:
        raise ValueError("missing successful runs: " + ", ".join(missing))
    for _, manifest in selected.values():
        validate_run(manifest)
    return selected


def plt_path(run_dir: Path, prefix: str) -> Path:
    path = run_dir / "artifacts" / f"{prefix}.plt"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def write_rows(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def baseline_rows(source: Path, mode: str) -> list[dict[str, float | str]]:
    result = []
    for row in parse_dfise_plt(source):
        result.append(
            {
                "mode": mode,
                "top_voltage_v": row["top InnerVoltage"],
                "top_current_a_per_um": row["top TotalCurrent"],
                "abs_top_current_a_per_um": abs(row["top TotalCurrent"]),
            }
        )
    return result


def transient_summary(run_dir: Path, manifest: dict, output_dir: Path) -> dict:
    let_value = float(manifest["let_mev_cm2_mg"])
    prefix = f"pn2d_let{int(let_value)}"
    source = plt_path(run_dir, prefix)
    raw = sorted(parse_dfise_plt(source), key=lambda row: row["time"])
    time_s = [row["time"] for row in raw]
    voltage_v = [row["top InnerVoltage"] for row in raw]
    current = [row["top TotalCurrent"] for row in raw]
    baseline = current[0]
    excursion = [abs(value - baseline) for value in current]
    abs_current = [abs(value) for value in current]
    abs_power = [abs(voltage * value) for voltage, value in zip(voltage_v, current)]
    peak_index = max(range(len(raw)), key=lambda index: abs_current[index])
    peak_excursion_index = max(range(len(raw)), key=lambda index: excursion[index])
    peak_power_index = max(range(len(raw)), key=lambda index: abs_power[index])
    tail_start = max(0, int(len(raw) * 0.9))
    tail_current = abs_current[tail_start:]
    tail_time = time_s[tail_start:]
    recovery_fraction = excursion[-1] / excursion[peak_excursion_index] if excursion[peak_excursion_index] else 0.0
    rows = [
        {
            "time_s": time,
            "top_voltage_v": voltage,
            "top_current_a_per_um": value,
            "abs_top_current_a_per_um": abs(value),
            "current_excursion_a_per_um": delta,
        }
        for time, voltage, value, delta in zip(time_s, voltage_v, current, excursion)
    ]
    csv_path = output_dir / f"pn2d_let{int(let_value)}_transient.csv"
    write_rows(csv_path, rows)
    metadata_path = run_dir / "inputs" / f"{prefix}.json"
    metadata = read_json(metadata_path)
    field_path = output_dir / f"pn2d_let{int(let_value)}_tdr_summary.json"
    field_summary = read_json(field_path) if field_path.is_file() else None
    return {
        "case_id": manifest["case_id"],
        "let_mev_cm2_mg": let_value,
        "let_f_pc_um": float(manifest["let_f_pc_um"]),
        "time_end_s": time_s[-1],
        "sample_count": len(rows),
        "baseline_current_a_per_um": baseline,
        "final_current_a_per_um": current[-1],
        "peak_abs_current_a_per_um": abs_current[peak_index],
        "peak_current_time_s": time_s[peak_index],
        "peak_abs_power_w_per_um": abs_power[peak_power_index],
        "peak_power_time_s": time_s[peak_power_index],
        "collected_charge_pc_per_um": trapz(excursion, time_s) * 1e12,
        "port_energy_j_per_um": trapz(abs_power, time_s),
        "final_to_peak_excursion_fraction": recovery_fraction,
        "recovered_to_10pct": recovery_fraction <= 0.1,
        "tail_abs_current_slope_a_per_um_s": linear_slope(tail_time, tail_current),
        "sustained_tail_growth": len(tail_current) >= 2 and tail_current[-1] > tail_current[0],
        "nominal_injected_charge_pc_per_1um_depth": float(metadata["let_f_pc_um"]) * float(metadata["length_um"]),
        "run_id": manifest["run_id"],
        "cpu_core": manifest["cpu_core"],
        "wall_time_seconds": float(manifest["wall_time_seconds"]),
        "source_plt": str(source),
        "source_plt_sha256": sha256(source),
        "transient_csv": str(csv_path),
        "tdr_summary": field_summary,
    }


def plot_results(baseline: list[dict], transient: list[dict], output_dir: Path) -> dict:
    import matplotlib.pyplot as plt

    figure_dir = output_dir.parent / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.5), constrained_layout=True)
    for mode in ("forward", "reverse"):
        rows = [row for row in baseline if row["mode"] == mode]
        axes[0].semilogy(
            [row["top_voltage_v"] for row in rows],
            [max(row["abs_top_current_a_per_um"], 1e-30) for row in rows],
            label=mode,
        )
    axes[0].set(xlabel="Top voltage (V)", ylabel="|Top current| (A/µm)", title="2D PN baseline I-V")
    axes[0].grid(True, which="both", alpha=0.3)
    axes[0].legend()
    for item in transient:
        rows = list(csv.DictReader(Path(item["transient_csv"]).open(encoding="utf-8")))
        axes[1].loglog(
            [max(float(row["time_s"]), 1e-14) for row in rows],
            [max(float(row["abs_top_current_a_per_um"]), 1e-30) for row in rows],
            label=f"LET {item['let_mev_cm2_mg']:g}",
        )
    axes[1].set(xlabel="Time (s)", ylabel="|Top current| (A/µm)", title="HeavyIon transient at VR = 100 V")
    axes[1].grid(True, which="both", alpha=0.3)
    axes[1].legend()
    png = figure_dir / "pn2d_baseline_and_heavy_ion.png"
    svg = figure_dir / "pn2d_baseline_and_heavy_ion.svg"
    figure.savefig(png, dpi=180)
    figure.savefig(svg)
    plt.close(figure)
    return {"png": str(png), "png_sha256": sha256(png), "svg": str(svg), "svg_sha256": sha256(svg)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    selected = select_runs(args.run_root)
    forward_dir, forward_manifest = selected["PN2D_FORWARD"]
    reverse_dir, reverse_manifest = selected["PN2D_REVERSE100"]
    baseline = baseline_rows(plt_path(forward_dir, "pn2d_forward"), "forward")
    baseline += baseline_rows(plt_path(reverse_dir, "pn2d_reverse100"), "reverse")
    baseline_csv = args.output_dir / "pn2d_baseline_iv.csv"
    write_rows(baseline_csv, baseline)
    transient = [
        transient_summary(*selected[case_id], args.output_dir)
        for case_id in ("PN2D_LET1", "PN2D_LET10", "PN2D_LET50")
    ]
    forward_endpoint = [row for row in baseline if row["mode"] == "forward"][-1]
    reverse_endpoint = [row for row in baseline if row["mode"] == "reverse"][-1]
    figures = plot_results(baseline, transient, args.output_dir)
    summary = {
        "schema": "pn_diode_heavy_ion_extraction/v1",
        "status": "PASS" if all(item["tdr_summary"] and item["tdr_summary"]["status"] == "PASS" for item in transient) else "PARTIAL",
        "normalization": "2D current per unit depth; 1 um equivalent depth gives the same numeric current in A",
        "baseline": {
            "forward_endpoint": forward_endpoint,
            "reverse_endpoint": reverse_endpoint,
            "forward_run_id": forward_manifest["run_id"],
            "reverse_run_id": reverse_manifest["run_id"],
            "baseline_csv": str(baseline_csv),
        },
        "transient_cases": transient,
        "figures": figures,
    }
    summary_path = args.output_dir / "pn2d_heavy_ion_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(summary_path)


if __name__ == "__main__":
    main()