# Run with Sentaurus Visual:
#   TDR_FILE=... PLT_FILE=... AUDIT_TDRS_JSON='{"9.2e-11":"..."}' \
#   CASE_ID=... OUTPUT_JSON=... OUTPUT_CSV=... PLOT_SPEC_FILE=... CASE_METADATA_FILE=... \
#   svisual -b -python extract_igbt_mosfet_seb_2ns.py

import csv
import json
import math
import os
from pathlib import Path

import numpy as np

E_CHARGE_C = 1.602176634e-19
MEV_TO_J = 1.602176634e-13
SILICON_DENSITY_MG_CM3 = 2329.0


def choose(variables, candidates, required=True):
    for name in candidates:
        if name in variables:
            return name
    if required:
        raise RuntimeError("missing required variable; tried: " + ", ".join(candidates))
    return None


def values(dataset, name):
    return np.asarray(sv.get_variable_data(dataset=dataset, varname=name), dtype=float)


case_id = os.environ["CASE_ID"]
tdr_file = Path(os.environ["TDR_FILE"])
plt_file = Path(os.environ["PLT_FILE"])
output_json = Path(os.environ["OUTPUT_JSON"])
output_csv = Path(os.environ["OUTPUT_CSV"])
plot_spec = json.loads(Path(os.environ["PLOT_SPEC_FILE"]).read_text(encoding="utf-8-sig"))
case_metadata = json.loads(Path(os.environ["CASE_METADATA_FILE"]).read_text(encoding="utf-8-sig"))
audit_tdrs = json.loads(os.environ.get("AUDIT_TDRS_JSON", "{}"))
track_y_um = float(case_metadata["track_y_um"])
let_f_pc_um = float(case_metadata["let_f_pc_um"])
track_length_um = float(case_metadata["length_um"])

dataset = sv.load_file(str(tdr_file), name="field_2p1ns", alldata=True, fod=True)
field_plot = sv.create_plot(dataset=dataset, name="plot_2p1ns")
sv.select_plots(field_plot)
probe_cut = sv.create_cutline(type="y", at=track_y_um, dataset=dataset, regions=["R.Si"], name="field_probe_cut")
variables = list(sv.list_variables(dataset=probe_cut))

field_rows = []
hotspot_result = None
for item in plot_spec["required_quantities"]:
    logical = item["logical"]
    actual = choose(variables, tuple(item["candidates"]), required=True)
    probe_data = values(probe_cut, actual)
    finite_probe = np.isfinite(probe_data)
    if len(probe_data) == 0 or not np.any(finite_probe):
        raise RuntimeError("field has no finite Silicon probe values: " + actual)
    minimum = sv.calculate_field_value(plot=field_plot, field=actual, min=True, materials=["Silicon"])
    maximum = sv.calculate_field_value(plot=field_plot, field=actual, max=True, materials=["Silicon"])
    min_value, min_position = float(minimum[0]), minimum[1]
    max_value, max_position = float(maximum[0]), maximum[1]
    extrema_finite = all(math.isfinite(value) for value in (min_value, max_value, *min_position[:2], *max_position[:2]))
    if logical == "temperature":
        hotspot_result = (max_value, [float(max_position[0]), float(max_position[1])])
    field_rows.append({
        "case_id": case_id,
        "logical_quantity": logical,
        "actual_field_name": actual,
        "unit": "native_svisual_unit",
        "node_count": int(len(probe_data)),
        "finite_count": int(np.count_nonzero(finite_probe)),
        "all_finite": bool(np.isfinite(probe_data).all() and extrema_finite),
        "minimum": min_value,
        "minimum_x_um": float(min_position[0]),
        "minimum_y_um": float(min_position[1]),
        "maximum": max_value,
        "maximum_x_um": float(max_position[0]),
        "maximum_y_um": float(max_position[1]),
        "region_scope": f"Silicon full-domain extrema; frozen-track y={track_y_um:.12g} um cutline finite-value audit",
    })

