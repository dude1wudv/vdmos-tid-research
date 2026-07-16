#!/usr/bin/env python3
"""Summarize only the independent 650 V campaign's runner manifests."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = "igbt_mosfet_650v_seb_20260715"
PROFILE = "650v_commercial_comparison_pending_calibration"
SUMMARY_SCOPE = "post_static_dc_restart_and_heavyion_cases_at_325_400_500v_only"
POST_STATIC_BIASES = {325.0, 400.0, 500.0}
DEFAULT_RUNTIME = ROOT / "local_runtime" / "tcad_projects" / CAMPAIGN
DEFAULT_OUT = ROOT / "docs" / "changes" / "2026-07-15-igbt-mosfet-650v-redesign" / "data"
FIELDS = ("summary_scope", "case_id", "run_id", "device_family", "high_terminal_name", "bias_quantity", "target_blocking_voltage_v", "actual_blocking_voltage_v", "rated_voltage_v", "bv_static_v", "bv_criterion", "derating_basis", "termination_reason", "lifecycle", "exit_code", "wall_time_seconds", "local_run_dir")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    rows = []
    for path in sorted(args.runtime.glob("runs/*/run_manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        schema = manifest.get("case_schema", {})
        if schema.get("campaign_id") != CAMPAIGN or schema.get("publication_profile") != PROFILE:
            continue
        try:
            target_voltage = float(schema.get("target_blocking_voltage_v"))
        except (TypeError, ValueError):
            continue
        if target_voltage not in POST_STATIC_BIASES:
            continue
        row = {"summary_scope": SUMMARY_SCOPE, "case_id": manifest.get("case_id", "NA"), "run_id": manifest.get("run_id", "NA"), "lifecycle": manifest.get("lifecycle", "NA"), "exit_code": manifest.get("exit_code", "NA"), "wall_time_seconds": manifest.get("wall_time_seconds", "NA"), "local_run_dir": manifest.get("local_run_dir", "NA")}
        row.update({field: schema.get(field, "NA") for field in FIELDS if field not in row})
        rows.append(row)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "campaign_run_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (args.output / "campaign_run_summary.json").write_text(json.dumps({"campaign_id": CAMPAIGN, "publication_profile": PROFILE, "summary_scope": SUMMARY_SCOPE, "static_calibration_runs_excluded": True, "run_count": len(rows), "runs": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"campaign={CAMPAIGN} matched_runs={len(rows)}")


if __name__ == "__main__":
    main()