# Run with Sentaurus Visual:
#   SOURCE_TDR=... CASE_ID=... DEVICE_FAMILY=... BIAS_V=... MESH_SHA256=... OUTPUT_JSON=... \
#   svisual -b -python extract_igbt_mosfet_650v_field_tdr.py

import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

source = Path(os.environ["SOURCE_TDR"])
output = Path(os.environ["OUTPUT_JSON"])
case_id = os.environ["CASE_ID"]
family = os.environ["DEVICE_FAMILY"]
bias_v = float(os.environ["BIAS_V"])
mesh_sha256 = os.environ["MESH_SHA256"]
track_start_x = float(os.environ["TRACK_START_X"])
track_end_x = float(os.environ["TRACK_END_X"])
track_y_mode = os.environ.get("TRACK_Y_MODE", "EXPLICIT")
track_y_requested = os.environ.get("TRACK_Y")
strict_margin = float(os.environ.get("STRICT_MARGIN", "0.01"))

dataset = sv.load_file(str(source), name="field_localization", alldata=True, fod=True)
plot = sv.create_plot(dataset=dataset, name="field_localization_plot")
sv.select_plots(plot)
fields = list(sv.list_fields(dataset=dataset))


def choose(candidates, required=True):
    for name in candidates:
        if name in fields:
            return name
    if required:
        raise RuntimeError("missing required field: " + ", ".join(candidates))
    return None


def maximum(field):
    result = sv.calculate_field_value(plot=plot, field=field, max=True, materials=["Silicon"])
    value = float(result[0])
    position = [float(result[1][0]), float(result[1][1])]
    if not all(math.isfinite(item) for item in [value] + position):
        raise RuntimeError("non-finite Silicon maximum for " + field)
    return {"field": field, "value": value, "position_um": position, "material_scope": "Silicon"}


def track_path_maximum(field, track_y, cut_name):
    cut = sv.create_cutline(type="y", at=track_y, dataset=dataset, regions=["R.Si"], name=cut_name)
    variables = list(sv.list_variables(dataset=cut))
    field_name = next((name for name in (field, "Abs(ElectricField-V)", "ElectricField") if name in variables), None)
    if field_name is None or "X" not in variables:
        raise RuntimeError("track cutline lacks X or electric-field magnitude")
    x_values = np.asarray(sv.get_variable_data(dataset=cut, varname="X"), dtype=float)
    field_values = np.asarray(sv.get_variable_data(dataset=cut, varname=field_name), dtype=float)
    mask = np.isfinite(x_values) & np.isfinite(field_values) & (x_values >= track_start_x) & (x_values <= track_end_x)
    if not np.any(mask):
        raise RuntimeError("track cutline has no finite samples inside the strict-interior segment")
    indexes = np.flatnonzero(mask)
    index = int(indexes[np.argmax(field_values[indexes])])
    return {
        "field": field_name,
        "value": float(field_values[index]),
        "position_um": [float(x_values[index]), float(track_y)],
        "sample_count": int(len(indexes)),
        "segment_x_um": [track_start_x, track_end_x],
        "material_scope": "R.Si cutline",
    }


electric_field = choose(("Abs(ElectricField-V)", "ElectricField", "ElectricField-V"))
impact_field = choose(("ImpactIonization", "AvalancheGeneration"), required=False)
potential_field = choose(("ElectrostaticPotential", "Potential"), required=False)
electric_field_max = maximum(electric_field)
impact_ionization_max = maximum(impact_field) if impact_field else None
if track_y_mode == "IMPACT_MAX_Y":
    if impact_ionization_max is None:
        raise RuntimeError("IMPACT_MAX_Y requires ImpactIonization or AvalancheGeneration")
    track_y = min(6.0 - strict_margin, max(strict_margin, float(impact_ionization_max["position_um"][1])))
    track_y_source = "impact-ionization maximum y coordinate, clamped to strict Silicon interior"
elif track_y_mode == "EXPLICIT":
    if track_y_requested is None:
        raise RuntimeError("EXPLICIT track selection requires TRACK_Y")
    track_y = float(track_y_requested)
    if not strict_margin <= track_y <= 6.0 - strict_margin:
        raise RuntimeError("explicit track y is outside the strict Silicon interior")
    track_y_source = "explicit geometry-derived y coordinate"
else:
    raise RuntimeError("unsupported TRACK_Y_MODE: " + track_y_mode)
track_field_max = track_path_maximum(electric_field, track_y, "track_path_electric")
track_impact_max = track_path_maximum(impact_field, track_y, "track_path_impact") if impact_field else None
result = {
    "schema_version": "650v_field_localization_tdr_extraction/v2",
    "case_id": case_id,
    "device_family": family,
    "bias_v": bias_v,
    "mesh_sha256": mesh_sha256,
    "source_tdr": str(source),
    "source_tdr_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "source_tdr_size_bytes": source.stat().st_size,
    "coordinate_system": {"x": "device depth from top surface", "y": "lateral cell coordinate", "unit": "um"},
    "electric_field_max": electric_field_max,
    "impact_ionization_max": impact_ionization_max,
    "track_selection": {
        "mode": track_y_mode,
        "track_y_um": track_y,
        "source": track_y_source,
        "strict_margin_um": strict_margin,
    },
    "track_path_electric_field_max": track_field_max,
    "track_path_impact_ionization_max": track_impact_max,
    "potential_max": maximum(potential_field) if potential_field else None,
    "available_fields": fields,
    "status": "VERIFIED",
}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print("FIELD_JSON_BEGIN")
print(json.dumps(result, sort_keys=True))
print("FIELD_JSON_END")