#!/usr/bin/env python3
"""Build a read-only, traceable analysis dataset for the frozen IGBT-SEB runs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DATA = (
    ROOT
    / "docs"
    / "changes"
    / "2026-07-11-igbt-seb-paper-reproduction"
    / "data"
)
DEFAULT_RUNTIME_ROOT = ROOT / "local_runtime" / "igbt_seb_full_20260712_035027"
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "docs"
    / "changes"
    / "2026-07-13-igbt-seb-现有数据复盘"
    / "data"
)

LINEAGE_HEADER = [
    "folder_id",
    "registry_case_id",
    "registry_attempt_id",
    "parent_run_id",
    "phase",
    "role",
    "eligibility",
    "status",
    "registry_presence",
    "folder_presence",
    "parameter_attempt_id",
    "parameter_phase",
    "metadata_status",
    "deck_sha256",
    "mesh_sha256",
    "source_path",
    "folder_path",
    "parameter_path",
]
COMMON_TIME_HEADER = [
    "variant_axis",
    "variant_value",
    "folder_id",
    "target_time_ns",
    "sample_time_ns",
    "left_sample_time_ns",
    "right_sample_time_ns",
    "sampling_method",
    "vce_v",
    "ic_a_um",
    "tmax_k",
    "power_w_um",
    "trend",
    "eligibility",
    "source_path",
]
DIAGNOSTIC_HEADER = [
    "diagnostic_type",
    "comparison_axis",
    "variant",
    "time_ns",
    "metric",
    "value",
    "unit",
    "comparator",
    "delta",
    "gate",
    "interpretation",
    "conclusion_scope",
    "source_path",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader)


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def normalized(row: dict[str, object], header: list[str]) -> dict[str, str]:
    return {
        name: "NA" if row.get(name) in (None, "") else str(row[name])
        for name in header
    }


def write_csv(path: Path, header: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(normalized(row, header) for row in rows)


def role_for_phase(phase: str) -> tuple[str, str]:
    if phase == "anchor":
        return "anchor_attempt", "anchor_observation_only"
    if phase == "smoke":
        return "input_smoke", "smoke_only"
    if phase in {"input_audit", "wt_hi_charge_audit"}:
        return "input_audit", "input_audit_only"
    if phase in {"execution_benchmark", "mesh_sensitivity_dc_benchmark"}:
        return "performance_probe", "performance_only"
    if phase in {"diagnostic", "mesh_sensitivity_dc_bias"}:
        return "failure_recovery", "diagnostic_only"
    return "physical_sensitivity", "diagnostic_only"


def parameter_metadata(path: Path, row: dict[str, str]) -> tuple[str, str, str]:
    if not path.is_file():
        return "NA", "NA", "NO_PARAMETERS_FILE"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "NA", "NA", "UNREADABLE_PARAMETERS"

    parameter_attempt = str(data.get("attempt_id", "NA"))
    parameter_phase = str(data.get("phase", "NA"))
    conflicts = []
    if str(data.get("case_id", row["case_id"])) != row["case_id"]:
        conflicts.append("case_id")
    if parameter_attempt != row["attempt_id"]:
        conflicts.append("attempt_id")
    if parameter_phase != "NA" and parameter_phase != row["phase"]:
        conflicts.append("phase")
    status = "MATCH" if not conflicts else "METADATA_CONFLICT:" + "+".join(conflicts)
    return parameter_attempt, parameter_phase, status


def build_lineage(source_data: Path, runtime_root: Path) -> list[dict[str, object]]:
    registry_path = source_data / "case_summary.csv"
    registry_rows = read_csv(registry_path)
    cases_root = runtime_root / "cases"
    folders = {path.name: path for path in cases_root.iterdir() if path.is_dir()}
    rows: list[dict[str, object]] = []
    registered_folders = set()

    for row in registry_rows:
        folder_id = f"{row['case_id']}__{row['attempt_id']}"
        registered_folders.add(folder_id)
        folder = folders.get(folder_id)
        parameter_path = folder / "parameters.json" if folder else None
        parameter_attempt, parameter_phase, metadata_status = parameter_metadata(
            parameter_path, row
        ) if parameter_path else ("NA", "NA", "FOLDER_MISSING")
        role, eligibility = role_for_phase(row["phase"])
        rows.append(
            {
                "folder_id": folder_id,
                "registry_case_id": row["case_id"],
                "registry_attempt_id": row["attempt_id"],
                "parent_run_id": row["parent_run_id"],
                "phase": row["phase"],
                "role": role,
                "eligibility": eligibility,
                "status": row["status"],
                "registry_presence": "REGISTERED",
                "folder_presence": "PRESENT" if folder else "MISSING",
                "parameter_attempt_id": parameter_attempt,
                "parameter_phase": parameter_phase,
                "metadata_status": metadata_status,
                "deck_sha256": row["deck_sha256"],
                "mesh_sha256": row["mesh_sha256"],
                "source_path": relative(registry_path),
                "folder_path": relative(folder) if folder else "NA",
                "parameter_path": relative(parameter_path)
                if parameter_path and parameter_path.is_file()
                else "NA",
            }
        )

    for folder_id in sorted(set(folders) - registered_folders):
        folder = folders[folder_id]
        parameter_path = folder / "parameters.json"
        parameter_attempt = "NA"
        parameter_phase = "NA"
        metadata_status = "UNREGISTERED_DIRECTORY"
        if parameter_path.is_file():
            try:
                data = json.loads(parameter_path.read_text(encoding="utf-8"))
                parameter_attempt = str(data.get("attempt_id", "NA"))
                parameter_phase = str(data.get("phase", "NA"))
            except (OSError, json.JSONDecodeError):
                metadata_status += ":UNREADABLE_PARAMETERS"
        rows.append(
            {
                "folder_id": folder_id,
                "registry_case_id": "NA",
                "registry_attempt_id": "NA",
                "parent_run_id": "NA",
                "phase": "unregistered",
                "role": "historical_or_incomplete_directory",
                "eligibility": "not_in_controlled_ledger",
                "status": "UNREGISTERED_DIRECTORY",
                "registry_presence": "UNREGISTERED",
                "folder_presence": "PRESENT",
                "parameter_attempt_id": parameter_attempt,
                "parameter_phase": parameter_phase,
                "metadata_status": metadata_status,
                "deck_sha256": "NA",
                "mesh_sha256": "NA",
                "source_path": relative(folder),
                "folder_path": relative(folder),
                "parameter_path": relative(parameter_path)
                if parameter_path.is_file()
                else "NA",
            }
        )

    if len(registry_rows) != 28:
        raise ValueError(f"Expected 28 controlled records, found {len(registry_rows)}")
    if len(folders) != 32:
        raise ValueError(f"Expected 32 case directories, found {len(folders)}")
    return rows


def load_common_time(
    path: Path,
    variant_axis: str,
    variant_value: str,
    folder_id: str,
) -> list[dict[str, object]]:
    rows = []
    for source in read_csv(path):
        target_ns = float(source["target_time_s"]) * 1e9
        has_exact_sample = "sample_time_s" in source
        rows.append(
            {
                "variant_axis": variant_axis,
                "variant_value": variant_value,
                "folder_id": folder_id,
                "target_time_ns": f"{target_ns:g}",
                "sample_time_ns": f"{float(source['sample_time_s']) * 1e9:g}"
                if has_exact_sample
                else "NA",
                "left_sample_time_ns": f"{float(source['left_sample_time_s']) * 1e9:g}"
                if source.get("left_sample_time_s")
                else "NA",
                "right_sample_time_ns": f"{float(source['right_sample_time_s']) * 1e9:g}"
                if source.get("right_sample_time_s")
                else "NA",
                "sampling_method": "exact_or_preinterpolated"
                if has_exact_sample
                else "linear_interpolation_between_samples",
                "vce_v": source["vce_v"],
                "ic_a_um": source["ic_a_um"],
                "tmax_k": source["tmax_k"],
                "power_w_um": source["power_w_um"],
                "trend": "GROWING",
                "eligibility": "diagnostic_only",
                "source_path": relative(path),
            }
        )
    return rows


def build_common_time(source_data: Path, runtime_root: Path) -> list[dict[str, object]]:
    cases = runtime_root / "cases"
    rows: list[dict[str, object]] = []

    baseline_public = source_data / "a01_wt_hi_sensitivity.csv"
    baseline_10 = next(
        row
        for row in read_csv(baseline_public)
        if row["wt_um"] == "0.1" and row["time_ns"] == "10"
    )
    rows.append(
        {
            "variant_axis": "baseline",
            "variant_value": "Wt0.1_Y3.5_thermal_steady_baseline_mesh",
            "folder_id": "A01_v2500_let15_y3p5__attempt07_A40_60",
            "target_time_ns": "10",
            "sample_time_ns": "10",
            "left_sample_time_ns": "NA",
            "right_sample_time_ns": "NA",
            "sampling_method": "published_target_value",
            "vce_v": baseline_10["vce_v"],
            "ic_a_um": baseline_10["ic_a_um"],
            "tmax_k": baseline_10["tmax_k"],
            "power_w_um": str(float(baseline_10["vce_v"]) * float(baseline_10["ic_a_um"])),
            "trend": baseline_10["trend"],
            "eligibility": "diagnostic_only",
            "source_path": relative(baseline_public),
        }
    )

    specifications = [
        (
            "baseline",
            "Wt0.1_Y3.5_thermal_steady_baseline_mesh",
            "A01_v2500_let15_y3p5__attempt07_A40_60",
            "baseline_common_time_summary.csv",
        ),
        (
            "mesh",
            "track_core_half",
            "A01_v2500_let15_y3p5__attempt18_meshhalf_transient_to60",
            "common_time_summary.csv",
        ),
        (
            "wt_hi",
            "0.2_um",
            "A01_v2500_let15_y3p5__attempt19_wt0p2_transient_to60",
            "common_time_summary.csv",
        ),
        (
            "wt_hi",
            "0.5_um",
            "A01_v2500_let15_y3p5__attempt21_wt0p5_transient_to60",
            "common_time_summary.csv",
        ),
        (
            "thermal_initial_state",
            "cold300_nonsteady",
            "A01_v2500_let15_y3p5__attempt24_cold300_transient_to60",
            "common_time_summary.csv",
        ),
        (
            "position",
            "Y3.4_um",
            "A01_v2500_let15_y3p4__attempt25_position_transient_to60",
            "common_time_summary.csv",
        ),
        (
            "position",
            "Y3.6_um",
            "A01_v2500_let15_y3p6__attempt26_position_transient_to60",
            "common_time_summary.csv",
        ),
    ]
    for axis, value, folder_id, filename in specifications:
        rows.extend(load_common_time(cases / folder_id / filename, axis, value, folder_id))

    if len(rows) != 28:
        raise ValueError(f"Expected 28 common-time rows, found {len(rows)}")
    return sorted(rows, key=lambda row: (str(row["variant_axis"]), str(row["variant_value"]), float(row["target_time_ns"])))


def evidence_row(
    diagnostic_type: str,
    comparison_axis: str,
    variant: str,
    time_ns: str,
    metric: str,
    value: object,
    unit: str,
    comparator: object,
    delta: object,
    gate: str,
    interpretation: str,
    source_path: Path,
) -> dict[str, object]:
    return {
        "diagnostic_type": diagnostic_type,
        "comparison_axis": comparison_axis,
        "variant": variant,
        "time_ns": time_ns,
        "metric": metric,
        "value": value,
        "unit": unit,
        "comparator": comparator,
        "delta": delta,
        "gate": gate,
        "interpretation": interpretation,
        "conclusion_scope": "diagnostic_only",
        "source_path": relative(source_path),
    }


def build_diagnostics(source_data: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    charge_path = source_data / "heavyion_charge_audit.csv"
    charge = {row["time_ps"]: row["trapezoid_charge_pc"] for row in read_csv(charge_path)}
    rows.append(
        evidence_row(
            "heavyion_charge_closure",
            "full_pulse_charge",
            "Wt0.1_um",
            "92-108_ps",
            "integrated_charge",
            charge["SUMMARY"],
            "pC",
            charge["NOMINAL"],
            str(float(charge["RELATIVE_ERROR"]) * 100),
            charge["CLOSURE"],
            "总电荷闭合排除明显输入电荷错误，但不验证局部沉积分布唯一正确",
            charge_path,
        )
    )

    solver_path = source_data / "solver_benchmark_summary.csv"
    solver_rows = read_csv(solver_path)
    baseline_speed = float(solver_rows[0]["wall_s_per_advanced_ns"])
    for row in solver_rows:
        speed = float(row["wall_s_per_advanced_ns"])
        rows.append(
            evidence_row(
                "solver_ablation",
                "solver_controls",
                row["variant"],
                "40-60",
                "wall_s_per_advanced_ns",
                row["wall_s_per_advanced_ns"],
                "s/ns",
                baseline_speed,
                f"{(speed / baseline_speed - 1) * 100:.6f}%",
                "ACCEPTED" if row["accepted"].lower() == "true" else "REJECTED",
                f"{row['run_status']}; physical_equivalence={row['physical_equivalence']}",
                solver_path,
            )
        )

    mesh_path = source_data / "a01_meshhalf_transient_comparison.csv"
    for row in read_csv(mesh_path):
        rows.append(
            evidence_row(
                "mesh_sensitivity",
                "track_core_mesh",
                "meshhalf_vs_baseline",
                row["time_ns"],
                "ic_relative_difference",
                row["ic_relative_difference_pct"],
                "%",
                "2% acceptance gate",
                row["tmax_difference_k"] + " K Tmax difference",
                row["row_result"],
                "晚时刻电流差异用于网格门，不直接作 SEB 分类",
                mesh_path,
            )
        )

    field_path = source_data / "a01_field_evidence.csv"
    for row in read_csv(field_path):
        for metric, unit in (
            ("emax_v_cm", "V/cm"),
            ("impact_line_integral_cm2_s", "cm^-2 s^-1"),
            ("pbody_minus_nplus_proxy_v", "V"),
        ):
            rows.append(
                evidence_row(
                    "local_field_evidence",
                    "track_core_mesh",
                    row["mesh_variant"],
                    row["time_ns"],
                    metric,
                    row[metric],
                    unit,
                    "same metric on adjacent mesh",
                    "NA",
                    "MESH_SENSITIVE",
                    "局部雪崩—寄生 NPN 代理量尚未形成网格无关因果链",
                    field_path,
                )
            )

    wt_path = source_data / "a01_wt_hi_sensitivity.csv"
    for row in read_csv(wt_path):
        if row["time_ns"] != "60":
            continue
        rows.append(
            evidence_row(
                "wt_hi_sensitivity",
                "radial_width",
                row["wt_um"] + "_um",
                "60",
                "ic_difference_vs_wt0p1",
                row["ic_difference_vs_wt0p1_pct"],
                "%",
                "Wt0.1_um",
                row["charge_error_pct"] + "% charge error",
                row["charge_gate"],
                "展宽改变晚时刻幅值，但所有变体仍持续增长",
                wt_path,
            )
        )

    thermal_path = source_data / "a01_thermal_initial_state_sensitivity.csv"
    thermal_rows = [row for row in read_csv(thermal_path) if row["time_ns"] == "60"]
    thermal_baseline = float(next(row for row in thermal_rows if row["initial_state"] == "thermal_steady")["ic_a_um"])
    for row in thermal_rows:
        delta = (float(row["ic_a_um"]) / thermal_baseline - 1) * 100
        rows.append(
            evidence_row(
                "thermal_initial_state",
                "initial_temperature_state",
                row["initial_state"],
                "60",
                "ic_difference_vs_thermal_steady",
                f"{delta:.6f}",
                "%",
                "thermal_steady",
                row["initial_tmax_k"] + " K initial Tmax",
                "TREND_NOT_REVERSED",
                "冷态对照未削弱后期增长，不能据此认定热边界已验证",
                thermal_path,
            )
        )

    position_path = source_data / "a01_position_sensitivity.csv"
    for row in read_csv(position_path):
        if row["time_ns"] != "60" or row["y_um"] == "3.5":
            continue
        rows.append(
            evidence_row(
                "local_position_sensitivity",
                "strike_y",
                "Y" + row["y_um"] + "_um",
                "60",
                "ic_difference_vs_y3p5",
                row["ic_difference_vs_y3p5_pct"],
                "%",
                "Y3.5_um",
                row["tmax_difference_vs_y3p5_k"] + " K Tmax difference",
                "TREND_NOT_REVERSED",
                "仅为局部偏移诊断，不是正式位置扫描",
                position_path,
            )
        )

    thread_path = source_data / "a01_meshhalf_dc_thread_benchmark.csv"
    for row in read_csv(thread_path):
        rows.append(
            evidence_row(
                "thread_performance",
                "threads",
                row["threads"] + "_thread",
                "DC_probe_300s",
                "last_converged_vce",
                row["last_converged_vce_v"],
                "V",
                "equal wall budget",
                row["cpu_user_s"] + " CPU user s",
                row["decision"],
                "只支持当前 DC 探针的资源选择，不外推为通用线程规律",
                thread_path,
            )
        )
    return rows


def validate_outputs(
    lineage: list[dict[str, object]],
    common_time: list[dict[str, object]],
    diagnostics: list[dict[str, object]],
) -> None:
    folder_ids = [str(row["folder_id"]) for row in lineage]
    if len(folder_ids) != len(set(folder_ids)):
        raise ValueError("Lineage folder_id is not unique")
    if sum(row["registry_presence"] == "REGISTERED" for row in lineage) != 28:
        raise ValueError("Registered lineage count is not 28")
    if sum(row["registry_presence"] == "UNREGISTERED" for row in lineage) != 4:
        raise ValueError("Unregistered directory count is not 4")
    if any(row["eligibility"] != "diagnostic_only" for row in common_time):
        raise ValueError("Common-time data escaped diagnostic scope")
    baseline_60 = next(
        row
        for row in common_time
        if row["variant_axis"] == "baseline" and row["target_time_ns"] == "60"
    )
    if abs(float(baseline_60["ic_a_um"]) - 0.000760421515043) > 1e-15:
        raise ValueError("Baseline 60 ns current does not match frozen evidence")
    if not diagnostics or any(row["conclusion_scope"] != "diagnostic_only" for row in diagnostics):
        raise ValueError("Diagnostic evidence scope is incomplete")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-data", type=Path, default=DEFAULT_SOURCE_DATA)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    lineage = build_lineage(args.source_data, args.runtime_root)
    common_time = build_common_time(args.source_data, args.runtime_root)
    diagnostics = build_diagnostics(args.source_data)
    validate_outputs(lineage, common_time, diagnostics)

    write_csv(args.output_dir / "运行谱系表.csv", LINEAGE_HEADER, lineage)
    write_csv(args.output_dir / "共同时间指标.csv", COMMON_TIME_HEADER, common_time)
    write_csv(args.output_dir / "诊断证据表.csv", DIAGNOSTIC_HEADER, diagnostics)
    print(
        "analysis dataset built: "
        f"lineage={len(lineage)}, common_time={len(common_time)}, diagnostics={len(diagnostics)}"
    )


if __name__ == "__main__":
    main()