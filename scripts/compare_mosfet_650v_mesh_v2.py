#!/usr/bin/env python3
"""Audit the MOSFET baseline -> refined-v1 -> refined-v2 mesh trend."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_DATA = ROOT / "docs" / "changes" / "2026-07-15-igbt-mosfet-650v-redesign" / "data"
DEVICE_DSL = ROOT / "projects" / "igbt_mosfet_650v_seb_20260715" / "devices" / "mosfet_650v_sj.json"
METRICS = {
    "bv": ("bv", "bv_v", "relative", "bv_relative_max"),
    "vth": ("vth", "voltage_v", "absolute", "vth_absolute_v_max"),
    "conduction": ("conduction", "value", "relative", "conduction_relative_max"),
    "off_leakage": ("off_leakage", "total_current_a", "relative", "off_leakage_relative_max"),
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def finite(value: Any, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite value: {label}")
    return number


def metric_delta(left: float, right: float, mode: str) -> float:
    if mode == "absolute":
        return abs(right - left)
    if left == 0:
        raise ValueError("relative comparison baseline cannot be zero")
    return abs(right - left) / abs(left)


def scheduler_closed(source: dict[str, Any]) -> bool:
    scheduling = source.get("scheduling_evidence", {})
    return bool(
        scheduling.get("allocation_mode") == "AUTO_LEASE"
        and scheduling.get("sdevice_threads") == 1
        and scheduling.get("lease_acquired") is True
        and scheduling.get("lease_released") is True
        and scheduling.get("affinity_verification") == "VERIFIED"
        and str(scheduling.get("exit_code")) == "0"
    )


def validate_extraction(document: dict[str, Any], variant: str) -> dict[str, Any]:
    if document.get("schema_version") != "650v_static_extraction/v2":
        raise ValueError(f"{variant}: unsupported extraction schema")
    if document.get("mesh_variant") != variant:
        raise ValueError(f"{variant}: mesh variant mismatch")
    if document.get("heavy_ion_authorized") is not False:
        raise ValueError(f"{variant}: HeavyIon must remain unauthorized")
    result = document.get("results", {}).get("MOSFET")
    if not isinstance(result, dict):
        raise ValueError(f"{variant}: MOSFET result is missing")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=REPORT_DATA / "static_baseline_extraction.json")
    parser.add_argument("--refined-v1", type=Path, default=REPORT_DATA / "static_refined_extraction.json")
    parser.add_argument("--refined-v2", type=Path, default=REPORT_DATA / "static_refined_v2_local_extraction.json")
    parser.add_argument("--v1-gate", type=Path, default=REPORT_DATA / "static_mesh_consistency.json")
    parser.add_argument("--output-dir", type=Path, default=REPORT_DATA)
    args = parser.parse_args()

    baseline_document = read_json(args.baseline)
    v1_document = read_json(args.refined_v1)
    v2_document = read_json(args.refined_v2)
    baseline = validate_extraction(baseline_document, "baseline")
    v1 = validate_extraction(v1_document, "refined")
    v2_variant = str(v2_document.get("mesh_variant", ""))
    if not v2_variant.startswith("refined_v2"):
        raise ValueError("refined-v2 extraction must use an explicit v2 mesh variant")
    v2 = validate_extraction(v2_document, v2_variant)

    v1_gate = read_json(args.v1_gate)
    v1_vth_gate = v1_gate.get("devices", {}).get("MOSFET", {}).get("comparisons", {}).get("vth", {})
    if not (
        v1_gate.get("status") == "FAILED"
        and v1_gate.get("heavy_ion_authorized") is False
        and v1_vth_gate.get("passed") is False
        and math.isclose(finite(v1_vth_gate.get("delta"), "v1 Vth delta"), 0.11826345087832646, rel_tol=0, abs_tol=1e-12)
    ):
        raise ValueError("historical refined-v1 FAILED evidence is missing or was rewritten")

    run_set_path = ROOT / v2_document["run_set"]
    if sha256(run_set_path) != v2_document["run_set_sha256"]:
        raise ValueError("refined-v2 run-set hash binding is invalid")
    run_set = read_json(run_set_path)
    if run_set.get("mesh_variant") != v2_variant or set(run_set.get("devices", {})) != {"MOSFET"}:
        raise ValueError("refined-v2 run set must contain only MOSFET")
    mesh_binding = run_set.get("mesh_generation_manifest", {})
    if set(mesh_binding) != {"path", "sha256"}:
        raise ValueError("refined-v2 run set must bind its mesh-generation manifest")
    mesh_manifest_path = ROOT / mesh_binding["path"]
    if sha256(mesh_manifest_path) != mesh_binding["sha256"]:
        raise ValueError("refined-v2 mesh-generation manifest hash binding is invalid")
    mesh_manifest = read_json(mesh_manifest_path)
    if mesh_manifest.get("status") != "SUCCEEDED" or mesh_manifest.get("heavy_ion_authorized") is not False:
        raise ValueError("refined-v2 mesh-generation evidence is incomplete")

    mesh_hashes = [baseline["mesh_sha256"], v1["mesh_sha256"], v2["mesh_sha256"]]
    expected_hashes = [
        mesh_manifest["convergence_chain"]["baseline_mesh_sha256"],
        mesh_manifest["convergence_chain"]["refined_v1_mesh_sha256"],
        mesh_manifest["mesh"]["sha256"],
    ]
    if mesh_hashes != expected_hashes or len(set(mesh_hashes)) != 3:
        raise ValueError("three-level mesh hash chain is invalid")
    points = [
        int(mesh_manifest["convergence_chain"]["baseline_points"]),
        int(mesh_manifest["convergence_chain"]["refined_v1_points"]),
        int(mesh_manifest["mesh"]["points"]),
    ]
    elements = [
        int(mesh_manifest["convergence_chain"]["baseline_elements"]),
        int(mesh_manifest["convergence_chain"]["refined_v1_elements"]),
        int(mesh_manifest["mesh"]["elements"]),
    ]
    mesh_progression_passed = points[0] < points[1] < points[2] and elements[0] < elements[1] < elements[2]

    baseline_factor = finite(baseline["area_factor"]["value"], "baseline AreaFactor")
    v1_factor = finite(v1["area_factor"]["value"], "v1 AreaFactor")
    v2_factor = finite(v2["area_factor"]["value"], "v2 AreaFactor")
    fixed_area_factor_passed = bool(
        baseline_factor == v1_factor == v2_factor
        and v1["area_factor"].get("policy") == "fixed_from_baseline_extraction"
        and v2["area_factor"].get("policy") == "fixed_from_baseline_extraction"
    )

    spec = read_json(DEVICE_DSL)
    thresholds = {
        name: finite(value, name)
        for name, value in spec["mesh_consistency_contract"]["thresholds"].items()
    }
    comparisons: dict[str, Any] = {}
    csv_rows: list[dict[str, Any]] = []
    metric_passes: list[bool] = []
    for metric, (section, field, mode, threshold_name) in METRICS.items():
        values = [
            finite(baseline[section][field], f"{metric}.baseline"),
            finite(v1[section][field], f"{metric}.refined_v1"),
            finite(v2[section][field], f"{metric}.refined_v2"),
        ]
        delta_01 = metric_delta(values[0], values[1], mode)
        delta_12 = metric_delta(values[1], values[2], mode)
        delta_02 = metric_delta(values[0], values[2], mode)
        step_01 = abs(values[1] - values[0])
        step_12 = abs(values[2] - values[1])
        contraction_ratio = step_12 / step_01 if step_01 > 0 else math.inf
        contracting = bool(0 < contraction_ratio < 1)
        observed_order = -math.log(contraction_ratio, 2) if contracting else None
        same_direction = (values[1] - values[0]) * (values[2] - values[1]) > 0
        extrapolated_limit = None
        estimated_remaining_error = None
        if contracting and same_direction:
            extrapolated_limit = values[2] + (values[2] - values[1]) * contraction_ratio / (1 - contraction_ratio)
            remaining_absolute = abs(extrapolated_limit - values[2])
            estimated_remaining_error = (
                remaining_absolute
                if mode == "absolute"
                else remaining_absolute / abs(extrapolated_limit)
            )
        threshold = thresholds[threshold_name]
        successive_delta_passed = delta_12 <= threshold
        if metric == "vth":
            passed = bool(
                successive_delta_passed
                and contracting
                and same_direction
                and estimated_remaining_error is not None
                and estimated_remaining_error <= threshold
            )
            acceptance_rule = "unchanged successive Vth threshold plus contracting three-level active-mesh estimate"
        else:
            passed = bool(successive_delta_passed)
            acceptance_rule = "unchanged refined-v1 to refined-v2 threshold"
        metric_passes.append(passed)
        record = {
            "baseline": values[0],
            "refined_v1": values[1],
            "refined_v2": values[2],
            "baseline_to_v1_delta": delta_01,
            "v1_to_v2_delta": delta_12,
            "baseline_to_v2_delta_context_only": delta_02,
            "delta_mode": mode,
            "step_contraction_ratio": contraction_ratio,
            "observed_order_for_halved_contract": observed_order,
            "same_direction_monotonic": same_direction,
            "extrapolated_limit": extrapolated_limit,
            "estimated_v2_remaining_error": estimated_remaining_error,
            "threshold": threshold,
            "threshold_name": threshold_name,
            "successive_delta_passed": successive_delta_passed,
            "acceptance_rule": acceptance_rule,
            "passed": passed,
        }
        comparisons[metric] = record
        csv_rows.append({"metric": metric, **record})

    v2_sources = v2.get("sources", {})
    scheduler_passed = set(v2_sources) == set(METRICS) and all(scheduler_closed(source) for source in v2_sources.values())
    v2_static_passed = v2.get("static_gate_passed") is True
    all_passed = bool(
        mesh_progression_passed
        and fixed_area_factor_passed
        and scheduler_passed
        and v2_static_passed
        and all(metric_passes)
    )
    output = {
        "schema_version": "650v_mosfet_three_level_mesh_consistency/v1",
        "status": "PASSED" if all_passed else "FAILED",
        "decision_basis": "refined-v2 keeps refined-v1 global/off-state controls and halves only the active-region spacings; Vth must satisfy the unchanged 0.1 V successive threshold plus a contracting three-level remaining-error estimate, while the other three gates must satisfy their unchanged refined-v1-to-v2 thresholds",
        "thresholds_unchanged": thresholds,
        "historical_refined_v1_gate": {
            "status": "FAILED",
            "path": relative(args.v1_gate),
            "sha256": sha256(args.v1_gate),
            "vth_absolute_delta_v": finite(v1_vth_gate["delta"], "v1 Vth delta"),
            "threshold_v": finite(v1_vth_gate["threshold"], "v1 Vth threshold"),
        },
        "evidence": {
            "baseline_extraction": {"path": relative(args.baseline), "sha256": sha256(args.baseline)},
            "refined_v1_extraction": {"path": relative(args.refined_v1), "sha256": sha256(args.refined_v1)},
            "refined_v2_extraction": {"path": relative(args.refined_v2), "sha256": sha256(args.refined_v2)},
            "refined_v2_run_set": {"path": relative(run_set_path), "sha256": sha256(run_set_path)},
            "refined_v2_mesh_generation": {"path": relative(mesh_manifest_path), "sha256": sha256(mesh_manifest_path)},
        },
        "mesh_progression": {
            "variants": ["baseline", "refined_v1", v2_variant],
            "sha256": mesh_hashes,
            "points": points,
            "elements": elements,
            "passed": mesh_progression_passed,
        },
        "area_factor": {
            "baseline_fixed_value": baseline_factor,
            "refined_v1_fixed_value": v1_factor,
            "refined_v2_fixed_value": v2_factor,
            "refined_v1_diagnostic_self_calibrated": v1["area_factor"]["diagnostic_self_calibrated_value"],
            "refined_v2_diagnostic_self_calibrated": v2["area_factor"]["diagnostic_self_calibrated_value"],
            "passed": fixed_area_factor_passed,
        },
        "comparisons": comparisons,
        "v2_static_gates_passed": v2_static_passed,
        "v2_scheduler_evidence_passed": scheduler_passed,
        "v2_runs": {
            kind: {
                "run_id": source["run_id"],
                "run_manifest_sha256": source["run_manifest_sha256"],
                "source_plt_sha256": source["source_plt_sha256"],
                "scheduling_evidence": source["scheduling_evidence"],
            }
            for kind, source in v2_sources.items()
        },
        "static_mesh_gate_closed": all_passed,
        "heavy_ion_prerequisite_mesh_ready": all_passed,
        "post_static_authorization_ready": False,
        "heavy_ion_authorized": False,
        "authorization_state": (
            "MESH_V2_CONVERGENCE_PASSED_EXPLICIT_HEAVYION_AUTHORIZATION_NOT_ISSUED"
            if all_passed
            else "MESH_V2_CONVERGENCE_FAILED_POST_STATIC_CAMPAIGN_BLOCKED"
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "static_mesh_consistency_v2.json"
    csv_path = args.output_dir / "static_mesh_consistency_v2.csv"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"mosfet_mesh_v2={'PASSED' if all_passed else 'FAILED'} evidence={json_path}")


if __name__ == "__main__":
    main()