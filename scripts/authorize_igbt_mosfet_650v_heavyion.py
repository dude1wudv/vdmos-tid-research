#!/usr/bin/env python3
"""Issue fail-closed HeavyIon authorization after static, mesh, and track gates."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "changes" / "2026-07-15-igbt-mosfet-650v-redesign" / "data"
RUNTIME = ROOT / "local_runtime" / "tcad_projects" / "igbt_mosfet_650v_seb_20260715"
DSL_PATHS = {
    "IGBT": ROOT / "projects" / "igbt_mosfet_650v_seb_20260715" / "devices" / "igbt_650v.json",
    "MOSFET": ROOT / "projects" / "igbt_mosfet_650v_seb_20260715" / "devices" / "mosfet_650v_sj.json",
}
AUTHORIZATION = DATA / "heavy_ion_authorization.json"
EVIDENCE_PATHS = {
    "baseline_extraction": DATA / "static_baseline_extraction.json",
    "refined_v1_extraction": DATA / "static_refined_extraction.json",
    "refined_v1_mesh_gate": DATA / "static_mesh_consistency.json",
    "refined_v2_extraction": DATA / "static_refined_v2_local_extraction.json",
    "refined_v2_mesh_gate": DATA / "static_mesh_consistency_v2.json",
    "field_track_localization": DATA / "field_track_localization_v2.json",
}
REQUIRED_GATES = ("bv", "vth", "conduction", "off_leakage", "mesh_consistency")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def resolved_value(spec: dict[str, Any], name: str) -> Any:
    item = spec["parameters"][name]
    if item["final_value"] is not None:
        return item["final_value"]
    if item.get("candidate_value") is not None:
        return item["candidate_value"]
    return item["seed_value"]


def file_record(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": relative(path), "sha256": sha256(path), "size_bytes": path.stat().st_size}


def verify_bound_record(record: dict[str, Any]) -> None:
    path = ROOT / record["path"]
    if not path.is_file() or sha256(path) != record["sha256"]:
        raise ValueError(f"bound-file mismatch: {record['path']}")


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


def source_run_record(source: dict[str, Any], stage: str, metric: str) -> dict[str, Any]:
    manifest_path = ROOT / source["run_manifest"]
    plt_path = ROOT / source["source_plt"]
    if sha256(manifest_path) != source["run_manifest_sha256"]:
        raise ValueError(f"{source['run_id']}: manifest hash mismatch")
    if sha256(plt_path) != source["source_plt_sha256"]:
        raise ValueError(f"{source['run_id']}: PLT hash mismatch")
    manifest = read_json(manifest_path)
    if (
        manifest.get("run_id") != source["run_id"]
        or manifest.get("lifecycle") != "SUCCEEDED"
        or str(manifest.get("exit_code")) != "0"
        or not scheduler_closed(source)
    ):
        raise ValueError(f"{source['run_id']}: static run is not scheduler-closed")
    return {
        "stage": stage,
        "metric": metric,
        "run_id": source["run_id"],
        "run_manifest": file_record(manifest_path),
        "source_plt": file_record(plt_path),
        "mesh_sha256": source["mesh_sha256"],
        "scheduling_evidence": source["scheduling_evidence"],
    }


def mesh_record(extraction_result: dict[str, Any], preferred_metric: str = "bv") -> dict[str, Any]:
    source = extraction_result["sources"][preferred_metric]
    manifest_path = ROOT / source["run_manifest"]
    manifest = read_json(manifest_path)
    mesh_input = next(item for item in manifest["inputs"] if item["relative_path"].endswith("_msh.tdr"))
    mesh_path = manifest_path.parent / mesh_input["relative_path"]
    if sha256(mesh_path) != mesh_input["sha256"] or mesh_input["sha256"] != extraction_result["mesh_sha256"]:
        raise ValueError(f"{extraction_result['device_family']}: mesh binding mismatch")
    return {
        "variant": extraction_result["mesh_variant"],
        "path": relative(mesh_path),
        "sha256": mesh_input["sha256"],
        "size_bytes": mesh_path.stat().st_size,
    }


def current_track(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "track_x_um": float(resolved_value(spec, "track_x")),
        "track_y_um": float(resolved_value(spec, "track_y")),
        "direction": [float(item) for item in resolved_value(spec, "track_direction")],
        "length_um": float(resolved_value(spec, "track_length")),
    }


def expected_track(field: dict[str, Any], family: str) -> dict[str, Any]:
    track = field["tracks"][family]
    return {
        "track_x_um": float(track["start_um"][0]),
        "track_y_um": float(track["start_um"][1]),
        "direction": [float(item) for item in track["direction"]],
        "length_um": float(track["length_um"]),
    }


def main() -> None:
    if AUTHORIZATION.exists():
        raise FileExistsError(f"refusing to overwrite authorization evidence: {AUTHORIZATION}")

    evidence = {name: read_json(path) for name, path in EVIDENCE_PATHS.items()}
    baseline = evidence["baseline_extraction"]
    refined_v1 = evidence["refined_v1_extraction"]
    mesh_v1 = evidence["refined_v1_mesh_gate"]
    refined_v2 = evidence["refined_v2_extraction"]
    mesh_v2 = evidence["refined_v2_mesh_gate"]
    field = evidence["field_track_localization"]

    if not (
        baseline.get("all_static_gates_passed") is True
        and refined_v1.get("all_refined_static_gates_passed") is True
        and mesh_v1.get("status") == "FAILED"
        and mesh_v1.get("devices", {}).get("IGBT", {}).get("status") == "PASSED"
        and mesh_v1.get("devices", {}).get("MOSFET", {}).get("status") == "FAILED"
        and math.isclose(
            float(mesh_v1["devices"]["MOSFET"]["comparisons"]["vth"]["delta"]),
            0.11826345087832646,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        and mesh_v2.get("status") == "PASSED"
        and mesh_v2.get("static_mesh_gate_closed") is True
        and refined_v2.get("all_refined_static_gates_passed") is True
        and field.get("status") == "VERIFIED_TRACKS_FROZEN_HEAVYION_NOT_AUTHORIZED"
        and field.get("all_tracks_frozen") is True
        and field.get("heavy_ion_authorized") is False
    ):
        raise ValueError("five-gate or track-freeze evidence is incomplete")
    if any(document.get("heavy_ion_authorized") is not False for document in (baseline, refined_v1, mesh_v1, refined_v2, mesh_v2)):
        raise ValueError("pre-authorization evidence must remain HeavyIon-unauthorized")

    specs = {family: read_json(path) for family, path in DSL_PATHS.items()}
    expected_candidates = {
        "IGBT": ("igbt_lifetime_300us", {"minority_carrier_lifetime_s": 0.0003}),
        "MOSFET": ("mosfet_attempt24_sj_scale_0p8", {"sj_pillar_doping_scale": 0.8}),
    }
    for family, spec in specs.items():
        gates = spec["static_gates"]
        if not all(gates.get(gate) == "PASSED" for gate in REQUIRED_GATES):
            raise ValueError(f"{family}: five gates are not PASSED")
        if gates.get("heavy_ion_authorized") is not False:
            raise ValueError(f"{family}: expected a not-yet-authorized DSL")
        candidate_id, candidate_values = expected_candidates[family]
        if spec["candidate_freeze"]["candidate_id"] != candidate_id or spec["candidate_freeze"]["candidate_values"] != candidate_values:
            raise ValueError(f"{family}: frozen reference candidate mismatch")
        if current_track(spec) != expected_track(field, family):
            raise ValueError(f"{family}: DSL track does not exactly match field evidence")

    static_runs: dict[str, list[dict[str, Any]]] = {"IGBT": [], "MOSFET": []}
    stage_documents = {
        "baseline": baseline,
        "refined_v1": refined_v1,
        "refined_v2_local": refined_v2,
    }
    for stage, document in stage_documents.items():
        for family, result in document.get("results", {}).items():
            for metric, source in result["sources"].items():
                static_runs[family].append(source_run_record(source, stage, metric))

    meshes = {
        "IGBT": [
            mesh_record(baseline["results"]["IGBT"]),
            mesh_record(refined_v1["results"]["IGBT"]),
        ],
        "MOSFET": [
            mesh_record(baseline["results"]["MOSFET"]),
            mesh_record(refined_v1["results"]["MOSFET"]),
            mesh_record(refined_v2["results"]["MOSFET"]),
        ],
    }
    expected_meshes = {
        "IGBT": [
            "535bef9cfb4537174f746545cb3b7b3b95ed8ea536e6fea4e6a5408a408e1664",
            "84d24e1dc14052ee3ef3525ced567ee9337c97ba0e5e55eefc1d0ddde09fd755",
        ],
        "MOSFET": [
            "fa8279e907be5bf545b938e0cb24fffd69e544225bd4366ad5285589f848e569",
            "949901b1790b164c47e6b2dce92e522bda0ecdb5dc71f8724d9fdc301b39b4ad",
            "1b900c26df4e367aa7a5621e21a24479f07b3ad0fbe3c7294d19398f6bdb0727",
        ],
    }
    for family, records in meshes.items():
        if [record["sha256"] for record in records] != expected_meshes[family]:
            raise ValueError(f"{family}: baseline/refined mesh chain mismatch")

    field_runs = []
    for record in field["runs"]:
        for name in ("run_manifest", "source_plt", "field_tdr", "field_extraction"):
            verify_bound_record(record[name] if isinstance(record[name], dict) else {
                "path": record[name],
                "sha256": record[name + "_sha256"],
            })
        if not scheduler_closed({"scheduling_evidence": record["scheduling_evidence"]}):
            raise ValueError(f"{record['run_id']}: field run is not scheduler-closed")
        field_runs.append(record)

    evidence_files = {name: file_record(path) for name, path in EVIDENCE_PATHS.items()}

    for family, spec in specs.items():
        spec["static_gates"]["heavy_ion_authorized"] = True
        spec["static_gates"]["authorization_evidence"] = relative(AUTHORIZATION)
        spec["static_gates"]["combined_campaign_gate"] = "AUTHORIZED_EXACT_BOUND_EVIDENCE"
        spec["candidate_freeze"]["status"] = "FROZEN_REFERENCE_MODEL_STATIC_MESH_TRACK_PASSED_HEAVYION_AUTHORIZED"
        write_json_atomic(DSL_PATHS[family], spec)

    devices: dict[str, Any] = {}
    for family in ("IGBT", "MOSFET"):
        spec = read_json(DSL_PATHS[family])
        devices[family] = {
            "dsl": file_record(DSL_PATHS[family]),
            "candidate_id": spec["candidate_freeze"]["candidate_id"],
            "candidate_values": spec["candidate_freeze"]["candidate_values"],
            "five_gates": {gate: spec["static_gates"][gate] for gate in REQUIRED_GATES},
            "meshes": meshes[family],
            "static_runs": static_runs[family],
            "track": current_track(spec),
            "field_track": field["tracks"][family],
        }

    bound_files: dict[str, dict[str, Any]] = {}
    for record in evidence_files.values():
        bound_files[record["path"]] = record
    for family in devices.values():
        bound_files[family["dsl"]["path"]] = family["dsl"]
        for mesh in family["meshes"]:
            bound_files[mesh["path"]] = mesh
        for run in family["static_runs"]:
            bound_files[run["run_manifest"]["path"]] = run["run_manifest"]
            bound_files[run["source_plt"]["path"]] = run["source_plt"]
    for run in field_runs:
        for name in ("run_manifest", "source_plt", "field_tdr", "field_extraction"):
            path_key = run[name] if isinstance(run[name], str) else run[name]["path"]
            hash_key = run[name + "_sha256"] if isinstance(run[name], str) else run[name]["sha256"]
            path = ROOT / path_key
            bound_files[path_key] = {"path": path_key, "sha256": hash_key, "size_bytes": path.stat().st_size}
    for record in bound_files.values():
        verify_bound_record(record)

    authorization = {
        "schema_version": "650v_heavy_ion_authorization/v1",
        "campaign_id": "igbt_mosfet_650v_seb_20260715",
        "status": "AUTHORIZED",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "scope": "LET15 2.1 ns reference transients at 325/400/500 V only after matching DC restart evidence exists",
        "reference_model_only": True,
        "five_gate_policy": list(REQUIRED_GATES),
        "historical_refined_v1_mosfet_failure_retained": {
            "status": "FAILED_GATE_RETAINED",
            "vth_delta_v": 0.11826345087832646,
            "threshold_v": 0.1,
            "evidence": evidence_files["refined_v1_mesh_gate"],
        },
        "evidence_files": evidence_files,
        "devices": devices,
        "field_runs": field_runs,
        "bound_files": list(bound_files.values()),
        "post_static_render_policy": "DC restart may render now; transient rendering remains blocked until exact parent restart IDs and hashes are supplied",
        "heavy_ion_authorized": True,
    }
    write_json_atomic(AUTHORIZATION, authorization)
    print(f"authorization=AUTHORIZED evidence={AUTHORIZATION} bound_files={len(bound_files)}")


if __name__ == "__main__":
    main()