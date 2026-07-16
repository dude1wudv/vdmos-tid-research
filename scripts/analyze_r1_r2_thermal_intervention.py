#!/usr/bin/env python3
"""Build auditable R1/R2 temperature-intervention tables and figures.

This is a CPython-only postprocessor.  It reads the lossless SVisual-extracted
R1/R2 PLT CSVs and the recorded R2 TDR field audit; it never runs SDevice.
R2 has no transient Temperature equation: its Temperature TDRs are a frozen
loaded field, never a dynamic temperature time series.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "changes" / "2026-07-13-igbt-seb-现有数据复盘"
DATA = OUT / "data"
FIGURES = OUT / "figures"
R1_CSV = DATA / "r1_plt.csv"
R2_CSV = DATA / "r2_plt.csv"
R1_RUN = "A01_v2500_let15_y3p5_thermal__R1_thermo_coupled_to60__20260713T064449946Z__1d9cd23a"
R2_RUN = "A01_v2500_let15_y3p5_thermal__R2_thermo_locked_300_to60__20260713T093117597Z__4c085443"
R1_SOURCE = ROOT / "local_runtime" / "igbt_seb_thermal_runs" / R1_RUN / "artifacts" / "transient_r1_coupled.plt"
R2_SOURCE = ROOT / "local_runtime" / "igbt_seb_thermal_runs" / R2_RUN / "artifacts" / "transient_r2_locked300.plt"
R2_ARTIFACTS = ROOT / "local_runtime" / "igbt_seb_thermal_runs" / R2_RUN / "artifacts"
PRESTRIKE_CUTOFF_S = 9e-11
KEY_TIMES = (4e-10, 1e-8, 4e-8, 5e-8, 6e-8)
# Each derivative is central-differenced only within its uniform linear segment.
GRID_SEGMENTS = (
    ("pre_strike_0p1ps", 1e-13, 9e-11, 1e-13),
    ("ion_pulse_0p02ps", 9e-11, 1.2e-10, 2e-14),
    ("post_pulse_2ps", 1.2e-10, 4e-10, 2e-12),
    ("early_growth_0p1ns", 4e-10, 1e-8, 1e-10),
    ("late_growth_0p5ns", 1e-8, 6e-8, 5e-10),
)
# Read-only SVisual field audit, W-2024.09, executed 2026-07-13.  These values
# are deliberately retained as frozen-field snapshots rather than transient data.
R2_TDR_AUDIT = (
    ("pre", 0.0, "field_pre_des.tdr", 300.0, 324.6332156891672),
    ("0.4ns", 4e-10, "field_0p4ns_des.tdr", 300.0, 324.6332156891672),
    ("10ns", 1e-8, "field_10ns_des.tdr", 300.0, 324.6332156891672),
    ("40ns", 4e-8, "field_40ns_des.tdr", 300.0, 324.6332156891672),
    ("50ns", 5e-8, "field_50ns_des.tdr", 300.0, 324.6332156891672),
    ("60ns", 6e-8, "field_60ns_des.tdr", 300.0, 324.6332156891672),
)


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def read_plt(path: Path, variant: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for source_row, row in enumerate(csv.DictReader(handle), start=2):
            rows.append({
                "variant": variant, "time_s": float(row["time_s"]),
                "vce_v": float(row["collector_inner_voltage_v"]),
                "ic_a_um": float(row["collector_total_current_a_um"]),
                "tmax_k": float(row["plt_tmax_k"]) if row["plt_tmax_k"] else None,
                "source_row": source_row,
            })
    if not rows or rows[-1]["time_s"] != 6e-8:
        raise ValueError(f"{path} is empty or does not end at 60 ns")
    return rows


def bracket(rows: list[dict[str, Any]], time_s: float) -> tuple[dict[str, Any], dict[str, Any]]:
    for row in rows:
        if math.isclose(row["time_s"], time_s, rel_tol=0, abs_tol=max(1e-22, time_s * 1e-12)):
            return row, row
    for left, right in zip(rows, rows[1:]):
        if left["time_s"] < time_s < right["time_s"]:
            return left, right
    raise ValueError(f"Cannot bracket {time_s:g} s")


def interpolate(rows: list[dict[str, Any]], time_s: float) -> dict[str, Any]:
    left, right = bracket(rows, time_s)
    f = 0.0 if left is right else (time_s - left["time_s"]) / (right["time_s"] - left["time_s"])
    def value(name: str) -> float | None:
        if left[name] is None or right[name] is None:
            return None
        return float(left[name]) + f * (float(right[name]) - float(left[name]))
    return {
        "selection_method": "raw_exact" if left is right else "linear_interpolation",
        "time_s": time_s, "vce_v": value("vce_v"), "ic_a_um": value("ic_a_um"),
        "tmax_k": value("tmax_k"), "left_source_row": left["source_row"],
        "left_source_time_s": left["time_s"], "right_source_row": right["source_row"],
        "right_source_time_s": right["time_s"],
    }


def grid_for(rows: list[dict[str, Any]], variant: str, tpre_k: float | None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    energy = 0.0
    for segment, start, end, dt in GRID_SEGMENTS:
        count = round((end - start) / dt)
        points = []
        for i in range(count + 1):
            point = interpolate(rows, start + i * dt)
            point.update({"variant": variant, "segment_id": segment, "time_ns": point["time_s"] * 1e9,
                          "grid_dt_s": 0.0 if i == 0 else dt, "temperature_delivery":
                          "PLT_transient_scalar" if variant == "R1" else "TDR_frozen_field",
                          "r1_tpre_k": tpre_k if variant == "R1" else None,
                          "r1_delta_t_k": (point["tmax_k"] - tpre_k) if variant == "R1" else None})
            points.append(point)
        for i, point in enumerate(points):
            if i:
                prior = points[i - 1]
                energy += 0.5 * (abs(prior["vce_v"] * prior["ic_a_um"]) + abs(point["vce_v"] * point["ic_a_um"])) * dt
            point["power_w_um"] = abs(point["vce_v"] * point["ic_a_um"])
            point["cumulative_port_energy_j_um"] = energy
            if 0 < i < len(points) - 1:
                prior, following = points[i - 1], points[i + 1]
                point["d_log_abs_ic_dt_s_inv"] = (math.log(abs(following["ic_a_um"])) - math.log(abs(prior["ic_a_um"]))) / (2 * dt)
                point["d_r1_delta_t_dt_k_s"] = ((following["r1_delta_t_k"] - prior["r1_delta_t_k"]) / (2 * dt)
                                                  if variant == "R1" else None)
            else:
                point["d_log_abs_ic_dt_s_inv"] = None
                point["d_r1_delta_t_dt_k_s"] = None
        output.extend(points)
    return output


def write_csv(path: Path, rows: list[dict[str, Any]], header: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def r2_raw_long(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retain every native R2 PLT row and attach electrical-port diagnostics.

    Temperature values are intentionally absent: R2 only provides the separately
    audited, frozen TDR field snapshots.
    """
    output: list[dict[str, Any]] = []
    energy = 0.0
    previous: dict[str, Any] | None = None
    for row in rows:
        power = abs(row["vce_v"] * row["ic_a_um"])
        if previous is not None:
            dt = row["time_s"] - previous["time_s"]
            if dt <= 0:
                raise ValueError("R2 PLT times must be strictly increasing")
            prior_power = abs(previous["vce_v"] * previous["ic_a_um"])
            energy += 0.5 * (prior_power + power) * dt
        output.append({
            "sample_kind": "raw_plt",
            "variant": "R2",
            "time_s": row["time_s"],
            "time_ns": row["time_s"] * 1e9,
            "vce_v": row["vce_v"],
            "ic_a_um": row["ic_a_um"],
            "power_w_um": power,
            "cumulative_port_energy_j_um": energy,
            "source_csv": rel(R2_CSV),
            "source_plt": rel(R2_SOURCE),
            "source_row": row["source_row"],
            "temperature_delivery": "TDR_frozen_field",
            "temperature_equation_not_solved": True,
            "temperature_semantics": "No transient Tmax or deltaT; see r2_thermal_tdr_frozen_snapshots.csv.",
            "diagnostic_only": True,
        })
        previous = row
    return output


