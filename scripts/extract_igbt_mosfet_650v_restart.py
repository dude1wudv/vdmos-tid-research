#!/usr/bin/env python3
"""Extract and fail-close one authorized 650 V DC restart run."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / "docs" / "changes" / "2026-07-15-igbt-mosfet-650v-redesign" / "data" / "heavy_ion_authorization.json"
DEFAULT_RUN_ROOT = ROOT / "local_runtime" / "tcad_projects" / "igbt_mosfet_650v_seb_20260715" / "runs"
DEFAULT_BINDING_SET = AUTHORIZATION.parent / "restart_binding_set.json"
FLOAT = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?")
CONTACT_ROW = re.compile(
    r"^\s*(?P<name>Collector|Drain)\s+"
    r"(?P<voltage>[+-]?\d+(?:\.\d+)?E[+-]\d+)\s+"
    r"(?P<electron>[+-]?\d+(?:\.\d+)?E[+-]\d+)\s+"
    r"(?P<hole>[+-]?\d+(?:\.\d+)?E[+-]\d+)\s+"
    r"(?P<total>[+-]?\d+(?:\.\d+)?E[+-]\d+)\s*$",
    re.MULTILINE,
)
TEMPERATURE_ROW = re.compile(
    r"Tmin:\s+(?P<tmin>[+-]?\d+(?:\.\d+)?)\s+"
    r"Tave:\s+(?P<tavg>[+-]?\d+(?:\.\d+)?)\s+"
    r"Tmax:\s+(?P<tmax>[+-]?\d+(?:\.\d+)?)\s+K"
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def record(path: Path) -> dict[str, Any]:
    return {"path": relative(path), "sha256": sha256(path), "size_bytes": path.stat().st_size}


def last_match(pattern: re.Pattern[str], text: str, label: str) -> re.Match[str]:
    matches = list(pattern.finditer(text))
    if not matches:
        raise ValueError(f"missing {label}")
    return matches[-1]


def parse_final_plt_row(path: Path) -> dict[str, float]:
    text = path.read_text(encoding="utf-8-sig")
    dataset_match = re.search(r"datasets\s*=\s*\[(.*?)\]\s*functions\s*=", text, re.DOTALL)
    data_match = re.search(r"\bData\s*\{(.*)\}\s*$", text, re.DOTALL)
    if dataset_match is None or data_match is None:
        raise ValueError(f"unsupported DF-ISE PLT: {path}")
    datasets = re.findall(r'"([^"]+)"', dataset_match.group(1))
    values = [float(token) for token in FLOAT.findall(data_match.group(1))]
    if not datasets or len(values) % len(datasets):
        raise ValueError(f"PLT cardinality mismatch: {path}")
    return dict(zip(datasets, values[-len(datasets):]))


def parse_final_plt_bias(path: Path, high_terminal: str) -> float:
    row = parse_final_plt_row(path)
    field = f"{high_terminal} InnerVoltage"
    if field not in row:
        raise ValueError(f"missing {field}: {path}")
    return row[field]


def scheduler_closed(manifest: dict[str, Any]) -> bool:
    scheduling = manifest.get("scheduling_evidence", {})
    return bool(
        manifest.get("allocation_mode") == "AUTO_LEASE"
        and manifest.get("sdevice_threads") == 1
        and manifest.get("lease_acquired") is True
        and manifest.get("lease_released") is True
        and manifest.get("affinity_verification") == "VERIFIED"
        and scheduling.get("allocation_mode") == "AUTO_LEASE"
        and scheduling.get("sdevice_threads") == 1
        and scheduling.get("lease_acquired") is True
        and scheduling.get("lease_released") is True
        and scheduling.get("affinity_verification") == "VERIFIED"
        and str(scheduling.get("exit_code")) == "0"
    )


def bound_record_matches(item: dict[str, Any]) -> bool:
    try:
        path = ROOT / str(item["path"])
        return path.is_file() and sha256(path) == item["sha256"] and path.stat().st_size == int(item["size_bytes"])
    except (KeyError, TypeError, ValueError, OSError):
        return False


def build_binding_set(run_root: Path) -> dict[str, Any]:
    authorization_sha256 = sha256(AUTHORIZATION)
    expected = {(family, bias) for family in ("IGBT", "MOSFET") for bias in (325, 400, 500)}
    indexed: dict[tuple[str, int], dict[str, Any]] = {}
    for gate_path in sorted(run_root.glob("*/restart_gate.json")):
        gate = read_json(gate_path)
        if gate.get("schema_version") != "650v_dc_restart_gate/v1" or gate.get("status") != "PASS":
            continue
        key = (str(gate.get("device_family")), int(gate.get("bias_v")))
        if key not in expected:
            continue
        if key in indexed:
            raise ValueError(f"duplicate passing restart gate for {key[0]} {key[1]} V")
        required_records = ("run_manifest", "metadata", "restart_main", "restart_circuit", "prebias_tdr")
        if not all(bound_record_matches(gate.get(name, {})) for name in required_records):
            raise ValueError(f"{key[0]} {key[1]} V restart gate has a stale bound file")
        manifest = read_json(ROOT / gate["run_manifest"]["path"])
        metadata = read_json(ROOT / gate["metadata"]["path"])
        authorization_record = metadata.get("authorization_evidence", {})
        if not (
            manifest.get("run_id") == gate.get("run_id")
            and manifest.get("lifecycle") == "SUCCEEDED"
            and str(manifest.get("exit_code")) == "0"
            and scheduler_closed(manifest)
            and math.isclose(float(gate.get("actual_bias_v")), float(key[1]), rel_tol=0.0, abs_tol=1e-6)
            and authorization_record.get("sha256") == authorization_sha256
            and bound_record_matches(authorization_record)
        ):
            raise ValueError(f"{key[0]} {key[1]} V restart gate is not exactly authorized and closed")
        indexed[key] = gate
    missing = sorted(expected - set(indexed))
    if missing:
        text = ", ".join(f"{family} {bias} V" for family, bias in missing)
        raise ValueError(f"restart binding set is blocked; missing PASS gates: {text}")
    for family in ("IGBT", "MOSFET"):
        chain = [indexed[(family, bias)] for bias in (325, 400, 500)]
        if not (
            chain[0]["parent_run_id"] == f"AUTHORIZATION_{authorization_sha256[:16]}"
            and chain[1]["parent_run_id"] == chain[0]["run_id"]
            and chain[2]["parent_run_id"] == chain[1]["run_id"]
        ):
            raise ValueError(f"{family} restart parent chain is not strictly 325 to 400 to 500 V")
    records = []
    for family in ("IGBT", "MOSFET"):
        for bias in (325, 400, 500):
            gate = indexed[(family, bias)]
            records.append({
                "device_family": family,
                "bias_v": bias,
                "run_id": gate["run_id"],
                "parent_run_id": gate["parent_run_id"],
                "actual_bias_v": gate["actual_bias_v"],
                "mesh_sha256": gate["mesh_sha256"],
                "run_manifest": gate["run_manifest"],
                "restart_gate": record(run_root / Path(gate["run_manifest"]["path"]).parent.name / "restart_gate.json"),
                "restart_main": gate["restart_main"],
                "restart_circuit": gate["restart_circuit"],
                "prebias_tdr": gate["prebias_tdr"],
                "scheduling_evidence": gate["scheduling_evidence"],
            })
    return {
        "schema_version": "650v_restart_binding_set/v1",
        "authorization_sha256": authorization_sha256,
        "status": "PASS",
        "records": records,
    }


def extract(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "run_manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("lifecycle") != "SUCCEEDED" or str(manifest.get("exit_code")) != "0":
        raise ValueError("restart runner did not succeed")
    metadata_input = next(
        run_dir / item["relative_path"]
        for item in manifest["inputs"]
        if item["relative_path"].endswith(".json")
    )
    metadata = read_json(metadata_input)
    authorization_record = metadata.get("authorization_evidence", {})
    if not (
        metadata.get("phase") == "dc_restart"
        and metadata.get("heavy_ion_authorized") is True
        and authorization_record.get("path") == relative(AUTHORIZATION)
        and authorization_record.get("sha256") == sha256(AUTHORIZATION)
        and authorization_record.get("size_bytes") == AUTHORIZATION.stat().st_size
    ):
        raise ValueError("restart metadata is not bound to the current authorization")

    family = str(manifest["device_family"])
    high = "Collector" if family == "IGBT" else "Drain"
    target_bias = float(metadata["target_blocking_voltage_v"])
    prefix = str(metadata["restart_prefix"])
    artifact_dir = run_dir / "artifacts"
    stdout_path = artifact_dir / "stdout.log"
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
    contact = last_match(CONTACT_ROW, stdout, "final high-side contact row")
    temperature_matches = list(TEMPERATURE_ROW.finditer(stdout))
    temperature = temperature_matches[-1] if temperature_matches else None
    stdout_bias = float(contact.group("voltage"))
    current = float(contact.group("total"))

    plt_path = artifact_dir / f"{prefix.replace('_restart', '_dc_restart')}.plt"
    log_path = artifact_dir / f"{prefix.replace('_restart', '_dc_restart')}.log_des.log"
    restart_main = artifact_dir / f"{prefix}_des.sav"
    restart_circuit = artifact_dir / f"{prefix}_circuit_des.sav"
    pre_tdr = artifact_dir / f"{prefix.replace('_restart', '_dc_pre')}_des.tdr"
    required = [plt_path, log_path, restart_main, restart_circuit, pre_tdr]
    missing = [path.name for path in required if not path.is_file()]
    plt_row = parse_final_plt_row(plt_path) if plt_path.is_file() else {}
    bias_field = f"{high} InnerVoltage"
    if plt_path.is_file() and bias_field not in plt_row:
        raise ValueError(f"missing {bias_field}: {plt_path}")
    plt_bias = plt_row.get(bias_field, math.nan)
    if temperature is not None:
        tmin = float(temperature.group("tmin"))
        tavg = float(temperature.group("tavg"))
        tmax = float(temperature.group("tmax"))
        temperature_source = "stdout"
    else:
        missing_temperature_fields = [field for field in ("Tmin", "Tave", "Tmax") if field not in plt_row]
        if missing_temperature_fields:
            raise ValueError(f"missing final temperature summary: {', '.join(missing_temperature_fields)}")
        tmin, tavg, tmax = (plt_row["Tmin"], plt_row["Tave"], plt_row["Tmax"])
        temperature_source = "plt"
    mesh_input = next(item for item in manifest["inputs"] if item["relative_path"].endswith("_msh.tdr"))
    expected_mesh = metadata["verified_mesh"]["sha256"]

    checks = {
        "runner_succeeded": True,
        "scheduler_verified": scheduler_closed(manifest),
        "authorization_exact": True,
        "mesh_hash_exact": mesh_input["sha256"] == expected_mesh,
        "stdout_bias_exact": math.isclose(stdout_bias, target_bias, rel_tol=0.0, abs_tol=1e-6),
        "plt_bias_exact": math.isclose(plt_bias, target_bias, rel_tol=0.0, abs_tol=1e-6),
        "bias_channels_agree": math.isclose(stdout_bias, plt_bias, rel_tol=0.0, abs_tol=1e-6),
        "finite_operating_values": all(math.isfinite(value) for value in (stdout_bias, plt_bias, current, tmin, tavg, tmax)),
        "ordered_temperature_summary": tmin <= tavg <= tmax,
        "native_restart_pair_present": restart_main.is_file() and restart_circuit.is_file(),
        "prebias_tdr_present": pre_tdr.is_file(),
        "all_required_artifacts_present": not missing,
    }
    passed = all(checks.values())
    result = {
        "schema_version": "650v_dc_restart_gate/v1",
        "status": "PASS" if passed else "FAIL",
        "run_id": manifest["run_id"],
        "case_id": manifest["case_id"],
        "attempt_id": manifest["attempt_id"],
        "parent_run_id": manifest["parent_run_id"],
        "device_family": family,
        "bias_v": int(target_bias),
        "target_bias_v": target_bias,
        "actual_bias_v": plt_bias,
        "stdout_bias_v": stdout_bias,
        "high_side_current_a_per_um": current,
        "power_w_per_um": plt_bias * current,
        "tmin_k": tmin,
        "tavg_k": tavg,
        "tmax_k": tmax,
        "temperature_source": temperature_source,
        "lifecycle": manifest["lifecycle"],
        "termination_reason": "COMPLETED_TARGET_BIAS_AND_NATIVE_SAVE" if passed else "RESTART_GATE_FAILED",
        "wall_time_seconds": manifest["wall_time_seconds"],
        "scheduling_evidence": manifest["scheduling_evidence"],
        "mesh_sha256": mesh_input["sha256"],
        "checks": checks,
        "missing_required_artifacts": missing,
        "run_manifest": record(manifest_path),
        "metadata": record(metadata_input),
        "stdout": record(stdout_path),
        "source_plt": record(plt_path) if plt_path.is_file() else None,
        "source_log": record(log_path) if log_path.is_file() else None,
        "restart_main": record(restart_main) if restart_main.is_file() else None,
        "restart_circuit": record(restart_circuit) if restart_circuit.is_file() else None,
        "prebias_tdr": record(pre_tdr) if pre_tdr.is_file() else None,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--build-binding-set", action="store_true")
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.build_binding_set:
        if args.run_dir:
            parser.error("--run-dir cannot be combined with --build-binding-set")
        result = build_binding_set(args.run_root.resolve())
        output = args.output.resolve() if args.output else DEFAULT_BINDING_SET
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"restart_binding_set=PASS records={len(result['records'])} output={output}")
        return 0
    if args.run_dir is None:
        parser.error("--run-dir is required unless --build-binding-set is used")
    run_dir = args.run_dir.resolve()
    result = extract(run_dir)
    output = args.output.resolve() if args.output else run_dir / "restart_gate.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"restart_gate={result['status']} run_id={result['run_id']} actual_bias_v={result['actual_bias_v']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())