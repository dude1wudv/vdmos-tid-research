# Run under Sentaurus Visual, not CPython:
#   PLT_FILE=... FIELD_TDRS_JSON='{"pre":"..."}' OUTPUT_CSV=... OUTPUT_JSON=... \
#     svisual -b -python extract_igbt_seb_thermal_intervention.py
#
# This is a read-only postprocessor.  It never invokes SDevice or alters inputs.

import csv
import json
import os
from pathlib import Path

import numpy as np


def choose(variables, candidates, required=True):
    for name in candidates:
        if name in variables:
            return name
    if required:
        raise RuntimeError("missing required variable; tried: " + ", ".join(candidates))
    return None


def values(dataset, name):
    return np.asarray(sv.get_variable_data(dataset=dataset, varname=name), dtype=float)


plt_file = Path(os.environ["PLT_FILE"])
tdr_files = json.loads(os.environ["FIELD_TDRS_JSON"])
output_csv = Path(os.environ["OUTPUT_CSV"])
output_json = Path(os.environ["OUTPUT_JSON"])

plt_dataset = sv.load_file(str(plt_file), name="thermal_transient_plt")
plt_variables = list(sv.list_variables(dataset=plt_dataset))
time_name = choose(plt_variables, ("time", "Time"))
voltage_name = choose(plt_variables, ("Collector InnerVoltage", "Collector OuterVoltage"))
current_name = choose(plt_variables, ("Collector TotalCurrent",))
tmax_name = choose(plt_variables, ("Tmax", "MaximumTemperature", "LatticeTemperatureMax"), required=False)
time_s = values(plt_dataset, time_name)
voltage_v = values(plt_dataset, voltage_name)
current_a_um = values(plt_dataset, current_name)
tmax_k = values(plt_dataset, tmax_name) if tmax_name else None
if not (len(time_s) == len(voltage_v) == len(current_a_um)):
    raise RuntimeError("PLT required-variable lengths differ")
if tmax_k is not None and len(tmax_k) != len(time_s):
    raise RuntimeError("PLT Tmax length differs from time")

output_csv.parent.mkdir(parents=True, exist_ok=True)
with output_csv.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=[
        "time_s", "collector_inner_voltage_v", "collector_total_current_a_um", "plt_tmax_k"
    ])
    writer.writeheader()
    for index in range(len(time_s)):
        writer.writerow({
            "time_s": repr(float(time_s[index])),
            "collector_inner_voltage_v": repr(float(voltage_v[index])),
            "collector_total_current_a_um": repr(float(current_a_um[index])),
            "plt_tmax_k": "" if tmax_k is None else repr(float(tmax_k[index])),
        })

tdr_results = []
for label, tdr_file in tdr_files.items():
    field_dataset = sv.load_file(str(tdr_file), alldata=True, fod=True, name="field_" + label.replace(".", "p"))
    variables = list(sv.list_variables(dataset=field_dataset))
    temperature_name = choose(variables, ("Temperature", "LatticeTemperature"))
    temperature = values(field_dataset, temperature_name)
    if len(temperature) == 0:
        raise RuntimeError("empty temperature field: " + str(tdr_file))
    tdr_results.append({
        "checkpoint_id": label,
        "source_file": str(tdr_file),
        "temperature_variable": temperature_name,
        "node_count": int(len(temperature)),
        "tmin_k": float(np.nanmin(temperature)),
        "tmax_k": float(np.nanmax(temperature)),
        "temperature_all_finite": bool(np.isfinite(temperature).all()),
        "variables_available": variables,
    })

metadata = {
    "source_plt_file": str(plt_file),
    "plt_sample_count": int(len(time_s)),
    "plt_variables_available": plt_variables,
    "plt_variables_used": {
        "time": time_name,
        "collector_voltage": voltage_name,
        "collector_current": current_name,
        "tmax": tmax_name,
    },
    "plt_tmax_semantics": (
        "native PLT scalar" if tmax_name else
        "ABSENT: PLT has no Tmax-like scalar; blank plt_tmax_k is missing data, not zero or a frozen-temperature measurement"
    ),
    "time_start_s": float(time_s[0]),
    "time_end_s": float(time_s[-1]),
    "field_tdr_temperature": tdr_results,
    "extraction": "Sentaurus Visual Python API; read-only; PLT values written without resampling; TDR Tmax is nanmax(Temperature).",
}
output_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
print(json.dumps(metadata, indent=2))