def save(fig: plt.Figure, name: str) -> None:
    for suffix in (".png", ".svg"):
        fig.savefig(FIGURES / f"{name}{suffix}", dpi=300 if suffix == ".png" else None, bbox_inches="tight")
    plt.close(fig)


def plot_ic(r1: list[dict[str, Any]], r2: list[dict[str, Any]]) -> None:
    fig, axis = plt.subplots(figsize=(10.2, 5.6))
    for label, rows, color in (("R1 fully coupled", r1, "#111111"), ("R2 locked electrical solve", r2, "#0072B2")):
        axis.plot([x["time_s"] for x in rows], [abs(x["ic_a_um"]) for x in rows], label=label, color=color, linewidth=1.5)
    axis.set(xscale="log", yscale="log", xlabel="Time (s)", ylabel="Collector current |Ic| (A/µm)",
             title="R1/R2 electrical intervention comparison: 2500 V, LET 15")
    axis.grid(True, which="both", linestyle=":", alpha=.35); axis.legend()
    fig.text(.5, .01, "R2 Temperature frozen / no transient Temperature equation. Electrical contrast only; diagnostic_only + MESH_SENSITIVE.", ha="center", fontsize=8.5)
    fig.tight_layout(rect=(.02,.05,.98,.98)); save(fig, "r1_r2_ic_intervention")


