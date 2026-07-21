# Run with Sentaurus Visual:
#   CASE_METADATA_FILE=... FINAL_TDR=... AUDIT_TDRS_JSON='{"9.2e-11":"..."}' OUTPUT_JSON=... \
#   svisual -b -python extract_pn_diode_tdr.py

import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

E_CHARGE_C = 1.602176634e-19


def choose(names, candidates, required=True):
    for candidate in candidates:
        if candidate in names:
            return candidate
    if required:
        raise RuntimeError("missing required field; tried: " + ", ".join(candidates))
    return None


def maximum(plot, field):
    value, position = sv.calculate_field_value(
        plot=plot, field=field, max=True, materials=["Silicon"]
    )
    result = {
        "field": field,
        "value": float(value),
        "position_um": [float(position[0]), float(position[1])],
        "material_scope": "Silicon",
    }
    if not all(math.isfinite(item) for item in [result["value"]] + result["position_um"]):
        raise RuntimeError("non-finite maximum for " + field)
    return result


metadata_path = Path(os.environ["CASE_METADATA_FILE"])
output_json = Path(os.environ["OUTPUT_JSON"])
metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
final_tdr = Path(os.environ.get("FINAL_TDR", metadata["exact_final_tdr"]))
audit_tdrs = json.loads(os.environ["AUDIT_TDRS_JSON"]) if "AUDIT_TDRS_JSON" in os.environ else metadata["heavy_ion_audit_tdrs"]

dataset = sv.load_file(str(final_tdr), name="pn_final", alldata=True, fod=True)
plot = sv.create_plot(dataset=dataset, name="pn_final_plot")
sv.select_plots(plot)
fields = list(sv.list_fields(dataset=dataset))
field_specs = {
    "electric_field": ("Abs(ElectricField-V)", "ElectricField", "ElectricField-V"),
    "avalanche_generation": ("AvalancheGeneration", "ImpactIonization"),
    "electron_density": ("eDensity", "ElectronDensity"),
    "hole_density": ("hDensity", "HoleDensity"),
    "heavy_ion_charge_density": ("HeavyIonChargeDensity",),
    "temperature": ("Temperature", "LatticeTemperature"),
}
field_maxima = {}
for logical, candidates in field_specs.items():
    actual = choose(fields, candidates, required=logical not in {"avalanche_generation", "temperature"})
    field_maxima[logical] = maximum(plot, actual) if actual else None

audit_rows = []
for time_text, source_text in sorted(audit_tdrs.items(), key=lambda item: float(item[0])):
    source = Path(source_text)
    audit_dataset = sv.load_file(
        str(source), name="audit_" + time_text.replace(".", "p").replace("-", "m"), alldata=True
    )
    audit_plot = sv.create_plot(
        dataset=audit_dataset, name="audit_plot_" + time_text.replace(".", "p").replace("-", "m")
    )
    sv.select_plots(audit_plot)
    audit_fields = list(sv.list_fields(dataset=audit_dataset))
    generation = choose(audit_fields, ("HeavyIonGeneration",))
    audit_rows.append(
        {
            "time_s": float(time_text),
            "source_tdr": str(source),
            "source_tdr_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "field": generation,
            "space_integral_raw": float(sv.integrate_field(plot=audit_plot, field=generation)),
            "domain_raw": float(
                sv.integrate_field(plot=audit_plot, field=generation, returndomain=True)
            ),
        }
    )

audit_times = np.asarray([row["time_s"] for row in audit_rows], dtype=float)
raw_rates = np.asarray([row["space_integral_raw"] for row in audit_rows], dtype=float)
trapz_charge_pc = float(np.trapz(raw_rates, audit_times) * E_CHARGE_C)
peak_rate = float(np.max(raw_rates))
fit_mask = raw_rates > peak_rate * 1e-4
fit_x_ps = (audit_times[fit_mask] - float(metadata["strike_time_s"])) / 1e-12
fit_log_rate = np.log(raw_rates[fit_mask])
fit_coefficients = np.polyfit(fit_x_ps, fit_log_rate, 2)
fit_values = np.polyval(fit_coefficients, fit_x_ps)
fit_residual = float(np.sum((fit_log_rate - fit_values) ** 2))
fit_total = float(np.sum((fit_log_rate - float(np.mean(fit_log_rate))) ** 2))
fit_r_squared = 1.0 - fit_residual / fit_total if fit_total > 0 else 1.0
quadratic, linear, constant = [float(value) for value in fit_coefficients]
if quadratic >= 0:
    raise RuntimeError("HeavyIon generation fit is not a decaying Gaussian")
gaussian_rate_integral = (
    math.exp(constant - linear * linear / (4.0 * quadratic))
    * math.sqrt(math.pi / -quadratic)
    * 1e-12
)
integrated_charge_pc = gaussian_rate_integral * E_CHARGE_C
nominal_charge_pc = float(metadata["let_f_pc_um"]) * float(metadata["length_um"])
closure_error_pct = abs(integrated_charge_pc / nominal_charge_pc - 1.0) * 100.0
trapz_closure_error_pct = abs(trapz_charge_pc / nominal_charge_pc - 1.0) * 100.0
result = {
    "schema": "pn_diode_tdr_extraction/v1",
    "case_id": metadata["case_id"],
    "source_final_tdr": str(final_tdr),
    "source_final_tdr_sha256": hashlib.sha256(final_tdr.read_bytes()).hexdigest(),
    "available_fields": fields,
    "field_maxima": field_maxima,
    "heavy_ion_charge": {
        "nominal_charge_pc_per_1um_depth": nominal_charge_pc,
        "integrated_generation_charge_pc_per_1um_depth": integrated_charge_pc,
        "closure_error_pct": closure_error_pct,
        "integration_method": "analytic integral of quadratic log-rate Gaussian fit",
        "gaussian_fit_coefficients_ps": [quadratic, linear, constant],
        "gaussian_fit_r_squared": fit_r_squared,
        "trapz_charge_pc_per_1um_depth_diagnostic": trapz_charge_pc,
        "trapz_closure_error_pct_diagnostic": trapz_closure_error_pct,
        "audit_points": audit_rows,
        "conversion": "integral(SVisual 2D generation rate,time)*elementary_charge",
    },
    "checks": {
        "all_audit_points_present": len(audit_rows) == len(audit_tdrs),
        "gaussian_fit_r_squared_ge_0p995": fit_r_squared >= 0.995,
        "charge_closure_le_5pct": closure_error_pct <= 5.0,
        "final_tdr_present": final_tdr.is_file(),
    },
}
result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
output_json.parent.mkdir(parents=True, exist_ok=True)
output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("PN_TDR_JSON_BEGIN")
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
print("PN_TDR_JSON_END")
if result["status"] != "PASS":
    raise RuntimeError("PN TDR extraction gate failed")