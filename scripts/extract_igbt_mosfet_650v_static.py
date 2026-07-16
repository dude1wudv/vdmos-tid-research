#!/usr/bin/env python3
"""Extract auditable static gates for the independent 650 V IGBT/MOSFET models."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = ROOT / "local_runtime" / "tcad_projects" / "igbt_mosfet_650v_seb_20260715"
DEFAULT_REPORT_DATA = ROOT / "docs" / "changes" / "2026-07-15-igbt-mosfet-650v-redesign" / "data"
DEVICE_DSL = {
    "IGBT": ROOT / "projects" / "igbt_mosfet_650v_seb_20260715" / "devices" / "igbt_650v.json",
    "MOSFET": ROOT / "projects" / "igbt_mosfet_650v_seb_20260715" / "devices" / "mosfet_650v_sj.json",
}
FLOAT = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def parse_dfise_plt(path: Path) -> list[dict[str, float]]:
    text = path.read_text(encoding="utf-8-sig")
    dataset_match = re.search(r"datasets\s*=\s*\[(.*?)\]\s*functions\s*=", text, re.DOTALL)
    data_match = re.search(r"\bData\s*\{(.*)\}\s*$", text, re.DOTALL)
    if dataset_match is None or data_match is None:
        raise ValueError(f"not a supported DF-ISE text PLT: {path}")
    datasets = re.findall(r'"([^"]+)"', dataset_match.group(1))
    values = [float(token) for token in FLOAT.findall(data_match.group(1))]
    if not datasets or len(values) % len(datasets):
        raise ValueError(f"PLT dataset/value cardinality mismatch: {path}")
    return [
        dict(zip(datasets, values[index:index + len(datasets)]))
        for index in range(0, len(values), len(datasets))
    ]


def bracket_by_x(rows: list[dict[str, float]], x_name: str, target: float) -> tuple[dict[str, float], dict[str, float]]:
    ordered = sorted(rows, key=lambda row: row[x_name])
    for row in ordered:
        if math.isclose(row[x_name], target, rel_tol=0.0, abs_tol=max(1e-12, abs(target) * 1e-12)):
            return row, row
    for left, right in zip(ordered, ordered[1:]):
        if left[x_name] < target < right[x_name]:
            return left, right
    raise ValueError(f"cannot bracket {x_name}={target:g}")


def interpolate_y(rows: list[dict[str, float]], x_name: str, y_name: str, target: float) -> dict[str, Any]:
    left, right = bracket_by_x(rows, x_name, target)
    fraction = 0.0 if left is right else (target - left[x_name]) / (right[x_name] - left[x_name])
    value = left[y_name] + fraction * (right[y_name] - left[y_name])
    return {
        "value": value,
        "selection_method": "raw_exact" if left is right else "linear_interpolation",
        "left_x": left[x_name],
        "right_x": right[x_name],
    }


def crossing_voltage_log_current(
    rows: list[dict[str, float]], voltage_name: str, current_name: str, criterion_a_um: float
) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: row[voltage_name])
    for left, right in zip(ordered, ordered[1:]):
        left_current = abs(left[current_name])
        right_current = abs(right[current_name])
        if left_current <= criterion_a_um <= right_current and right_current > left_current:
            if left_current > 0 and not math.isclose(left_current, right_current):
                fraction = (
                    math.log10(criterion_a_um) - math.log10(left_current)
                ) / (math.log10(right_current) - math.log10(left_current))
                voltage = left[voltage_name] + fraction * (right[voltage_name] - left[voltage_name])
                method = "log_current_interpolation"
            else:
                fraction = (criterion_a_um - left_current) / (right_current - left_current)
                voltage = left[voltage_name] + fraction * (right[voltage_name] - left[voltage_name])
                method = "linear_current_interpolation"
            return {
                "voltage_v": voltage,
                "selection_method": method,
                "left_voltage_v": left[voltage_name],
                "left_current_a_um": left_current,
                "right_voltage_v": right[voltage_name],
                "right_current_a_um": right_current,
            }
    raise ValueError(f"current criterion {criterion_a_um:g} A/um is not crossed")


def first_raw_current_crossing(
    rows: list[dict[str, float]], voltage_name: str, current_name: str, criterion_a_um: float
) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: row[voltage_name])
    for index, row in enumerate(ordered):
        current = abs(row[current_name])
        if current >= criterion_a_um:
            prior = ordered[index - 1] if index else None
            return {
                "bv_v": row[voltage_name],
                "current_a_um": current,
                "selection_method": "first_raw_sample_meeting_electrical_criterion",
                "prior_voltage_v": prior[voltage_name] if prior else None,
                "prior_current_a_um": abs(prior[current_name]) if prior else None,
            }
    raise ValueError(f"BV current criterion {criterion_a_um:g} A/um is not crossed")


def load_succeeded_run(runs_root: Path, run_id: str, family: str) -> tuple[Path, dict[str, Any]]:
    run_dir = runs_root / run_id
    manifest_path = run_dir / "run_manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("run_id") != run_id or manifest.get("device_family") != family:
        raise ValueError(f"run identity mismatch: {run_id}")
    if manifest.get("lifecycle") != "SUCCEEDED" or str(manifest.get("exit_code")) != "0":
        raise ValueError(f"static evidence must be a successful run: {run_id}")
    scheduling = manifest.get("scheduling_evidence", {})
    if not (
        manifest.get("sdevice_threads") == 1
        and scheduling.get("lease_acquired") is True
        and scheduling.get("lease_released") is True
        and scheduling.get("affinity_verification") == "VERIFIED"
    ):
        raise ValueError(f"run lacks mandatory single-thread lease evidence: {run_id}")
    return run_dir, manifest


def source_record(run_dir: Path, manifest: dict[str, Any], plt_path: Path) -> dict[str, Any]:
    return {
        "run_id": manifest["run_id"],
        "run_manifest": relative(run_dir / "run_manifest.json"),
        "run_manifest_sha256": sha256(run_dir / "run_manifest.json"),
        "source_plt": relative(plt_path),
        "source_plt_sha256": sha256(plt_path),
        "mesh_sha256": next(item["sha256"] for item in manifest["inputs"] if item["relative_path"].endswith("_msh.tdr")),
        "scheduling_evidence": manifest["scheduling_evidence"],
    }


def device_result(
    runtime: Path,
    family: str,
    run_ids: dict[str, str],
    mesh_variant: str,
    fixed_area_factor: float | None = None,
    expected_mesh_sha256: str | None = None,
) -> dict[str, Any]:
    spec_path = DEVICE_DSL[family]
    spec = read_json(spec_path)
    stem = family.lower()
    high = "Collector" if family == "IGBT" else "Drain"
    targets = spec["static_targets"]
    run_files = {
        "bv": f"{stem}_bv.plt",
        "conduction": f"Conduction_{stem}_conduction.plt",
        "vth": f"Vth_{stem}_vth.plt",
        "off_leakage": f"OffLeakage_{stem}_off_leakage.plt",
    }
    rows: dict[str, list[dict[str, float]]] = {}
    sources: dict[str, dict[str, Any]] = {}
    for kind, run_id in run_ids.items():
        run_dir, manifest = load_succeeded_run(runtime / "runs", run_id, family)
        allowed_manifest_variants = {mesh_variant, "seed_baseline"} if mesh_variant == "baseline" else {mesh_variant}
        if manifest.get("mesh_variant") not in allowed_manifest_variants:
            raise ValueError(f"{run_id}: expected mesh_variant={mesh_variant}")
        plt_path = run_dir / "artifacts" / run_files[kind]
        rows[kind] = parse_dfise_plt(plt_path)
        sources[kind] = source_record(run_dir, manifest, plt_path)
    mesh_hashes = {source["mesh_sha256"] for source in sources.values()}
    if len(mesh_hashes) != 1:
        raise ValueError(f"{family} {mesh_variant} run set does not bind one immutable mesh")
    mesh_sha256 = next(iter(mesh_hashes))
    if expected_mesh_sha256 is not None and mesh_sha256 != expected_mesh_sha256:
        raise ValueError(f"{family} {mesh_variant} mesh hash mismatch")

    high_voltage = f"{high} InnerVoltage"
    high_current = f"{high} ConductionCurrent"
    high_current_abs = f"{high} AbsoluteConductionCurrent"
    for test_rows in rows.values():
        for row in test_rows:
            row[high_current] = row[f"{high} eCurrent"] + row[f"{high} hCurrent"]
            row[high_current_abs] = abs(row[high_current])
    conduction_target = targets["conduction"]
    target_total_current = float(conduction_target["current_a"])
    if family == "IGBT":
        calibration_voltage = float(conduction_target["typ_voltage_v"])
        conduction_quantity = "VCE_sat"
        baseline_calibrated_value = calibration_voltage
        max_value = float(conduction_target["max_voltage_v"])
    else:
        calibration_voltage = float(conduction_target["typ_resistance_ohm"]) * target_total_current
        conduction_quantity = "RDS_on"
        baseline_calibrated_value = float(conduction_target["typ_resistance_ohm"])
        max_value = float(conduction_target["max_resistance_ohm"])
    raw_on = interpolate_y(rows["conduction"], high_voltage, high_current_abs, calibration_voltage)
    raw_on_current = float(raw_on["value"])
    if raw_on_current <= 0:
        raise ValueError(f"non-positive on-state current for {family}")
    diagnostic_area_factor = target_total_current / raw_on_current
    area_factor = diagnostic_area_factor if fixed_area_factor is None else float(fixed_area_factor)
    if not math.isfinite(area_factor) or area_factor <= 0:
        raise ValueError(f"invalid AreaFactor for {family}")
    raw_target_current = target_total_current / area_factor
    on_voltage = interpolate_y(rows["conduction"], high_current_abs, high_voltage, raw_target_current)
    conduction_value = float(on_voltage["value"]) if family == "IGBT" else float(on_voltage["value"]) / target_total_current
    conduction_pass = conduction_value <= max_value

    raw_vth_criterion = float(targets["vth"]["criterion_current_a"]) / area_factor
    vth = crossing_voltage_log_current(rows["vth"], "Gate InnerVoltage", high_current, raw_vth_criterion)
    vth_pass = float(targets["vth"]["min_v"]) <= vth["voltage_v"] <= float(targets["vth"]["max_v"])

    leakage_raw = interpolate_y(
        rows["off_leakage"], high_voltage, high_current, float(targets["off_leakage"]["blocking_voltage_v"])
    )
    leakage_raw_a_um = abs(float(leakage_raw["value"]))
    leakage_total_a = leakage_raw_a_um * area_factor
    leakage_pass = leakage_total_a <= float(targets["off_leakage"]["max_current_a"])

    bv_criterion = 1.0e-6
    bv = first_raw_current_crossing(rows["bv"], high_voltage, high_current, bv_criterion)
    bv_pass = bv["bv_v"] >= float(spec["rated_voltage_v"])

    static_gate_passed = bool(conduction_pass and vth_pass and leakage_pass and bv_pass)
    return {
        "device_family": family,
        "structure_id": spec["structure_id"],
        "device_dsl": relative(spec_path),
        "device_dsl_sha256": sha256(spec_path),
        "mesh_variant": mesh_variant,
        "mesh_sha256": mesh_sha256,
        "area_factor": {
            "value": area_factor,
            "policy": "self_calibrated_baseline" if fixed_area_factor is None else "fixed_from_baseline_extraction",
            "unit": "um effective out-of-plane width",
            "definition": "datasheet conduction current divided by raw 2D current at the datasheet typical conduction point",
            "calibration_voltage_v": calibration_voltage,
            "raw_current_a_um": raw_on_current,
            "target_total_current_a": target_total_current,
            "diagnostic_self_calibrated_value": diagnostic_area_factor,
            "diagnostic_relative_delta_from_fixed": (
                0.0 if fixed_area_factor is None else diagnostic_area_factor / area_factor - 1.0
            ),
        },
        "conduction": {
            "quantity": conduction_quantity,
            "value": conduction_value,
            "baseline_calibrated_value": baseline_calibrated_value,
            "maximum_allowed_value": max_value,
            "status": "WITHIN_DATASHEET_MAX" if conduction_pass else "FAILED_DATASHEET_MAX",
            "passed": conduction_pass,
            "raw_target_current_a_um": raw_target_current,
            "selection": on_voltage,
            "diagnostic_current_at_baseline_typical_voltage": raw_on,
        },
        "vth": {
            **vth,
            "datasheet_total_current_criterion_a": float(targets["vth"]["criterion_current_a"]),
            "raw_2d_current_criterion_a_um": raw_vth_criterion,
            "minimum_v": float(targets["vth"]["min_v"]),
            "maximum_v": float(targets["vth"]["max_v"]),
            "bias_relation": targets["vth"]["bias_relation"],
            "passed": vth_pass,
        },
        "off_leakage": {
            "blocking_voltage_v": float(targets["off_leakage"]["blocking_voltage_v"]),
            "raw_current_a_um": leakage_raw_a_um,
            "total_current_a": leakage_total_a,
            "maximum_total_current_a": float(targets["off_leakage"]["max_current_a"]),
            "passed": leakage_pass,
            "selection": leakage_raw,
        },
        "bv": {
            **bv,
            "criterion_a_um": bv_criterion,
            "rated_voltage_v": float(spec["rated_voltage_v"]),
            "passed": bv_pass,
            "solver_failure_used_as_bv": False,
        },
        "static_gate_passed": static_gate_passed,
        "baseline_static_gate_passed": static_gate_passed if mesh_variant == "baseline" else None,
        "refined_static_gate_passed": static_gate_passed if mesh_variant.startswith("refined") else None,
        "mesh_consistency_status": (
            "PENDING_THREE_LEVEL_COMPARISON"
            if mesh_variant.startswith("refined_v2")
            else spec["static_gates"].get("mesh_consistency", "PENDING")
        ),
        "sources": sources,
    }


def write_summary_csv(path: Path, results: dict[str, dict[str, Any]]) -> None:
    rows = []
    for family, result in results.items():
        rows.append({
            "device_family": family,
            "mesh_variant": result["mesh_variant"],
            "area_factor_um": result["area_factor"]["value"],
            "bv_v": result["bv"]["bv_v"],
            "bv_passed": result["bv"]["passed"],
            "vth_v": result["vth"]["voltage_v"],
            "vth_passed": result["vth"]["passed"],
            "conduction_quantity": result["conduction"]["quantity"],
            "conduction_value": result["conduction"]["value"],
            "conduction_maximum_allowed_value": result["conduction"]["maximum_allowed_value"],
            "conduction_passed": result["conduction"]["passed"],
            "off_leakage_raw_a_um": result["off_leakage"]["raw_current_a_um"],
            "off_leakage_total_a": result["off_leakage"]["total_current_a"],
            "off_leakage_maximum_total_a": result["off_leakage"]["maximum_total_current_a"],
            "off_leakage_passed": result["off_leakage"]["passed"],
            "static_gate_passed": result["static_gate_passed"],
            "mesh_consistency_status": result["mesh_consistency_status"],
        })
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-set", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DATA)
    parser.add_argument("--output-stem", help="override static_<mesh_variant> output stem")
    parser.add_argument("--device-family", choices=("IGBT", "MOSFET"), help="extract only one device family")
    parser.add_argument("--baseline-extraction", type=Path, default=DEFAULT_REPORT_DATA / "static_baseline_extraction.json")
    args = parser.parse_args()

    run_set = read_json(args.run_set)
    if run_set.get("schema_version") != "650v_static_run_set/v1":
        raise ValueError("run set must be a 650v_static_run_set/v1 document")
    mesh_variant = run_set.get("mesh_variant")
    if not isinstance(mesh_variant, str) or (mesh_variant != "baseline" and not mesh_variant.startswith("refined")):
        raise ValueError("run set mesh_variant must be baseline or an explicit refined level")
    families = (args.device_family,) if args.device_family else ("IGBT", "MOSFET")
    if set(run_set.get("devices", {})) != set(families):
        raise ValueError(f"run set must contain exactly {','.join(families)}")
    required_runs = {"bv", "conduction", "vth", "off_leakage"}
    for family, run_ids in run_set["devices"].items():
        if set(run_ids) != required_runs:
            raise ValueError(f"{family} run set must contain {sorted(required_runs)}")

    fixed_area_factors: dict[str, float | None] = {family: None for family in families}
    expected_meshes: dict[str, str | None] = {family: None for family in families}
    baseline_binding: dict[str, Any] | None = None
    if mesh_variant.startswith("refined"):
        baseline = read_json(args.baseline_extraction)
        if baseline.get("mesh_variant") != "baseline" or not set(families).issubset(baseline.get("results", {})):
            raise ValueError("refined extraction requires baseline evidence for every requested family")
        mesh_bindings = run_set.get("mesh_sha256")
        if not isinstance(mesh_bindings, dict) or set(mesh_bindings) != set(families):
            raise ValueError("refined run set must bind every requested device mesh SHA-256")
        for family in families:
            fixed_area_factors[family] = float(baseline["results"][family]["area_factor"]["value"])
            expected_meshes[family] = str(mesh_bindings[family])
            if not re.fullmatch(r"[0-9a-f]{64}", expected_meshes[family] or ""):
                raise ValueError(f"invalid refined mesh hash for {family}")
        baseline_binding = {
            "path": relative(args.baseline_extraction),
            "sha256": sha256(args.baseline_extraction),
            "run_set": baseline["run_set"],
            "run_set_sha256": baseline["run_set_sha256"],
        }

    results = {
        family: device_result(
            args.runtime,
            family,
            run_set["devices"][family],
            mesh_variant,
            fixed_area_factor=fixed_area_factors[family],
            expected_mesh_sha256=expected_meshes[family],
        )
        for family in families
    }
    all_passed = all(result["static_gate_passed"] for result in results.values())
    output = {
        "schema_version": "650v_static_extraction/v2",
        "mesh_variant": mesh_variant,
        "run_set": relative(args.run_set),
        "run_set_sha256": sha256(args.run_set),
        "baseline_binding": baseline_binding,
        "area_factor_semantics": (
            "one device-specific effective out-of-plane width self-calibrated from the baseline typical conduction point, then reused for baseline Vth and leakage"
            if mesh_variant == "baseline"
            else "fixed baseline AreaFactor reused unchanged for refined conduction, Vth, and off-state leakage; refined self-calibrated factor is diagnostic only"
        ),
        "results": results,
        "all_static_gates_passed": all_passed,
        "all_baseline_static_gates_passed": all_passed if mesh_variant == "baseline" else None,
        "all_refined_static_gates_passed": all_passed if mesh_variant.startswith("refined") else None,
        "heavy_ion_authorized": False,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_stem = args.output_stem or f"static_{mesh_variant}"
    json_path = args.output_dir / f"{output_stem}_extraction.json"
    csv_path = args.output_dir / f"{output_stem}_gate_summary.csv"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_summary_csv(csv_path, results)
    print(f"extraction={json_path} summary={csv_path} all_passed={all_passed}")


if __name__ == "__main__":
    main()