if hotspot_result is None:
    raise RuntimeError("temperature hotspot was not extracted")
hotspot_temperature, hotspot_xy = hotspot_result

plt_dataset = sv.load_file(str(plt_file), name="transient_plt")
plt_variables = list(sv.list_variables(dataset=plt_dataset))
time_name = choose(plt_variables, ("time", "Time"))
high_contact = "Drain" if "MOSFET" in case_id.upper() else "Collector"
voltage_name = choose(plt_variables, (high_contact + " InnerVoltage", high_contact + " OuterVoltage"))
current_name = choose(plt_variables, (high_contact + " TotalCurrent",))
time_s = values(plt_dataset, time_name)
voltage_v = values(plt_dataset, voltage_name)
current_a_um = values(plt_dataset, current_name)
if not (len(time_s) == len(voltage_v) == len(current_a_um)):
    raise RuntimeError("PLT required-variable lengths differ")
order = np.argsort(time_s)
time_s = time_s[order]
voltage_v = voltage_v[order]
current_a_um = current_a_um[order]
baseline_current = float(current_a_um[0])
current_excursion = np.abs(current_a_um - baseline_current)
absolute_power_w_um = np.abs(voltage_v * current_a_um)
peak_current_index = int(np.argmax(np.abs(current_a_um)))
peak_power_index = int(np.argmax(absolute_power_w_um))
collected_charge_pc_um = float(np.trapz(current_excursion, time_s) * 1e12)
port_energy_j_um = float(np.trapz(absolute_power_w_um, time_s))
peak_excursion = float(np.max(current_excursion))
final_excursion = float(current_excursion[-1])
recovery_fraction = final_excursion / peak_excursion if peak_excursion > 0 else 0.0
tail_start = max(0, int(len(time_s) * 0.9))
tail_time = time_s[tail_start:]
tail_current = np.abs(current_a_um[tail_start:])
tail_slope_a_um_s = float(np.polyfit(tail_time, tail_current, 1)[0]) if len(tail_time) >= 2 else math.nan
recovered_to_10pct = bool(recovery_fraction <= 0.1)
sustained_growth = bool(len(tail_current) >= 2 and tail_slope_a_um_s > 0 and tail_current[-1] > tail_current[0])

audit_rows = []
for time_text, source in sorted(audit_tdrs.items(), key=lambda item: float(item[0])):
    audit_dataset = sv.load_file(str(source), name="audit_" + time_text.replace(".", "p").replace("-", "m"), alldata=True)
    generation_name = "HeavyIonGeneration"
    audit_plot = sv.create_plot(dataset=audit_dataset, name="plot_" + time_text.replace(".", "p").replace("-", "m"))
    sv.select_plots(audit_plot)
    raw_integral = float(sv.integrate_field(plot=audit_plot, field=generation_name))
    raw_domain = float(sv.integrate_field(plot=audit_plot, field=generation_name, returndomain=True))
    audit_rows.append({
        "time_s": float(time_text),
        "source_tdr": str(source),
        "field": generation_name,
        "space_integral_raw": raw_integral,
        "domain_raw": raw_domain,
    })

nominal_charge_pc = let_f_pc_um * track_length_um
nominal_deposited_energy_mev = (
    float(case_metadata["let_mev_cm2_mg"])
    * SILICON_DENSITY_MG_CM3
    * track_length_um
    * 1e-4
)
nominal_deposited_energy_j = nominal_deposited_energy_mev * MEV_TO_J
integrated_charge_pc = None
charge_error_pct = None
if len(audit_rows) >= 2:
    audit_times = np.asarray([row["time_s"] for row in audit_rows], dtype=float)
    raw_rates = np.asarray([row["space_integral_raw"] for row in audit_rows], dtype=float)
    integrated_charge_pc = float(np.trapz(raw_rates, audit_times) * E_CHARGE_C)
    charge_error_pct = float(abs(integrated_charge_pc / nominal_charge_pc - 1.0) * 100.0)
