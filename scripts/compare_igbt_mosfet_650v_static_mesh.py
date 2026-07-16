#!/usr/bin/env python3
"""Fail-closed baseline/refined static mesh consistency comparison."""
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
DEVICE_DSL = {
    "IGBT": ROOT / "projects" / "igbt_mosfet_650v_seb_20260715" / "devices" / "igbt_650v.json",
    "MOSFET": ROOT / "projects" / "igbt_mosfet_650v_seb_20260715" / "devices" / "mosfet_650v_sj.json",
}
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


def finite_number(value: Any, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite mesh comparison value: {label}")
    return number


def relative_delta(baseline: float, refined: float) -> float:
    if baseline == 0:
        raise ValueError("relative mesh comparison baseline cannot be zero")
    return abs(refined - baseline) / abs(baseline)


def validate_extraction(document: dict[str, Any], variant: str) -> None:
    if document.get("schema_version") != "650v_static_extraction/v2" or document.get("mesh_variant") != variant:
        raise ValueError(f"expected {variant} 650v_static_extraction/v2 evidence")
    if set(document.get("results", {})) != {"IGBT", "MOSFET"}:
        raise ValueError(f"{variant} extraction is incomplete")
    if document.get("heavy_ion_authorized") is not False:
        raise ValueError(f"{variant} extraction must not authorize HeavyIon")


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=REPORT_DATA / "static_baseline_extraction.json")
    parser.add_argument("--refined", type=Path, default=REPORT_DATA / "static_refined_extraction.json")
    parser.add_argument("--output-dir", type=Path, default=REPORT_DATA)
    args = parser.parse_args()

    baseline = read_json(args.baseline)
    refined = read_json(args.refined)
    validate_extraction(baseline, "baseline")
    validate_extraction(refined, "refined")

    refined_run_set_path = ROOT / refined["run_set"]
    if sha256(refined_run_set_path) != refined["run_set_sha256"]:
        raise ValueError("refined run-set hash binding is invalid")
    refined_run_set = read_json(refined_run_set_path)
    mesh_manifest_binding = refined_run_set.get("mesh_generation_manifest", {})
    if set(mesh_manifest_binding) != {"path", "sha256"}:
        raise ValueError("refined run set must bind one mesh-generation manifest")
    mesh_manifest_path = ROOT / mesh_manifest_binding["path"]
    if sha256(mesh_manifest_path) != mesh_manifest_binding["sha256"]:
        raise ValueError("mesh-generation manifest hash binding is invalid")
    mesh_manifest = read_json(mesh_manifest_path)
    if mesh_manifest.get("status") != "SUCCEEDED" or set(mesh_manifest.get("meshes", {})) != {"IGBT", "MOSFET"}:
        raise ValueError("refined mesh generation evidence is incomplete")

    dsl_documents = {family: read_json(path) for family, path in DEVICE_DSL.items()}
    threshold_sets = [document["mesh_consistency_contract"]["thresholds"] for document in dsl_documents.values()]
    if threshold_sets[0] != threshold_sets[1]:
        raise ValueError("IGBT and MOSFET mesh thresholds must match")
    thresholds = {name: finite_number(value, name) for name, value in threshold_sets[0].items()}

    device_results: dict[str, Any] = {}
    csv_rows: list[dict[str, Any]] = []
    all_passed = True
    for family in ("IGBT", "MOSFET"):
        baseline_result = baseline["results"][family]
        refined_result = refined["results"][family]
        dsl = dsl_documents[family]
        baseline_mesh = baseline_result["mesh_sha256"]
        refined_mesh = refined_result["mesh_sha256"]
        if baseline_mesh != dsl["candidate_freeze"]["baseline_mesh_sha256"]:
            raise ValueError(f"{family} baseline mesh does not match candidate freeze")
        if refined_mesh == baseline_mesh:
            raise ValueError(f"{family} refined mesh is not a new mesh")
        if refined_mesh != refined_run_set["mesh_sha256"][family]:
            raise ValueError(f"{family} refined extraction/run-set mesh mismatch")
        if refined_mesh != mesh_manifest["meshes"][family]["sha256"]:
            raise ValueError(f"{family} refined mesh-generation hash mismatch")

        baseline_factor = finite_number(baseline_result["area_factor"]["value"], f"{family}.baseline.AreaFactor")
        refined_factor = finite_number(refined_result["area_factor"]["value"], f"{family}.refined.AreaFactor")
        fixed_area_factor_passed = baseline_factor == refined_factor and refined_result["area_factor"].get("policy") == "fixed_from_baseline_extraction"

        comparisons: dict[str, Any] = {}
        metric_passes: list[bool] = []
        for metric, (section, field, mode, threshold_name) in METRICS.items():
            baseline_value = finite_number(baseline_result[section][field], f"{family}.{metric}.baseline")
            refined_value = finite_number(refined_result[section][field], f"{family}.{metric}.refined")
            delta = abs(refined_value - baseline_value) if mode == "absolute" else relative_delta(baseline_value, refined_value)
            threshold = thresholds[threshold_name]
            passed = delta <= threshold
            metric_passes.append(passed)
            comparisons[metric] = {
                "baseline": baseline_value,
                "refined": refined_value,
                "delta": delta,
                "delta_mode": mode,
                "threshold": threshold,
                "threshold_name": threshold_name,
                "passed": passed,
            }
            csv_rows.append({
                "device_family": family,
                "metric": metric,
                "baseline": baseline_value,
                "refined": refined_value,
                "delta": delta,
                "delta_mode": mode,
                "threshold": threshold,
                "passed": passed,
            })

        refined_sources = refined_result["sources"]
        scheduler_passed = set(refined_sources) == {"bv", "conduction", "vth", "off_leakage"} and all(
            scheduler_closed(source) for source in refined_sources.values()
        )
        refined_static_passed = refined_result.get("static_gate_passed") is True
        device_passed = bool(fixed_area_factor_passed and scheduler_passed and refined_static_passed and all(metric_passes))
        all_passed = all_passed and device_passed
        device_results[family] = {
            "status": "PASSED" if device_passed else "FAILED",
            "device_dsl": relative(DEVICE_DSL[family]),
            "device_dsl_sha256": sha256(DEVICE_DSL[family]),
            "baseline_mesh_sha256": baseline_mesh,
            "refined_mesh_sha256": refined_mesh,
            "baseline_area_factor": baseline_factor,
            "refined_fixed_area_factor": refined_factor,
            "refined_diagnostic_self_calibrated_area_factor": refined_result["area_factor"]["diagnostic_self_calibrated_value"],
            "fixed_area_factor_passed": fixed_area_factor_passed,
            "refined_static_gates_passed": refined_static_passed,
            "scheduler_evidence_passed": scheduler_passed,
            "comparisons": comparisons,
            "baseline_runs": {
                kind: {
                    "run_id": source["run_id"],
                    "run_manifest_sha256": source["run_manifest_sha256"],
                    "source_plt_sha256": source["source_plt_sha256"],
                }
                for kind, source in baseline_result["sources"].items()
            },
            "refined_runs": {
                kind: {
                    "run_id": source["run_id"],
                    "run_manifest_sha256": source["run_manifest_sha256"],
                    "source_plt_sha256": source["source_plt_sha256"],
                    "scheduling_evidence": source["scheduling_evidence"],
                }
                for kind, source in refined_sources.items()
            },
        }

    status = "PASSED" if all_passed else "FAILED"
    output = {
        "schema_version": "650v_static_mesh_consistency/v1",
        "status": status,
        "thresholds": thresholds,
        "threshold_rationale": dsl_documents["IGBT"]["mesh_consistency_contract"]["rationale"],
        "baseline_extraction": {"path": relative(args.baseline), "sha256": sha256(args.baseline)},
        "refined_extraction": {"path": relative(args.refined), "sha256": sha256(args.refined)},
        "refined_run_set": {"path": relative(refined_run_set_path), "sha256": sha256(refined_run_set_path)},
        "mesh_generation_manifest": {"path": relative(mesh_manifest_path), "sha256": sha256(mesh_manifest_path)},
        "devices": device_results,
        "static_mesh_gate_closed": all_passed,
        "post_static_authorization_ready": all_passed,
        "heavy_ion_authorized": False,
        "authorization_state": (
            "STATIC_MESH_GATE_CLOSED_AUDIT_BINDING_READY_HEAVYION_NOT_AUTHORIZED"
            if all_passed
            else "STATIC_MESH_GATE_FAILED_POST_STATIC_CAMPAIGN_BLOCKED"
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "static_mesh_consistency.json"
    csv_path = args.output_dir / "static_mesh_consistency.csv"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"mesh_consistency={status} evidence={json_path}")


if __name__ == "__main__":
    main()