def plot_temperature(r1: list[dict[str, Any]]) -> None:
    fig, (left, right) = plt.subplots(1, 2, figsize=(11.3, 4.8))
    left.plot([x["time_s"] for x in r1], [x["r1_delta_t_k"] for x in r1], color="#c75520", linewidth=1.5)
    left.set(xscale="log", xlabel="Time (s)", ylabel="R1 ΔT = Tmax − Tpre (K)", title="R1: transient thermal solution")
    left.grid(True, which="both", linestyle=":", alpha=.35)
    t = [row[1] if row[1] else 1e-13 for row in R2_TDR_AUDIT]
    frozen = [row[4] for row in R2_TDR_AUDIT]
    right.plot(t, frozen, "s--", color="#0072B2", label="frozen field Tmax")
    right.set(xscale="log", xlabel="Saved time label (s)", ylabel="R2 frozen field Tmax (K)", title="R2: same loaded Temperature field at all snapshots")
    right.grid(True, which="both", linestyle=":", alpha=.35)
    right.text(.5,.18,"R2 Temperature frozen\nno transient Temperature equation\nNOT a dynamic temperature trace", transform=right.transAxes, ha="center", va="center", fontsize=9, weight="bold", bbox={"facecolor":"white","alpha":.9,"edgecolor":"#0072B2"})
    fig.tight_layout(); save(fig, "r1_r2_temperature_semantics")


