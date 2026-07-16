"""Build the 298 K / 550 V baseline-versus-track-refined mesh gate table.

This read-only summarizer accepts only SVisual JSON/CSV sidecars.  It never
reads TDR/PLT files and never starts a Sentaurus solver.
"""

import argparse
import csv
import json
import math
from pathlib import Path


GATES = (
    ("tmax_k", "json", "hotspot.temperature_k", "K", "abs(refined-baseline)/abs(baseline)*100", 5.0),
    ("terminal_collected_charge_pc_um", "json", "terminal_summary.collected_charge_pc_um", "pC/um", "abs(refined-baseline)/abs(baseline)*100", 5.0),
    ("terminal_energy_j_um", "json", "terminal_summary.energy_j_um", "J/um", "abs(refined-baseline)/abs(baseline)*100", 5.0),
    ("emax_v_cm", "csv", "electric_field.maximum", "V/cm", "abs(refined-baseline)/abs(baseline)*100", 10.0),
    ("hotspot_interface_distance_um", "json", "hotspot.distance_um", "um", "abs(refined-baseline)", 0.01),
)


def load_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def nested(mapping, dotted):
    value = mapping
    for key in dotted.split("."):
        value = value[key]
    return float(value)


def electric_field_maximum(path):
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["logical_quantity"] == "electric_field":
                return float(row["maximum"])
    raise ValueError(f"electric_field row not found: {path}")


def status_for(value, threshold):
    if not math.isfinite(value):
        return "NOT_ASSESSABLE"
    return "PASS" if value <= threshold else "FAIL"


def sources(root, device):
    baseline_case = f"{device}_T298_V550_L15"
    refined_case = f"VAL_{device}_T298_V550_L15_track_refined"
    return {
        "baseline_json": root / f"{baseline_case}_2ns.json",
        "baseline_csv": root / f"{baseline_case}_2ns_fields.csv",
        "refined_json": root / f"{refined_case}_2ns.json",
        "refined_csv": root / f"{refined_case}_2ns_fields.csv",
    }


def extract_value(kind, dotted, json_data, csv_path):
    return nested(json_data, dotted) if kind == "json" else electric_field_maximum(csv_path)


def compare_device(root, device):
    files = sources(root, device)
    baseline = load_json(files["baseline_json"])
    refined = load_json(files["refined_json"])
    sidecar_status = baseline.get("status") == "PASS" and refined.get("status") == "PASS"
    rows = []
    for metric, kind, dotted, unit, formula, threshold in GATES:
        baseline_value = extract_value(kind, dotted, baseline, files["baseline_csv"])
        refined_value = extract_value(kind, dotted, refined, files["refined_csv"])
        difference = abs(refined_value - baseline_value)
        if metric == "hotspot_interface_distance_um":
            gate_value = difference
            relative_pct = None
        elif baseline_value == 0.0:
            gate_value = math.nan
            relative_pct = None
        else:
            relative_pct = difference / abs(baseline_value) * 100.0
            gate_value = relative_pct
        status = status_for(gate_value, threshold) if sidecar_status else "NOT_ASSESSABLE"
        rows.append({
            "device_family": device,
            "temperature_k": 298.15,
            "bias_v": 550.0,
            "baseline_case_id": baseline["case_id"],
            "refined_case_id": refined["case_id"],
            "metric": metric,
            "unit": unit,
            "baseline_value": baseline_value,
            "refined_value": refined_value,
            "absolute_difference": difference,
            "relative_difference_pct": relative_pct if relative_pct is not None else "NA",
            "formula": formula,
            "gate_value": gate_value,
            "threshold": threshold,
            "status": status,
            "baseline_json": str(files["baseline_json"]),
            "baseline_fields_csv": str(files["baseline_csv"]),
            "refined_json": str(files["refined_json"]),
            "refined_fields_csv": str(files["refined_csv"]),
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extracts-dir", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    rows = [row for device in ("IGBT", "MOSFET") for row in compare_device(args.extracts_dir, device)]
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {}
    for device in ("IGBT", "MOSFET"):
        device_rows = [row for row in rows if row["device_family"] == device]
        summary[device] = {
            "status": "PASS" if all(row["status"] == "PASS" for row in device_rows) else "FAIL",
            "gate_statuses": {row["metric"]: row["status"] for row in device_rows},
        }
    result = {
        "schema": "igbt_mosfet_seb_mesh_comparison/v1",
        "source_policy": "Only SVisual JSON/CSV sidecars were read; no TDR, PLT, screenshot, or solver output was parsed.",
        "criteria": {
            "temperature_and_terminal_relative_difference_pct": 5.0,
            "electric_field_relative_difference_pct": 10.0,
            "hotspot_interface_distance_absolute_difference_um": 0.01,
        },
        "devices": summary,
        "overall_status": "PASS" if all(item["status"] == "PASS" for item in summary.values()) else "FAIL",
        "rows": rows,
    }
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall_status": result["overall_status"], "devices": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()