expected_audit_times = sorted(float(item) for item in case_metadata["heavy_ion_audit_tdrs"])
observed_audit_times = sorted(row["time_s"] for row in audit_rows)
audit_points_complete = len(expected_audit_times) == len(observed_audit_times) and all(
    math.isclose(expected, observed, rel_tol=0.0, abs_tol=1e-16)
    for expected, observed in zip(expected_audit_times, observed_audit_times)
)

checks = {
    "exact_tdr_present": tdr_file.is_file(),
    "all_required_fields_present": len(field_rows) == len(plot_spec["required_quantities"]),
    "all_required_fields_have_finite_values": all(row["all_finite"] for row in field_rows),
    "all_terminal_values_finite": bool(np.isfinite(time_s).all() and np.isfinite(voltage_v).all() and np.isfinite(current_a_um).all()),
    "plt_reaches_exact_2p1ns": bool(len(time_s) and math.isclose(float(time_s[-1]), 2.1e-9, rel_tol=0.0, abs_tol=1e-15)),
    "all_charge_audit_points_present": audit_points_complete,
    "charge_closure_le_5pct": charge_error_pct is not None and charge_error_pct <= 5.0,
}
status = "PASS" if all(checks.values()) else "FAIL"

output_csv.parent.mkdir(parents=True, exist_ok=True)
with output_csv.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(field_rows[0].keys()))
    writer.writeheader()
    writer.writerows(field_rows)

result = {
    "schema": "igbt_mosfet_seb_2ns_extraction/v1",
    "case_id": case_id,
    "status": status,
    "source_tdr": str(tdr_file),
    "source_plt": str(plt_file),
    "source_time_s": 2.1e-9,
    "post_strike_time_s": 2.0e-9,
    "variables_available": variables,
    "field_summary_csv": str(output_csv),
    "hotspot": {
        "x_um": hotspot_xy[0],
        "y_um": hotspot_xy[1],
        "temperature_k": hotspot_temperature,
        "scope": "full Silicon-domain argmax at the final stored state",
    },
    "terminal_summary": {
        "sample_count": int(len(time_s)),
        "time_end_s": float(time_s[-1]),
        "baseline_current_a_um": baseline_current,
        "final_current_a_um": float(current_a_um[-1]),
        "peak_abs_current_a_um": float(abs(current_a_um[peak_current_index])),
        "peak_current_time_s": float(time_s[peak_current_index]),
        "peak_abs_power_w_um": float(absolute_power_w_um[peak_power_index]),
        "peak_power_time_s": float(time_s[peak_power_index]),
        "collected_charge_pc_um": collected_charge_pc_um,
        "port_energy_j_um": port_energy_j_um,
        "final_to_peak_excursion_fraction": recovery_fraction,
        "tail_abs_current_slope_a_um_s": tail_slope_a_um_s,
        "recovered_to_10pct_of_peak_excursion": recovered_to_10pct,
        "sustained_tail_growth": sustained_growth,
    },
    "deposited_energy": {
        "nominal_mev": nominal_deposited_energy_mev,
        "nominal_j": nominal_deposited_energy_j,
        "definition": "LET(MeV cm^2/mg) * silicon density(2329 mg/cm^3) * frozen in-Silicon track length(cm)",
    },
    "heavy_ion_charge": {
        "let_f_pc_um": let_f_pc_um,
        "track_length_um": track_length_um,
        "nominal_charge_pc": nominal_charge_pc,
        "integrated_charge_pc": integrated_charge_pc,
        "closure_error_pct": charge_error_pct,
        "conversion": "trapz(SVisual 2D generation integral,time)*elementary_charge; assumes geometry coordinates in um and 1 um out-of-plane thickness, so um^3-to-cm^3 and C-to-pC factors cancel",
        "audit_points": audit_rows,
    },
    "checks": checks,
}
output_json.parent.mkdir(parents=True, exist_ok=True)
output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
if status != "PASS":
    raise RuntimeError("reference extraction gate failed")