def plot_keypoints(keys: list[dict[str, Any]]) -> None:
    fig, (a, b) = plt.subplots(1, 2, figsize=(11.3, 4.8))
    labels = [f"{x['target_time_ns']:g}" for x in keys]
    x = list(range(len(keys)))
    a.plot(x, [abs(k["r1_ic_a_um"]) for k in keys], "o-", label="R1", color="#111111")
    a.plot(x, [abs(k["r2_ic_a_um"]) for k in keys], "s-", label="R2", color="#0072B2")
    a.set(yscale="log", xticks=x, xticklabels=labels, xlabel="Target time (ns)", ylabel="|Ic| (A/µm)", title="Key-point current")
    a.grid(True, which="both", linestyle=":", alpha=.35); a.legend()
    b.plot(x, [k["r1_cumulative_port_energy_j_um"] for k in keys], "o-", label="R1", color="#111111")
    b.plot(x, [k["r2_cumulative_port_energy_j_um"] for k in keys], "s-", label="R2", color="#0072B2")
    b.set(xticks=x, xticklabels=labels, xlabel="Target time (ns)", ylabel="Cumulative |Vce·Ic| dt (J/µm)", title="Key-point port energy")
    b.grid(True, linestyle=":", alpha=.35); b.legend()
    fig.text(.5,.01,"R2 Temperature frozen / no transient Temperature equation. Energy is an electrical-port diagnostic, not a thermal-energy balance.", ha="center", fontsize=8.2)
    fig.tight_layout(rect=(.02,.05,.98,.98)); save(fig, "r1_r2_keypoints_energy")


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True); FIGURES.mkdir(parents=True, exist_ok=True)
    r1_raw, r2_raw = read_plt(R1_CSV, "R1"), read_plt(R2_CSV, "R2")
    r1_tpre = [x["tmax_k"] for x in r1_raw if x["time_s"] <= PRESTRIKE_CUTOFF_S][-1]
    r1, r2 = grid_for(r1_raw, "R1", r1_tpre), grid_for(r2_raw, "R2", None)
    r2_long = r2_raw_long(r2_raw)
    r2_long_header = ["sample_kind", "variant", "time_s", "time_ns", "vce_v", "ic_a_um", "power_w_um", "cumulative_port_energy_j_um", "source_csv", "source_plt", "source_row", "temperature_delivery", "temperature_equation_not_solved", "temperature_semantics", "diagnostic_only"]
    write_csv(DATA / "r2_thermal_electrical_long.csv", r2_long, r2_long_header)
    header = ["variant","segment_id","time_s","time_ns","grid_dt_s","selection_method","left_source_row","left_source_time_s","right_source_row","right_source_time_s","vce_v","ic_a_um","power_w_um","cumulative_port_energy_j_um","d_log_abs_ic_dt_s_inv","temperature_delivery","tmax_k","r1_tpre_k","r1_delta_t_k","d_r1_delta_t_dt_k_s"]
    write_csv(DATA / "r1_r2_intervention_linear_grid_long.csv", r1 + r2, header)
    def grid_point(points: list[dict[str, Any]], target_s: float) -> dict[str, Any]:
        point = min(points, key=lambda row: abs(row["time_s"] - target_s))
        if not math.isclose(point["time_s"], target_s, rel_tol=0, abs_tol=1e-21):
            raise ValueError(f"Uniform grid lacks key time {target_s:g} s")
        return point

    frozen = {t: tmax for _, t, _, _, tmax in R2_TDR_AUDIT}
    keys = []
    for time_s in KEY_TIMES:
        one, two = grid_point(r1, time_s), grid_point(r2, time_s)
        keys.append({"target_time_s":time_s,"target_time_ns":time_s*1e9,"interpolation_label":"both variants piecewise-linear on declared uniform linear grid; raw_exact when source has target","r1_ic_a_um":one["ic_a_um"],"r2_ic_a_um":two["ic_a_um"],"r1_minus_r2_ic_a_um":one["ic_a_um"]-two["ic_a_um"],"r1_to_r2_ic_ratio":one["ic_a_um"]/two["ic_a_um"],"r1_power_w_um":one["power_w_um"],"r2_power_w_um":two["power_w_um"],"r1_cumulative_port_energy_j_um":one["cumulative_port_energy_j_um"],"r2_cumulative_port_energy_j_um":two["cumulative_port_energy_j_um"],"r1_tmax_k":one["tmax_k"],"r1_delta_t_k":one["r1_delta_t_k"],"r2_frozen_field_tmax_k":frozen[time_s],"r2_temperature_semantics":"TDR_frozen_field; not transient Tmax and no deltaT","diagnostic_only":True,"interpretation_boundary":"MESH_SENSITIVE; A01 INDETERMINATE; no causal acceptance gate passed."})
    key_header = list(keys[0])
    write_csv(DATA / "r1_r2_intervention_key_points.csv", keys, key_header)
    tdr_rows = [{"checkpoint_id":label,"time_s":time_s,"time_ns":time_s*1e9,"source_tdr":rel(R2_ARTIFACTS/file_name),"temperature_variable":"LatticeTemperature","tmin_k":tmin,"frozen_field_tmax_k":tmax,"temperature_delivery":"TDR_frozen_field","interpretation":"Frozen loaded field; do not use as dynamic Tmax or ΔT."} for label,time_s,file_name,tmin,tmax in R2_TDR_AUDIT]
    write_csv(DATA / "r2_thermal_tdr_frozen_snapshots.csv", tdr_rows, list(tdr_rows[0]))
    sidecar = {"schema_version":"igbt_seb_r2_locked_sidecar/v1","thermal_variant_id":"R2_ELECTRICAL_LOCKED_TEMPERATURE_FIELD","run_id":R2_RUN,"lifecycle":"SUCCEEDED","exit_code":0,"time_end_s":6e-8,"source_plt":rel(R2_SOURCE),"plt_sample_count":len(r2_raw),"r2_electrical_long_csv":rel(DATA / "r2_thermal_electrical_long.csv"),"r2_electrical_long_row_count":len(r2_long),"plt_variables_used":["time","Collector InnerVoltage","Collector TotalCurrent"],"plt_tmax":"ABSENT","temperature_delivery":"TDR_frozen_field","temperature_equation_not_solved":True,"temperature_equation":"NOT coupled in transient solves: Coupled {Poisson Electron Hole}","tdr_temperature_snapshots":tdr_rows,"interpretation_boundary":"Frozen TDR field provides a loading-state audit only. It is not a transient temperature solution; no R2 dynamic Tmax, ΔT, or thermal derivative is reported.","diagnostic_only":True,"mesh_status":"MESH_SENSITIVE","a01_status":"INDETERMINATE"}
    (DATA / "r2_thermal_sidecar.json").write_text(json.dumps(sidecar, indent=2, ensure_ascii=False), encoding="utf-8")
    plot_ic(r1, r2); plot_temperature(r1); plot_keypoints(keys)
    if len(r1_raw) < 2 or len(r2_raw) < 2:
        raise ValueError("PLT must contain at least two native samples per variant")
    if r1_raw[-1]["time_s"] != 6e-8 or r2_raw[-1]["time_s"] != 6e-8:
        raise ValueError("PLT endpoint must be exactly 60 ns")
    if len(r1) != len(r2) or not r2_long or r2_long[-1]["time_s"] != 6e-8:
        raise ValueError("Derived grid/R2 long-table endpoint mismatch")
    if any(not math.isclose(grid_point(r1, k["target_time_s"])["time_s"], k["target_time_s"], rel_tol=0, abs_tol=1e-21) or not math.isclose(grid_point(r2, k["target_time_s"])["time_s"], k["target_time_s"], rel_tol=0, abs_tol=1e-21) for k in keys):
        raise ValueError("Missing key time")
    print(json.dumps({"r1_plt_rows":len(r1_raw),"r2_plt_rows":len(r2_raw),"grid_rows_per_variant":len(r1),"r2_long_rows":len(r2_long),"key_rows":len(keys),"r1_60ns":keys[-1],"r2_frozen_tmax_k":frozen[6e-8]}, indent=2))

if __name__ == "__main__":
    main()