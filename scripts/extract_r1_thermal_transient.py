# Run with Sentaurus Visual from the R1 artifact directory:
#   svisual -b -python extract_r1_thermal_transient.py
# It uses SVisual's bundled Python/NumPy only and writes a raw, lossless PLT table.

import csv
import json
import os
from pathlib import Path

import numpy as np

INPUT_FILE = os.environ.get("R1_INPUT_FILE", "transient_r1_coupled.plt")
CSV_FILE = os.environ.get("R1_OUTPUT_CSV", "r1_transient_raw.csv")
JSON_FILE = os.environ.get("R1_OUTPUT_JSON", "r1_transient_extract_metadata.json")


def choose(variables, candidates):
    for name in candidates:
        if name in variables:
            return name
    raise RuntimeError("missing required variable; tried: " + ", ".join(candidates))


def read(dataset, name):
    return np.asarray(sv.get_variable_data(dataset=dataset, varname=name), dtype=float)


dataset = sv.load_file(INPUT_FILE, name="R1_transient")
variables = list(sv.list_variables(dataset=dataset))
time_name = choose(variables, ("time", "Time"))
voltage_name = choose(variables, ("Collector InnerVoltage", "Collector OuterVoltage"))
current_name = choose(variables, ("Collector TotalCurrent",))
tmax_name = choose(variables, ("Tmax", "MaximumTemperature", "LatticeTemperatureMax"))

time_s = read(dataset, time_name)
voltage_v = read(dataset, voltage_name)
current_a_um = read(dataset, current_name)
tmax_k = read(dataset, tmax_name)
if not (len(time_s) == len(voltage_v) == len(current_a_um) == len(tmax_k)):
    raise RuntimeError("PLT variable lengths differ")
if len(time_s) == 0:
    raise RuntimeError("PLT contains no samples")

with Path(CSV_FILE).open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=["time_s", "collector_inner_voltage_v", "collector_total_current_a_um", "tmax_k"],
    )
    writer.writeheader()
    for values in zip(time_s, voltage_v, current_a_um, tmax_k):
        writer.writerow(
            {
                "time_s": repr(float(values[0])),
                "collector_inner_voltage_v": repr(float(values[1])),
                "collector_total_current_a_um": repr(float(values[2])),
                "tmax_k": repr(float(values[3])),
            }
        )

metadata = {
    "source_file": INPUT_FILE,
    "sample_count": int(len(time_s)),
    "variables_available": variables,
    "variables_used": {
        "time": time_name,
        "collector_voltage": voltage_name,
        "collector_current": current_name,
        "tmax": tmax_name,
    },
    "time_start_s": float(time_s[0]),
    "time_end_s": float(time_s[-1]),
    "extraction": "SVisual Python API; values written without resampling",
}
Path(JSON_FILE).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
print(json.dumps(metadata, indent=2))