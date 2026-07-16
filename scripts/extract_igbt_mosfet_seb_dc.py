#!/usr/bin/env python3
"""Extract and gate one formal SEB campaign thermal-restart run."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def last_match(pattern: re.Pattern[str], text: str, label: str) -> re.Match[str]:
    matches = list(pattern.finditer(text))
    if not matches:
        raise ValueError(f"missing {label} in stdout")
    return matches[-1]


def artifact_record(path: Path) -> dict[str, object]:
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def extract(run_dir: Path) -> dict[str, object]:
    manifest_path = run_dir / "run_manifest.json"
    stdout_path = run_dir / "artifacts/stdout.log"
    if not manifest_path.is_file() or not stdout_path.is_file():
        raise FileNotFoundError("run_manifest.json or artifacts/stdout.log is missing")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
    contact = last_match(CONTACT_ROW, stdout, "final high-side contact row")
    temperature = last_match(TEMPERATURE_ROW, stdout, "final temperature row")

    target_vce = float(manifest["target_vce_v"])
    actual_vce = float(contact.group("voltage"))
    current = float(contact.group("total"))
    tmin = float(temperature.group("tmin"))
    tavg = float(temperature.group("tavg"))
    tmax = float(temperature.group("tmax"))
    relative_error = abs(actual_vce - target_vce) / abs(target_vce)

    case_id = str(manifest["case_id"])
    artifact_dir = run_dir / "artifacts"
    restart_main = artifact_dir / f"{case_id}_restart_des.sav"
    restart_circuit = artifact_dir / f"{case_id}_restart_circuit_des.sav"
    pre_tdr = artifact_dir / f"{case_id}_dc_pre_des.tdr"
    required = [restart_main, restart_circuit, pre_tdr]
    missing = [path.name for path in required if not path.is_file()]

    finite_values = [actual_vce, current, tmin, tavg, tmax]
    checks = {
        "runner_succeeded": manifest.get("lifecycle") == "SUCCEEDED" and str(manifest.get("exit_code")) == "0",
        "scheduler_verified": (
            manifest.get("allocation_mode") == "AUTO_LEASE"
            and manifest.get("sdevice_threads") == 1
            and manifest.get("lease_acquired") is True
            and manifest.get("lease_released") is True
            and manifest.get("affinity_verification") == "VERIFIED"
        ),
        "vce_relative_error_le_0p1pct": relative_error <= 0.001,
        "finite_operating_values": all(math.isfinite(value) for value in finite_values),
        "ordered_temperature_summary": tmin <= tavg <= tmax,
        "native_restart_pair_present": restart_main.is_file() and restart_circuit.is_file(),
        "prestrike_tdr_present": pre_tdr.is_file(),
    }
    passed = all(checks.values())
    return {
        "schema": "igbt_mosfet_seb_dc_gate/v1",
        "run_id": manifest["run_id"],
        "case_id": case_id,
        "attempt_id": manifest["attempt_id"],
        "device_family": manifest["device_family"],
        "target_vce_v": target_vce,
        "actual_vce_v": actual_vce,
        "vce_relative_error": relative_error,
        "high_side_current_a_per_um": current,
        "power_w_per_um": actual_vce * current,
        "tmin_k": tmin,
        "tavg_k": tavg,
        "tmax_k": tmax,
        "missing_required_artifacts": missing,
        "checks": checks,
        "status": "PASS" if passed else "FAIL",
        "artifacts": [artifact_record(path) for path in required if path.is_file()],
        "source_manifest": artifact_record(manifest_path),
        "source_stdout": artifact_record(stdout_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = extract(args.run_dir.resolve())
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())