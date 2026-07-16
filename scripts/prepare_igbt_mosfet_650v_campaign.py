#!/usr/bin/env python3
"""Render the independent 650 V IGBT/SJ-MOSFET campaign contract into private decks."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "igbt_mosfet_650v_seb_20260715"
DEFAULT_RUNTIME = ROOT / "local_runtime" / "tcad_projects" / "igbt_mosfet_650v_seb_20260715"
DEFAULT_REPORT_DATA = ROOT / "docs" / "changes" / "2026-07-15-igbt-mosfet-650v-redesign" / "data"
AUTHORIZATION_EVIDENCE = DEFAULT_REPORT_DATA / "heavy_ion_authorization.json"
DEVICE_FILES = (PROJECT / "devices" / "igbt_650v.json", PROJECT / "devices" / "mosfet_650v_sj.json")
PARAMETER_SEEDS = {
    "IGBT": DEFAULT_RUNTIME / "seed_IGBT_TrenchFieldStop" / "sdevice.par",
    "MOSFET": DEFAULT_RUNTIME / "seed_MOSFET_SuperJunction" / "sdevice.par",
}
BIASES = (325, 400, 500)
REFERENCE_LET_MEV_CM2_MG = 15.0
REFERENCE_LET_F_PC_UM = 0.1555
REFERENCE_WT_HI_UM = 0.1
REFERENCE_AUDIT_POINTS = (
    ("092ps", 9.2e-11), ("094ps", 9.4e-11), ("096ps", 9.6e-11), ("097ps", 9.7e-11),
    ("098ps", 9.8e-11), ("099ps", 9.9e-11), ("099p5ps", 9.95e-11), ("100ps", 1.0e-10),
    ("100p2ps", 1.002e-10), ("100p5ps", 1.005e-10), ("101ps", 1.01e-10),
    ("102ps", 1.02e-10), ("103ps", 1.03e-10), ("104ps", 1.04e-10),
    ("106ps", 1.06e-10), ("108ps", 1.08e-10),
)
REQUIRED = {"seed_value", "final_value", "unit", "source_evidence", "confidence", "calibration_status"}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace("\r\n", "\n"))


def value(spec: dict, name: str):
    item = spec["parameters"][name]
    if item["final_value"] is not None:
        return item["final_value"]
    if item.get("candidate_value") is not None:
        return item["candidate_value"]
    return item["seed_value"]


def mosfet_pillar_dopings(spec: dict) -> tuple[float, float]:
    scale = float(value(spec, "sj_pillar_doping_scale"))
    donor = float(value(spec, "n_pillar_donor_concentration")) * scale
    acceptor = float(value(spec, "p_pillar_acceptor_concentration")) * scale
    return donor, acceptor


def derived_metrics(spec: dict) -> dict:
    if spec["device_family"] != "MOSFET":
        return {}
    donor, acceptor = mosfet_pillar_dopings(spec)
    pitch = float(value(spec, "pillar_pitch"))
    p_width = float(value(spec, "p_pillar_width"))
    drain_setback = float(value(spec, "p_pillar_drain_setback"))
    drift = float(value(spec, "drift_thickness"))
    return {
        "sj_charge_balance_ratio": acceptor * p_width / (donor * pitch),
        "sj_effective_n_pillar_donor_concentration_cm3": donor,
        "sj_effective_p_pillar_acceptor_concentration_cm3": acceptor,
        "sj_pillar_doping_scale": float(value(spec, "sj_pillar_doping_scale")),
        "sj_net_pillar_acceptor_concentration_cm3": acceptor - donor,
        "sj_pillar_end_x_um": drift - drain_setback,
    }


def validate(spec: dict, source: Path) -> None:
    for key in ("schema_version", "structure_id", "device_family", "rated_voltage_v", "publication_profile", "gate_contact", "candidate_freeze", "parameters", "physics_contract", "static_targets", "static_gates", "mesh_consistency_contract"):
        if key not in spec:
            raise ValueError(f"{source.name}: missing {key}")
    if spec["schema_version"] != "650v_device_parameter_dsl/v1":
        raise ValueError(f"{source.name}: unsupported schema")
    if spec["rated_voltage_v"] != 650 or spec["device_family"] not in {"IGBT", "MOSFET"}:
        raise ValueError(f"{source.name}: expected a 650 V IGBT or MOSFET")
    freeze = spec["candidate_freeze"]
    freeze_required = {"status", "candidate_id", "candidate_values", "baseline_mesh_sha256", "baseline_run_set", "baseline_extraction", "scope_note"}
    if set(freeze) != freeze_required or not str(freeze["status"]).startswith("FROZEN_REFERENCE_MODEL_"):
        raise ValueError(f"{source.name}: invalid reference-model candidate freeze")
    if not re.fullmatch(r"[0-9a-f]{64}", str(freeze["baseline_mesh_sha256"])):
        raise ValueError(f"{source.name}: candidate freeze must bind a baseline mesh SHA-256")
    baseline_profile = mesh_profile(spec, "baseline")
    refined_profile = mesh_profile(spec, "refined")
    if baseline_profile == refined_profile:
        raise ValueError(f"{source.name}: refined mesh profile must differ from baseline")
    thresholds = spec["mesh_consistency_contract"].get("thresholds", {})
    expected_thresholds = {"bv_relative_max", "vth_absolute_v_max", "conduction_relative_max", "off_leakage_relative_max"}
    if set(thresholds) != expected_thresholds or any(not 0 < float(item) < 1 for item in thresholds.values()):
        raise ValueError(f"{source.name}: invalid fail-closed mesh thresholds")
    gate_contact = spec["gate_contact"]
    if spec["device_family"] == "IGBT":
        if set(gate_contact) != {"electrode_model", "barrier_ev", "source_evidence"} or gate_contact["electrode_model"] != "barrier_offset":
            raise ValueError(f"{source.name}: IGBT gate must preserve the seed barrier-offset contract")
        if not -2.0 <= float(gate_contact["barrier_ev"]) <= 2.0:
            raise ValueError(f"{source.name}: IGBT gate barrier is outside the supported calibration range")
    else:
        required_gate = {"electrode_model", "material", "conductivity_type", "source_evidence"}
        if set(gate_contact) != required_gate or gate_contact["electrode_model"] != "n_type_polysilicon":
            raise ValueError(f"{source.name}: MOSFET gate must preserve the seed n-type polysilicon contract")
        if gate_contact["material"] != "PolySi" or gate_contact["conductivity_type"] != "N":
            raise ValueError(f"{source.name}: MOSFET gate material contract is invalid")
    targets = spec["static_targets"]
    if set(targets) != {"temperature_k", "vth", "conduction", "off_leakage"}:
        raise ValueError(f"{source.name}: static_targets must define temperature, vth, conduction, and off_leakage")
    if float(targets["temperature_k"]) <= 0:
        raise ValueError(f"{source.name}: static target temperature must be positive")
    vth = targets["vth"]
    if set(vth) != {"min_v", "typ_v", "max_v", "criterion_current_a", "bias_relation"}:
        raise ValueError(f"{source.name}: Vth target must preserve the full datasheet test contract")
    if not float(vth["min_v"]) < float(vth["typ_v"]) < float(vth["max_v"]):
        raise ValueError(f"{source.name}: Vth target ordering is invalid")
    expected_bias_relation = "VCE=VGE" if spec["device_family"] == "IGBT" else "VDS=VGS"
    if vth["bias_relation"] != expected_bias_relation or float(vth["criterion_current_a"]) <= 0:
        raise ValueError(f"{source.name}: Vth criterion or synchronous bias relation is invalid")
    conduction_keys = {"gate_voltage_v", "current_a", "typ_voltage_v", "max_voltage_v"} if spec["device_family"] == "IGBT" else {"gate_voltage_v", "current_a", "typ_resistance_ohm", "max_resistance_ohm"}
    if set(targets["conduction"]) != conduction_keys:
        raise ValueError(f"{source.name}: conduction target must preserve the full datasheet test contract")
    if any(float(targets["conduction"][name]) <= 0 for name in conduction_keys):
        raise ValueError(f"{source.name}: conduction targets must be positive")
    if set(targets["off_leakage"]) != {"blocking_voltage_v", "max_current_a"}:
        raise ValueError(f"{source.name}: off-leakage target must preserve voltage and current")
    if float(targets["off_leakage"]["blocking_voltage_v"]) != 650 or float(targets["off_leakage"]["max_current_a"]) <= 0:
        raise ValueError(f"{source.name}: off-leakage target is invalid")
    for name, item in spec["parameters"].items():
        missing = REQUIRED - item.keys()
        if missing:
            raise ValueError(f"{source.name}:{name}: missing {sorted(missing)}")
        if item["final_value"] is not None and item["calibration_status"] != "VERIFIED":
            raise ValueError(f"{source.name}:{name}: final_value requires VERIFIED calibration_status")
    for name in ("drift_thickness", "track_x", "track_y", "track_length"):
        if name not in spec["parameters"] or not isinstance(value(spec, name), (int, float)):
            raise ValueError(f"{source.name}: {name} must be numeric")
    if spec["static_gates"].get("heavy_ion_authorized") is True:
        direction_item = spec["parameters"].get("track_direction")
        if not isinstance(direction_item, dict) or direction_item.get("calibration_status") != "VERIFIED":
            raise ValueError(f"{source.name}: authorized HeavyIon requires a VERIFIED track_direction")
        direction = value(spec, "track_direction")
        if not isinstance(direction, list) or len(direction) != 2 or sum(float(item) ** 2 for item in direction) <= 0:
            raise ValueError(f"{source.name}: invalid HeavyIon track direction")
        start_x = float(value(spec, "track_x"))
        start_y = float(value(spec, "track_y"))
        length = float(value(spec, "track_length"))
        end_x = start_x + float(direction[0]) * length
        end_y = start_y + float(direction[1]) * length
        drift = float(value(spec, "drift_thickness"))
        if not (0 < start_x < drift and 0 < end_x < drift and 0 < start_y < 6 and 0 < end_y < 6):
            raise ValueError(f"{source.name}: authorized HeavyIon track must remain strictly inside Silicon bounds")
    gate_oxide_thickness = float(value(spec, "gate_oxide_thickness"))
    if not 0.005 <= gate_oxide_thickness <= 0.2:
        raise ValueError(f"{source.name}: gate oxide thickness must be in [0.005, 0.2] um")
    body_start = float(value(spec, "body_implant_y_start"))
    body_end = float(value(spec, "body_implant_y_end"))
    source_end = float(value(spec, "source_implant_y_end"))
    oxide_outer_upper_y = 2.8 + gate_oxide_thickness
    if not 2.7 <= body_start <= oxide_outer_upper_y + 0.02:
        raise ValueError(f"{source.name}: P-body start leaves an uncovered gate-edge channel")
    if not body_start < source_end < body_end:
        raise ValueError(f"{source.name}: body/source implant extents are inconsistent")
    body_peak = float(value(spec, "body_peak_acceptor_concentration"))
    if not 1e16 <= body_peak <= 1e19:
        raise ValueError(f"{source.name}: P-body peak must be in [1e16, 1e19] cm^-3")
    interface_charge = float(value(spec, "interface_fixed_charge_concentration"))
    if not -5e12 <= interface_charge <= 5e12:
        raise ValueError(f"{source.name}: interface fixed charge must be in [-5e12, 5e12] cm^-2")
    if float(value(spec, "gate_corner_radius")) < 0:
        raise ValueError(f"{source.name}: gate corner radius must be non-negative")
    if spec["device_family"] == "IGBT":
        if float(value(spec, "field_stop_thickness")) <= 0 or float(value(spec, "field_stop_donor_concentration")) <= 0:
            raise ValueError(f"{source.name}: field-stop parameters must be positive")
        lifetime = float(value(spec, "minority_carrier_lifetime"))
        if not 1e-9 <= lifetime <= 1e-3:
            raise ValueError(f"{source.name}: minority-carrier lifetime must be in [1 ns, 1 ms]")
    if spec["device_family"] == "MOSFET":
        donor, acceptor = mosfet_pillar_dopings(spec)
        doping_scale = float(value(spec, "sj_pillar_doping_scale"))
        pitch = float(value(spec, "pillar_pitch"))
        p_width = float(value(spec, "p_pillar_width"))
        drain_setback = float(value(spec, "p_pillar_drain_setback"))
        drift = float(value(spec, "drift_thickness"))
        if donor <= 0 or acceptor <= donor:
            raise ValueError(f"{source.name}: P pillar must remain net acceptor doped")
        if not 0 < doping_scale <= 2:
            raise ValueError(f"{source.name}: SJ pillar doping scale must be in (0, 2]")
        if not 0 < p_width < pitch:
            raise ValueError(f"{source.name}: P-pillar width must be inside one pitch")
        if not 0 <= drain_setback < drift:
            raise ValueError(f"{source.name}: P-pillar drain setback must remain inside the drift region")


def sdevice_parameter_deck(spec: dict) -> tuple[str, Path]:
    source = PARAMETER_SEEDS[spec["device_family"]]
    text = source.read_text(encoding="utf-8")
    if spec["device_family"] == "MOSFET":
        return text, source
    lifetime = float(value(spec, "minority_carrier_lifetime"))
    pattern = re.compile(r"(?m)^(\s*taumax\s*=\s*)[0-9.eE+-]+\s*,\s*[0-9.eE+-]+(\s*# \[s\]\s*)$")

    def replacement(match: re.Match[str]) -> str:
        return f"{match.group(1)}{lifetime:.4e} ,\t{lifetime:.4e}{match.group(2)}"

    rendered, count = pattern.subn(replacement, text)
    if count != 1:
        raise ValueError(f"{source}: expected exactly one Scharfetter taumax line, found {count}")
    return rendered, source


def mesh_profile(spec: dict, variant: str) -> dict[str, Any]:
    contract = spec["mesh_consistency_contract"]
    if contract.get("schema_version") != "650v_static_mesh_contract/v1":
        raise ValueError(f"{spec['device_family']}: unsupported mesh consistency contract")
    profiles = contract.get("profiles", {})
    if variant not in profiles:
        raise ValueError(f"{spec['device_family']}: unknown mesh variant {variant}")
    profile = profiles[variant]
    required = {"global_size_um", "active_size_um", "offset_maxlevel", "interface_hlocal_um", "interface_factor"}
    if set(profile) != required:
        raise ValueError(f"{spec['device_family']}:{variant}: invalid mesh profile fields")
    for name in ("global_size_um", "active_size_um"):
        sizes = profile[name]
        if not isinstance(sizes, list) or len(sizes) != 4 or any(float(item) <= 0 for item in sizes):
            raise ValueError(f"{spec['device_family']}:{variant}: {name} must contain four positive sizes")
    if int(profile["offset_maxlevel"]) < 1 or float(profile["interface_hlocal_um"]) <= 0 or float(profile["interface_factor"]) <= 1:
        raise ValueError(f"{spec['device_family']}:{variant}: invalid interface refinement controls")
    return profile


def sde_deck(spec: dict, mesh_variant: str = "baseline") -> str:
    profile = mesh_profile(spec, mesh_variant)
    global_max_x, global_max_y, global_min_x, global_min_y = profile["global_size_um"]
    active_max_x, active_max_y, active_min_x, active_min_y = profile["active_size_um"]
    offset_maxlevel = int(profile["offset_maxlevel"])
    interface_hlocal = float(profile["interface_hlocal_um"])
    interface_factor = float(profile["interface_factor"])
    mesh_suffix = "" if mesh_variant == "baseline" else f"_{mesh_variant}"
    drift = value(spec, "drift_thickness")
    family = spec["device_family"]
    body_implant_y_start = value(spec, "body_implant_y_start")
    body_implant_y_end = value(spec, "body_implant_y_end")
    source_implant_y_end = value(spec, "source_implant_y_end")
    gate_corner_radius = value(spec, "gate_corner_radius")
    gate_oxide_thickness = float(value(spec, "gate_oxide_thickness"))
    oxide_left_lower_y = 2.0 - gate_oxide_thickness
    oxide_tip_lower_y = 2.1 - gate_oxide_thickness
    oxide_tip_x = 3.13 + gate_oxide_thickness
    oxide_tip_upper_y = 2.7 + gate_oxide_thickness
    oxide_left_upper_y = 2.8 + gate_oxide_thickness
    body_implant_depth = value(spec, "body_implant_depth")
    body_peak_acceptor = value(spec, "body_peak_acceptor_concentration")
    high = "Collector" if family == "IGBT" else "Drain"
    low = "Emitter" if family == "IGBT" else "Source"
    bottom = "BoronActiveConcentration" if family == "IGBT" else "ArsenicActiveConcentration"
    bottom_peak = "5.0e19"
    if family == "IGBT":
        drift_doping = value(spec, "drift_donor_concentration")
    else:
        drift_doping, pillar_doping = mosfet_pillar_dopings(spec)
    pillar = ""
    if family == "MOSFET":
        pillar_start_y = value(spec, "pillar_pitch") / 2.0
        pillar_end_y = pillar_start_y + value(spec, "p_pillar_width")
        pillar_end_x = drift - value(spec, "p_pillar_drain_setback")
        pillar = f'''\n(sdedr:define-refeval-window "RW.PPillar" "Rectangle" (position 0 {pillar_start_y} 0) (position {pillar_end_x} {pillar_end_y} 0))
(sdedr:define-constant-profile "P.Pillar" "BoronActiveConcentration" {pillar_doping})
(sdedr:define-constant-profile-placement "P.Pillar.Place" "P.Pillar" "RW.PPillar")
'''
    field_stop = ""
    if family == "IGBT":
        field_stop_thickness = value(spec, "field_stop_thickness")
        field_stop_doping = value(spec, "field_stop_donor_concentration")
        field_stop = f'''\n(sdedr:define-refeval-window "BL.FieldStop" "Line" (position {drift} 0 0) (position {drift} 6 0))
(sdedr:define-gaussian-profile "P.FieldStop" "ArsenicActiveConcentration" "PeakPos" 0 "PeakVal" {field_stop_doping} "ValueAtDepth" {drift_doping} "Depth" {field_stop_thickness} "Erf" "Length" 0.1)
(sdedr:define-analytical-profile-placement "P.FieldStop.Place" "P.FieldStop" "BL.FieldStop" "Positive" "NoReplace" "Eval")
'''
    metrics = derived_metrics(spec)
    audit_note = (
        f"; gate_oxide_thickness_um={gate_oxide_thickness:.9f} "
        f"body_peak_acceptor_cm-3={float(body_peak_acceptor):.9e}"
    )
    if metrics:
        audit_note += (
            f" sj_charge_balance_ratio={metrics['sj_charge_balance_ratio']:.9f} "
            f"pillar_doping_scale={metrics['sj_pillar_doping_scale']:.9f} "
            f"effective_nd_cm-3={metrics['sj_effective_n_pillar_donor_concentration_cm3']:.9e} "
            f"effective_na_cm-3={metrics['sj_effective_p_pillar_acceptor_concentration_cm3']:.9e} "
            f"net_pillar_acceptor_cm-3={metrics['sj_net_pillar_acceptor_concentration_cm3']:.9e} "
            f"pillar_end_x_um={metrics['sj_pillar_end_x_um']:.9f}"
        )
    return f'''; generated independent 650 V {family} reference model; seed assumptions are not datasheet facts
; mesh_variant={mesh_variant}; only mesh controls differ between baseline and refined contracts
{audit_note}
(sde:clear)
(sdegeo:set-default-boolean "BAB")
(define xmax {drift})
(define ymax 6.0)
(sdegeo:create-polygon (list (position 0 2.0 0) (position 3.13 2.1 0) (position 3.13 2.7 0) (position 0 2.8 0) (position 0 2.0 0)) "PolySi" "R.PolyGate")
(sdegeo:fillet-2d (find-vertex-id (position 3.13 2.1 0)) {gate_corner_radius})
(sdegeo:fillet-2d (find-vertex-id (position 3.13 2.7 0)) {gate_corner_radius})
(sdegeo:create-polygon (list (position 0 {oxide_left_lower_y} 0) (position {oxide_tip_x} {oxide_tip_lower_y} 0) (position {oxide_tip_x} {oxide_tip_upper_y} 0) (position 0 {oxide_left_upper_y} 0) (position 0 {oxide_left_lower_y} 0)) "Oxide" "R.Gox")
(sdegeo:fillet-2d (find-vertex-id (position {oxide_tip_x} {oxide_tip_lower_y} 0)) {gate_corner_radius})
(sdegeo:fillet-2d (find-vertex-id (position {oxide_tip_x} {oxide_tip_upper_y} 0)) {gate_corner_radius})
(sdegeo:create-rectangle (position 0 0 0) (position xmax ymax 0) "Silicon" "R.Si")
(sdegeo:define-contact-set "{low}" 4 (color:rgb 1 0 0) "##")
(sdegeo:define-contact-set "{high}" 4 (color:rgb 0 0 1) "##")
(sdegeo:define-contact-set "Gate" 4 (color:rgb 0 1 0) "##")
(sdegeo:insert-vertex (position 0 3.0 0))
(sdegeo:insert-vertex (position 0 4.2 0))
(sdegeo:insert-vertex (position 0 5.2 0))
(sdegeo:define-2d-contact (find-edge-id (position 0 3.7 0)) "{low}")
(sdegeo:define-2d-contact (find-edge-id (position 0 4.6 0)) "{low}")
(sdegeo:define-2d-contact (find-edge-id (position xmax 4.2 0)) "{high}")
(sdegeo:define-2d-contact (find-edge-id (position 0 2.4 0)) "Gate")
(sdedr:define-constant-profile "P.Drift" "PhosphorusActiveConcentration" {drift_doping})
(sdedr:define-constant-profile-material "P.Drift.Place" "P.Drift" "Silicon")
(sdedr:define-constant-profile "P.Poly" "PhosphorusActiveConcentration" 1e21)
(sdedr:define-constant-profile-material "P.Poly.Place" "P.Poly" "PolySi")
(sdedr:define-refeval-window "BL.PBody" "Line" (position 0 {body_implant_y_start} 0) (position 0 {body_implant_y_end} 0))
(sdedr:define-gaussian-profile "P.PBody" "BoronActiveConcentration" "PeakPos" 0 "PeakVal" {body_peak_acceptor} "ValueAtDepth" {drift_doping} "Depth" {body_implant_depth} "Erf" "Length" 0.1)
(sdedr:define-analytical-profile-placement "P.PBody.Place" "P.PBody" "BL.PBody" "Negative" "NoReplace" "Eval")
(sdedr:define-refeval-window "BL.NPlus" "Line" (position 0 3.2 0) (position 0 {source_implant_y_end} 0))
(sdedr:define-gaussian-profile "P.NPlus" "ArsenicActiveConcentration" "PeakPos" 0 "PeakVal" 7e19 "ValueAtDepth" 1e17 "Depth" 0.6 "Erf" "Length" 0.1)
(sdedr:define-analytical-profile-placement "P.NPlus.Place" "P.NPlus" "BL.NPlus" "Negative" "NoReplace" "Eval")
(sdedr:define-refeval-window "BL.Bottom" "Line" (position xmax 0 0) (position xmax ymax 0))
(sdedr:define-gaussian-profile "P.Bottom" "{bottom}" "PeakPos" 0 "PeakVal" {bottom_peak} "ValueAtDepth" {drift_doping} "Depth" 0.7 "Erf" "Length" 0.1)
(sdedr:define-analytical-profile-placement "P.Bottom.Place" "P.Bottom" "BL.Bottom" "Positive" "NoReplace" "Eval")
{field_stop}{pillar}
(sdedr:define-refeval-window "RW.Global" "Rectangle" (position 0 0 0) (position xmax ymax 0))
(sdedr:define-refinement-size "Ref.Global" {global_max_x} {global_max_y} {global_min_x} {global_min_y})
(sdedr:define-refinement-placement "Ref.Global.Place" "Ref.Global" "RW.Global")
(sdedr:define-refinement-function "Ref.Global" "DopingConcentration" "MaxTransDiff" 1)
(sdedr:define-refeval-window "RW.Active" "Rectangle" (position 0 0 0) (position 5.0 ymax 0))
(sdedr:define-refinement-size "Ref.Active" {active_max_x} {active_max_y} {active_min_x} {active_min_y})
(sdedr:define-refinement-placement "Ref.Active.Place" "Ref.Active" "RW.Active")
(sdedr:define-refinement-function "Ref.Active" "DopingConcentration" "MaxTransDiff" 1)
(sdedr:offset-block "material" "Silicon" "maxlevel" {offset_maxlevel})
(sdedr:offset-interface "region" "R.Si" "R.Gox" "hlocal" {interface_hlocal} "factor" {interface_factor})
(sdeio:save-tdr-bnd (get-body-list) "{family.lower()}_650v{mesh_suffix}_bnd.tdr")
(sdedr:write-cmd-file "{family.lower()}_650v{mesh_suffix}_msh.cmd")
(system:command "snmesh -offset {family.lower()}_650v{mesh_suffix}_msh")
'''


def gate_electrode(spec: dict) -> str:
    contact = spec["gate_contact"]
    if contact["electrode_model"] == "barrier_offset":
        return f'{{ Name="Gate" Voltage=0 Barrier={float(contact["barrier_ev"]):.8g} }}'
    return f'{{ Name="Gate" Voltage=0 Material="{contact["material"]}"({contact["conductivity_type"]}) }}'


def interface_charge_physics(spec: dict) -> str:
    concentration = float(value(spec, "interface_fixed_charge_concentration"))
    return f'Physics(MaterialInterface="Silicon/Oxide") {{ Traps(FixedCharge Conc={concentration:.8g}) }}'


def static_mesh_name(spec: dict, mesh_variant: str) -> str:
    # Validate the requested variant against the device's immutable mesh contract.
    # This keeps later refinement levels explicit instead of treating every
    # non-baseline mesh as the historical v1 "refined" mesh.
    mesh_profile(spec, mesh_variant)
    suffix = "" if mesh_variant == "baseline" else f"_{mesh_variant}"
    return f"{spec['device_family'].lower()}_650v{suffix}_msh.tdr"


def static_bv_deck(spec: dict, mesh_variant: str = "baseline") -> str:
    family = spec["device_family"]
    stem = family.lower()
    grid = static_mesh_name(spec, mesh_variant)
    high = "Collector" if family == "IGBT" else "Drain"
    low = "Emitter" if family == "IGBT" else "Source"
    mobility = "DopingDep HighFieldSaturation" if family == "IGBT" else "DopingDep Enormal HighFieldSaturation"
    return f'''# generated static BV calibration; mesh_variant={mesh_variant}; 1e8 ohm-um series stabilization, inner-voltage electrical criterion
File {{
  Grid = "{grid}"
  Parameters = "sdevice.par"
  Current = "{stem}_bv.plt"
  Plot = "{stem}_bv"
  Output = "{stem}_bv.log"
}}
Electrode {{
  {{ Name="{low}" Voltage=0 }}
  {{ Name="{high}" Voltage=0 Resist=1e8 }}
  {gate_electrode(spec)}
}}
Physics {{ Temperature=300 EffectiveIntrinsicDensity(OldSlotboom) }}
Physics(Material="Silicon") {{
  Mobility({mobility})
  Recombination(SRH(DopingDependence TempDependence) Auger Avalanche(GradQuasiFermi))
}}
{interface_charge_physics(spec)}
Plot {{ ElectricField/Vector eDensity hDensity TotalCurrent/Vector ImpactIonization eImpactIonization hImpactIonization }}
Math {{
  Extrapolate RelErrControl Digits=5 Iterations=35 NotDamped=80
  ErrRef(Electron)=1e10 ErrRef(Hole)=1e10
  AvalDensGradQF ElementVolumeAvalanche AvalFlatElementExclusion=1.0 ExitOnFailure
}}
Solve {{
  Poisson
  Coupled(Iterations=100 LineSearchDamping=1e-4) {{ Poisson Electron }}
  Coupled(Iterations=100 LineSearchDamping=1e-4) {{ Poisson Electron Hole }}
  Quasistationary(InitialStep=1e-5 Increment=1.3 MaxStep=0.005 MinStep=1e-8
    Goal {{ Name="{high}" Voltage=1200 }}
    BreakCriteria {{ Current(Contact="{high}" AbsVal=1e-6) }}
  ) {{ Coupled {{ Poisson Electron Hole }} }}
}}
'''


def static_terminals(spec: dict) -> tuple[str, str]:
    if spec["device_family"] == "IGBT":
        return "Collector", "Emitter"
    return "Drain", "Source"


def static_channel_mobility(spec: dict) -> str:
    if spec["device_family"] == "IGBT":
        return "PhuMob Enormal HighFieldSaturation(EparallelToInterface)"
    return "DopingDependence Enormal HighFieldSaturation"


def static_initial_solve() -> str:
    return '''  Poisson
  Coupled(Iterations=100 LineSearchDamping=1e-4) { Poisson Electron }
  Coupled(Iterations=100 LineSearchDamping=1e-4) { Poisson Electron Hole }
'''


def static_vth_deck(spec: dict, mesh_variant: str = "baseline") -> str:
    family = spec["device_family"]
    stem = family.lower()
    grid = static_mesh_name(spec, mesh_variant)
    high, low = static_terminals(spec)
    temperature = float(spec["static_targets"]["temperature_k"])
    sweep_voltage = float(spec["static_targets"]["vth"]["max_v"]) + 2.0
    return f'''# generated static Vth calibration; mesh_variant={mesh_variant}; high-terminal and gate ramps are synchronous
File {{
  Grid = "{grid}"
  Parameters = "sdevice.par"
  Current = "{stem}_vth.plt"
  Output = "{stem}_vth.log"
}}
Electrode {{
  {{ Name="{low}" Voltage=0 }}
  {{ Name="{high}" Voltage=0 }}
  {gate_electrode(spec)}
}}
Physics {{ Temperature={temperature:.8g} EffectiveIntrinsicDensity(OldSlotboom) }}
Physics(Material="Silicon") {{
  Mobility({static_channel_mobility(spec)})
  Recombination(SRH(DopingDependence TempDependence) Auger)
}}
{interface_charge_physics(spec)}
Math {{
  Extrapolate RelErrControl Digits=5 Iterations=35 NotDamped=80
  ErrRef(Electron)=1e10 ErrRef(Hole)=1e10
}}
Solve {{
{static_initial_solve()}  NewCurrentPrefix="Vth_"
  Quasistationary(
    InitialStep=1e-3 Increment=1.35 MaxStep=0.01 MinStep=1e-8
    Goal {{ Name="{high}" Voltage={sweep_voltage:.8g} }}
    Goal {{ Name="Gate" Voltage={sweep_voltage:.8g} }}
  ) {{
    Coupled {{ Poisson Electron Hole }}
    CurrentPlot(Time=(Range=(0 1) Intervals=100))
  }}
}}
'''


def static_conduction_deck(spec: dict, mesh_variant: str = "baseline") -> str:
    family = spec["device_family"]
    stem = family.lower()
    grid = static_mesh_name(spec, mesh_variant)
    high, low = static_terminals(spec)
    targets = spec["static_targets"]["conduction"]
    temperature = float(spec["static_targets"]["temperature_k"])
    gate_voltage = float(targets["gate_voltage_v"])
    if family == "IGBT":
        output_voltage = 2.0 * float(targets["max_voltage_v"])
    else:
        output_voltage = max(1.5, 1.5 * float(targets["current_a"]) * float(targets["max_resistance_ohm"]))
    return f'''# generated static on-state calibration; mesh_variant={mesh_variant}; output remains raw 2D current in A/um
File {{
  Grid = "{grid}"
  Parameters = "sdevice.par"
  Current = "{stem}_conduction.plt"
  Output = "{stem}_conduction.log"
}}
Electrode {{
  {{ Name="{low}" Voltage=0 }}
  {{ Name="{high}" Voltage=0 }}
  {gate_electrode(spec)}
}}
Physics {{ Temperature={temperature:.8g} EffectiveIntrinsicDensity(OldSlotboom) }}
Physics(Material="Silicon") {{
  Mobility({static_channel_mobility(spec)})
  Recombination(SRH(DopingDependence TempDependence) Auger)
}}
{interface_charge_physics(spec)}
Math {{
  Extrapolate RelErrControl Digits=5 Iterations=35 NotDamped=80
  ErrRef(Electron)=1e10 ErrRef(Hole)=1e10
}}
Solve {{
{static_initial_solve()}  Quasistationary(
    InitialStep=1e-3 Increment=1.35 MaxStep=0.05 MinStep=1e-8
    Goal {{ Name="Gate" Voltage={gate_voltage:.8g} }}
  ) {{ Coupled {{ Poisson Electron Hole }} }}
  NewCurrentPrefix="Conduction_"
  Quasistationary(
    InitialStep=1e-4 Increment=1.3 MaxStep=0.01 MinStep=1e-9
    Goal {{ Name="{high}" Voltage={output_voltage:.8g} }}
  ) {{
    Coupled {{ Poisson Electron Hole }}
    CurrentPlot(Time=(Range=(0 1) Intervals=120))
  }}
}}
'''


def static_off_leakage_deck(spec: dict, mesh_variant: str = "baseline") -> str:
    family = spec["device_family"]
    stem = family.lower()
    grid = static_mesh_name(spec, mesh_variant)
    high, low = static_terminals(spec)
    temperature = float(spec["static_targets"]["temperature_k"])
    blocking_voltage = float(spec["static_targets"]["off_leakage"]["blocking_voltage_v"])
    mobility = "DopingDep HighFieldSaturation" if family == "IGBT" else "DopingDep Enormal HighFieldSaturation"
    return f'''# generated 650 V off-state leakage test; mesh_variant={mesh_variant}; no solver-failure BV inference
File {{
  Grid = "{grid}"
  Parameters = "sdevice.par"
  Current = "{stem}_off_leakage.plt"
  Output = "{stem}_off_leakage.log"
}}
Electrode {{
  {{ Name="{low}" Voltage=0 }}
  {{ Name="{high}" Voltage=0 }}
  {gate_electrode(spec)}
}}
Physics {{ Temperature={temperature:.8g} EffectiveIntrinsicDensity(OldSlotboom) }}
Physics(Material="Silicon") {{
  Mobility({mobility})
  Recombination(SRH(DopingDependence TempDependence) Auger Avalanche(GradQuasiFermi))
}}
{interface_charge_physics(spec)}
Math {{
  Extrapolate RelErrControl Digits=5 Iterations=35 NotDamped=80
  ErrRef(Electron)=1e10 ErrRef(Hole)=1e10
  AvalDensGradQF ElementVolumeAvalanche AvalFlatElementExclusion=1.0 ExitOnFailure
}}
Solve {{
{static_initial_solve()}  NewCurrentPrefix="OffLeakage_"
  Quasistationary(
    InitialStep=1e-5 Increment=1.3 MaxStep=0.005 MinStep=1e-8
    Goal {{ Name="{high}" Voltage={blocking_voltage:.8g} }}
  ) {{
    Coupled {{ Poisson Electron Hole }}
    CurrentPlot(Time=(Range=(0 1) Intervals=200))
  }}
}}
'''


def static_case_decks(spec: dict, mesh_variant: str = "baseline") -> dict[str, str]:
    return {
        "vth": static_vth_deck(spec, mesh_variant),
        "conduction": static_conduction_deck(spec, mesh_variant),
        "off_leakage": static_off_leakage_deck(spec, mesh_variant),
    }


def static_metadata(spec: dict, test_kind: str, mesh_variant: str = "baseline") -> dict:
    family = spec["device_family"]
    high, low = static_terminals(spec)
    targets = spec["static_targets"]
    target_high_voltage = {
        "BV": 1200.0,
        "vth": float(targets["vth"]["max_v"]) + 2.0,
        "conduction": (
            2.0 * float(targets["conduction"]["max_voltage_v"])
            if family == "IGBT"
            else max(
                1.5,
                1.5 * float(targets["conduction"]["current_a"]) * float(targets["conduction"]["max_resistance_ohm"]),
            )
        ),
        "off_leakage": float(targets["off_leakage"]["blocking_voltage_v"]),
    }[test_kind]
    test_contract = {
        "BV": {
            "criterion": spec["static_gates"]["bv_criterion"],
            "series_resistance_ohm_um": 1.0e8,
            "voltage_extraction": "high-terminal InnerVoltage at first raw current sample meeting criterion",
        },
        "vth": targets["vth"],
        "conduction": targets["conduction"],
        "off_leakage": targets["off_leakage"],
    }[test_kind]
    return {
        "campaign_id": "igbt_mosfet_650v_seb_20260715",
        "publication_profile": spec["publication_profile"],
        "structure_id": spec["structure_id"],
        "device_family": family,
        "test_kind": test_kind,
        "gate_contact": spec["gate_contact"],
        "datasheet_test_contract": test_contract,
        "high_terminal_name": high,
        "low_terminal_name": low,
        "bias_quantity": "VCE" if family == "IGBT" else "VDS",
        "target_blocking_voltage_v": target_high_voltage,
        "actual_blocking_voltage_v": None,
        "target_vce_v": target_high_voltage,
        "actual_vce_v": None,
        "rated_voltage_v": 650,
        "bv_static_v": None,
        "bv_criterion": spec["static_gates"]["bv_criterion"],
        "derating_basis": "static calibration against the public datasheet test contract",
        "raw_current_unit": "A/um",
        "interface_fixed_charge_cm2": value(spec, "interface_fixed_charge_concentration"),
        "area_factor": None,
        "area_factor_status": "PENDING_CONDUCTION_EXTRACTION",
        "parent_restart_ids": [],
        "parent_restart_hashes": [],
        "termination_reason": "BV_CURRENT_CRITERION" if test_kind == "BV" else "PENDING_STATIC_EXTRACTION",
        "let_mev_cm2_mg": 0,
        "mesh_variant": mesh_variant,
        "t_init_k": targets["temperature_k"] if test_kind != "BV" else 300,
        "t_steady_k": targets["temperature_k"] if test_kind != "BV" else 300,
        "t_steady_max_k": targets["temperature_k"] if test_kind != "BV" else 300,
    }


def sdevice_deck(spec: dict, bias: int, phase: str, mesh_leaf: str = "mesh.tdr") -> str:
    family = spec["device_family"]
    high = "Collector" if family == "IGBT" else "Drain"
    low = "Emitter" if family == "IGBT" else "Source"
    x = float(value(spec, "track_x"))
    y = float(value(spec, "track_y"))
    length = float(value(spec, "track_length"))
    direction = value(spec, "track_direction") if "track_direction" in spec["parameters"] else [0.0, 1.0]
    dx, dy = (float(direction[0]), float(direction[1]))
    case_id = f"{family}650_V{bias}"
    phase_name = "transient" if phase == "transient" else "dc_restart"
    restart_prefix = f"{case_id}_restart"
    plot_prefix = f"{case_id}_{'tr_at2p1ns' if phase == 'transient' else 'dc_pre'}"
    mobility = "DopingDep HighFieldSaturation" if family == "IGBT" else "DopingDep Enormal HighFieldSaturation"
    ion = ""
    heavy_plot = ""
    break_criteria = ""
    if phase == "transient":
        ion = (
            f"\n  HeavyIon(StartPoint=({x:.8g} {y:.8g}) Direction=({dx:.8g} {dy:.8g}) "
            f"Length={length:.8g} Time=1e-10 LET_f={REFERENCE_LET_F_PC_UM:.8g} "
            f"Wt_hi={REFERENCE_WT_HI_UM:.8g} Gaussian PicoCoulomb)"
        )
        heavy_plot = "\n  HeavyIonGeneration HeavyIonChargeDensity"
        break_criteria = " BreakCriteria { LatticeTemperature(MaxVal=2500) }"
    return f'''# generated; {spec["structure_id"]}; {phase_name}; no SEB threshold claim
File {{
  Grid="{mesh_leaf}" Parameters="sdevice.par"
  Plot="{case_id}_{phase_name}" Current="{case_id}_{phase_name}.plt" Output="{case_id}_{phase_name}.log"
}}
Electrode {{ {gate_electrode(spec)} {{ Name="{low}" Voltage=0 }} {{ Name="{high}" Voltage=0 }} }}
Thermode {{ {{ Name="Gate" Temperature=298.15 }} {{ Name="{low}" Temperature=298.15 }} {{ Name="{high}" Temperature=298.15 }} }}
Physics {{
  Temperature=298.15 Thermodynamic
  Mobility({mobility})
  Recombination(SRH(DopingDependence TempDependence) Auger Avalanche(Lackner)){ion}
}}
{interface_charge_physics(spec)}
Plot {{
  eDensity hDensity TotalCurrent/Vector ElectricField/Vector Potential SpaceCharge
  Temperature JouleHeat TotalHeat AvalancheGeneration eAvalancheGeneration hAvalancheGeneration{heavy_plot}
  Doping DonorConcentration AcceptorConcentration
}}
Math {{ Extrapolate Transient=BE Iterations=30 Notdamped=50 Digits=5 ErrRef(Electron)=1e10 ErrRef(Hole)=1e10 ExitOnFailure{break_criteria} }}
Solve {{
'''+ (
        f'''  Load(FilePrefix="{restart_prefix}")
  Plot(FilePrefix="{case_id}_tr_pre" NoOverwrite)
  NewCurrentPrefix="{case_id}_tr_transient_"
  Transient(InitialTime=0 FinalTime=9.2e-11 InitialStep=1e-13 Increment=1.4 Decrement=2 MaxStep=1e-11 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_092ps" NoOverwrite)
  Transient(InitialTime=9.2e-11 FinalTime=9.4e-11 InitialStep=1e-12 Increment=1.4 Decrement=2 MaxStep=1e-12 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_094ps" NoOverwrite)
  Transient(InitialTime=9.4e-11 FinalTime=9.6e-11 InitialStep=1e-12 Increment=1.4 Decrement=2 MaxStep=1e-12 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_096ps" NoOverwrite)
  Transient(InitialTime=9.6e-11 FinalTime=9.7e-11 InitialStep=1e-12 Increment=1.4 Decrement=2 MaxStep=1e-12 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_097ps" NoOverwrite)
  Transient(InitialTime=9.7e-11 FinalTime=9.8e-11 InitialStep=2e-13 Increment=1.0 Decrement=2 MaxStep=2e-13 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_098ps" NoOverwrite)
  Transient(InitialTime=9.8e-11 FinalTime=9.9e-11 InitialStep=2e-13 Increment=1.0 Decrement=2 MaxStep=2e-13 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_099ps" NoOverwrite)
  Transient(InitialTime=9.9e-11 FinalTime=9.95e-11 InitialStep=2e-13 Increment=1.0 Decrement=2 MaxStep=2e-13 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_099p5ps" NoOverwrite)
  Transient(InitialTime=9.95e-11 FinalTime=1e-10 InitialStep=2e-13 Increment=1.0 Decrement=2 MaxStep=2e-13 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_100ps" NoOverwrite)
  Transient(InitialTime=1e-10 FinalTime=1.002e-10 InitialStep=2e-13 Increment=1.0 Decrement=2 MaxStep=2e-13 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_100p2ps" NoOverwrite)
  Transient(InitialTime=1.002e-10 FinalTime=1.005e-10 InitialStep=2e-13 Increment=1.0 Decrement=2 MaxStep=2e-13 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_100p5ps" NoOverwrite)
  Transient(InitialTime=1.005e-10 FinalTime=1.01e-10 InitialStep=2e-13 Increment=1.0 Decrement=2 MaxStep=2e-13 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_101ps" NoOverwrite)
  Transient(InitialTime=1.01e-10 FinalTime=1.02e-10 InitialStep=2e-13 Increment=1.0 Decrement=2 MaxStep=2e-13 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_102ps" NoOverwrite)
  Transient(InitialTime=1.02e-10 FinalTime=1.03e-10 InitialStep=1e-12 Increment=1.4 Decrement=2 MaxStep=1e-12 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_103ps" NoOverwrite)
  Transient(InitialTime=1.03e-10 FinalTime=1.04e-10 InitialStep=1e-12 Increment=1.4 Decrement=2 MaxStep=1e-12 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_104ps" NoOverwrite)
  Transient(InitialTime=1.04e-10 FinalTime=1.06e-10 InitialStep=1e-12 Increment=1.4 Decrement=2 MaxStep=1e-12 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_106ps" NoOverwrite)
  Transient(InitialTime=1.06e-10 FinalTime=1.08e-10 InitialStep=1e-12 Increment=1.4 Decrement=2 MaxStep=1e-12 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{case_id}_tr_audit_108ps" NoOverwrite)
  Transient(InitialTime=1.08e-10 FinalTime=2.1e-9 InitialStep=2e-13 Increment=1.4 Decrement=2 MaxStep=2e-11 MinStep=1e-17) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{plot_prefix}" NoOverwrite)
'''
        if phase == "transient"
        else f'''  Poisson
  Coupled(Iterations=100 LineSearchDamping=1e-4) {{ Poisson Electron }}
  Coupled(Iterations=100 LineSearchDamping=1e-4) {{ Poisson Electron Hole }}
  Quasistationary(InitialStep=1e-5 Increment=1.3 MaxStep=0.005 MinStep=1e-8 Goal {{ Name="{high}" Voltage={bias} }}) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Save(FilePrefix="{restart_prefix}")
  Plot(FilePrefix="{plot_prefix}" NoOverwrite)
'''
    ) + "}\n"


def case_metadata(spec: dict, bias: int, phase: str) -> dict:
    family = spec["device_family"]
    high = "Collector" if family == "IGBT" else "Drain"
    case_id = f"{family}650_V{bias}"
    return {
        "campaign_id": "igbt_mosfet_650v_seb_20260715",
        "publication_profile": spec["publication_profile"],
        "structure_id": spec["structure_id"],
        "device_family": spec["device_family"],
        "high_terminal_name": high,
        "bias_quantity": "VCE" if spec["device_family"] == "IGBT" else "VDS",
        "target_blocking_voltage_v": bias,
        "actual_blocking_voltage_v": None,
        "target_vce_v": bias,
        "actual_vce_v": None,
        "rated_voltage_v": 650,
        "bv_static_v": None,
        "bv_criterion": spec["static_gates"]["bv_criterion"],
        "derating_basis": {"325": "230 Vrms rectified peak", "400": "common PFC bus reference", "500": "~77% rating high-stress extension, not common continuous bus"}[str(bias)],
        "parent_restart_ids": [],
        "parent_restart_hashes": [],
        "termination_reason": "PENDING_STATIC_GATE" if phase == "transient" else "PENDING_RUN",
        "let_mev_cm2_mg": REFERENCE_LET_MEV_CM2_MG if phase == "transient" else 0,
        "let_f_pc_um": REFERENCE_LET_F_PC_UM if phase == "transient" else None,
        "wt_hi_um": REFERENCE_WT_HI_UM if phase == "transient" else None,
        "track_x_um": value(spec, "track_x"), "track_y_um": value(spec, "track_y"),
        "direction": value(spec, "track_direction") if "track_direction" in spec["parameters"] else [0.0, 1.0],
        "length_um": value(spec, "track_length"), "drift_thickness_um": value(spec, "drift_thickness"),
        "restart_prefix": f"{case_id}_restart",
        "prestrike_tdr": f"{case_id}_tr_pre_des.tdr" if phase == "transient" else None,
        "heavy_ion_audit_tdrs": {
            f"{time_s:.12g}": f"{case_id}_tr_audit_{suffix}_des.tdr"
            for suffix, time_s in REFERENCE_AUDIT_POINTS
        } if phase == "transient" else {},
        "exact_2p1ns_tdr": f"{case_id}_tr_at2p1ns_des.tdr" if phase == "transient" else None,
        "mesh_variant": "AUTHORIZED_VERIFIED_MESH", "strike_time_s": 1e-10 if phase == "transient" else None,
        "total_time_s": 2.1e-9 if phase == "transient" else None
    }


def _bound_file_matches(record: dict[str, Any]) -> bool:
    try:
        path = ROOT / str(record["path"])
        return path.is_file() and sha(path) == record["sha256"] and path.stat().st_size == int(record["size_bytes"])
    except (KeyError, TypeError, ValueError, OSError):
        return False


def _scheduler_closed(record: dict[str, Any]) -> bool:
    scheduling = record.get("scheduling_evidence", {})
    return bool(
        scheduling.get("allocation_mode") == "AUTO_LEASE"
        and scheduling.get("sdevice_threads") == 1
        and scheduling.get("lease_acquired") is True
        and scheduling.get("lease_released") is True
        and scheduling.get("affinity_verification") == "VERIFIED"
        and str(scheduling.get("exit_code")) == "0"
    )


def post_static_gate_ready(spec: dict) -> bool:
    required = ("bv", "vth", "conduction", "off_leakage", "mesh_consistency")
    gates = spec["static_gates"]
    if not all(gates.get(name) == "PASSED" for name in required) or gates.get("heavy_ion_authorized") is not True:
        return False
    if gates.get("authorization_evidence") != str(AUTHORIZATION_EVIDENCE.relative_to(ROOT)).replace("\\", "/"):
        return False
    if not AUTHORIZATION_EVIDENCE.is_file():
        return False
    try:
        authorization = read_json(AUTHORIZATION_EVIDENCE)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not (
        authorization.get("schema_version") == "650v_heavy_ion_authorization/v1"
        and authorization.get("campaign_id") == "igbt_mosfet_650v_seb_20260715"
        and authorization.get("status") == "AUTHORIZED"
        and authorization.get("heavy_ion_authorized") is True
        and authorization.get("reference_model_only") is True
        and authorization.get("five_gate_policy") == list(required)
    ):
        return False
    family = spec["device_family"]
    device = authorization.get("devices", {}).get(family, {})
    dsl_record = device.get("dsl", {})
    dsl_path = PROJECT / "devices" / ("igbt_650v.json" if family == "IGBT" else "mosfet_650v_sj.json")
    if not _bound_file_matches(dsl_record) or dsl_record.get("path") != str(dsl_path.relative_to(ROOT)).replace("\\", "/"):
        return False
    if device.get("candidate_id") != spec["candidate_freeze"]["candidate_id"] or device.get("candidate_values") != spec["candidate_freeze"]["candidate_values"]:
        return False
    if device.get("five_gates") != {name: "PASSED" for name in required}:
        return False
    expected_track = {
        "track_x_um": float(value(spec, "track_x")),
        "track_y_um": float(value(spec, "track_y")),
        "direction": [float(item) for item in value(spec, "track_direction")],
        "length_um": float(value(spec, "track_length")),
    }
    if device.get("track") != expected_track or device.get("field_track", {}).get("status") != "VERIFIED_FROZEN_NOT_SEED":
        return False
    meshes = device.get("meshes", [])
    if not meshes or any(not _bound_file_matches(record) for record in meshes):
        return False
    if device["field_track"].get("mesh_sha256") != meshes[-1].get("sha256"):
        return False
    if not device.get("static_runs") or any(not _scheduler_closed(record) for record in device["static_runs"]):
        return False
    field_runs = [record for record in authorization.get("field_runs", []) if record.get("case_id", "").startswith(family)]
    if len(field_runs) != 3 or any(not _scheduler_closed(record) for record in field_runs):
        return False
    bound_files = authorization.get("bound_files", [])
    if not bound_files or any(not _bound_file_matches(record) for record in bound_files):
        return False
    return True


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/"),
        "sha256": sha(path),
        "size_bytes": path.stat().st_size,
    }


def _validated_restart_bindings(
    path: Path | None,
    authorization: dict[str, Any],
    authorization_sha256: str,
) -> dict[tuple[str, int], dict[str, Any]]:
    if path is None:
        return {}
    document = read_json(path)
    if not (
        document.get("schema_version") == "650v_restart_binding_set/v1"
        and document.get("authorization_sha256") == authorization_sha256
    ):
        raise ValueError("restart bindings do not match the exact authorization")
    records = document.get("records", [])
    expected_keys = {(family, bias) for family in ("IGBT", "MOSFET") for bias in BIASES}
    indexed: dict[tuple[str, int], dict[str, Any]] = {}
    for record in records:
        family = str(record.get("device_family"))
        bias = int(record.get("bias_v"))
        key = (family, bias)
        if key in indexed or key not in expected_keys:
            raise ValueError("restart bindings contain duplicate or unknown device/bias keys")
        manifest_record = record.get("run_manifest", {})
        gate_record = record.get("restart_gate", {})
        main_record = record.get("restart_main", {})
        circuit_record = record.get("restart_circuit", {})
        if not all(_bound_file_matches(item) for item in (manifest_record, gate_record, main_record, circuit_record)):
            raise ValueError(f"{family} {bias} V restart binding hash mismatch")
        manifest = read_json(ROOT / manifest_record["path"])
        gate = read_json(ROOT / gate_record["path"])
        expected_prefix = f"{family}650_V{bias}_restart"
        if not (
            manifest.get("run_id") == record.get("run_id")
            and gate.get("schema_version") == "650v_dc_restart_gate/v1"
            and gate.get("status") == "PASS"
            and gate.get("run_id") == record.get("run_id")
            and gate.get("run_manifest") == manifest_record
            and gate.get("restart_main") == main_record
            and gate.get("restart_circuit") == circuit_record
            and manifest.get("lifecycle") == "SUCCEEDED"
            and str(manifest.get("exit_code")) == "0"
            and manifest.get("sdevice_threads") == 1
            and _scheduler_closed(manifest)
            and math.isclose(float(record.get("actual_bias_v")), float(bias), rel_tol=0.0, abs_tol=1e-6)
            and math.isclose(float(gate.get("actual_bias_v")), float(bias), rel_tol=0.0, abs_tol=1e-6)
            and gate.get("mesh_sha256") == record.get("mesh_sha256")
            and Path(main_record["path"]).name == expected_prefix + "_des.sav"
            and Path(circuit_record["path"]).name == expected_prefix + "_circuit_des.sav"
            and record.get("mesh_sha256") == authorization["devices"][family]["meshes"][-1]["sha256"]
        ):
            raise ValueError(f"{family} {bias} V restart binding is not a successful exact-bias parent")
        indexed[key] = record
    if set(indexed) != expected_keys:
        raise ValueError("restart bindings must contain all six device/bias parents before transient rendering")
    return indexed


def render_post_static_cases(
    runtime: Path,
    specs: list[tuple[Path, dict]],
    restart_bindings_path: Path | None,
) -> None:
    authorization = read_json(AUTHORIZATION_EVIDENCE)
    authorization_sha256 = sha(AUTHORIZATION_EVIDENCE)
    restart_bindings = _validated_restart_bindings(
        restart_bindings_path,
        authorization,
        authorization_sha256,
    )
    suffix = f"authorization_{authorization_sha256[:16]}"
    if restart_bindings_path is not None:
        suffix += f"__restart_{sha(restart_bindings_path)[:16]}"
    output_root = runtime / "post_static_inputs" / suffix
    if output_root.exists():
        raise FileExistsError(f"refusing existing post-static render directory: {output_root}")

    records: list[dict[str, Any]] = []
    for source, spec in specs:
        family = spec["device_family"]
        family_record = authorization["devices"][family]
        if family_record["dsl"]["sha256"] != sha(source):
            raise ValueError(f"{family}: DSL changed after authorization")
        mesh_record = family_record["meshes"][-1]
        if not _bound_file_matches(mesh_record):
            raise ValueError(f"{family}: authorized mesh binding is invalid")
        mesh_path = ROOT / mesh_record["path"]
        family_dir = output_root / family.lower()
        parameter_text, parameter_source = sdevice_parameter_deck(spec)
        parameter_path = family_dir / "sdevice.par"
        put(parameter_path, parameter_text)
        for bias in BIASES:
            case_dir = family_dir / str(bias)
            dc_deck = case_dir / f"{family.lower()}_{bias}_dc_restart.cmd"
            dc_meta = case_dir / f"{family.lower()}_{bias}_dc_restart.json"
            put(dc_deck, sdevice_deck(spec, bias, "dc", mesh_path.name))
            metadata = case_metadata(spec, bias, "dc_restart")
            metadata.update({
                "phase": "dc_restart",
                "authorization_evidence": _file_record(AUTHORIZATION_EVIDENCE),
                "authorized_dsl": family_record["dsl"],
                "verified_mesh": mesh_record,
                "expected_restart_main_leaf": f"{family}650_V{bias}_restart_des.sav",
                "expected_restart_circuit_leaf": f"{family}650_V{bias}_restart_circuit_des.sav",
                "parent_restart_ids": [],
                "parent_restart_hashes": [],
                "termination_reason": "PENDING_DC_RESTART_RUN",
                "heavy_ion_authorized": True,
                "transient_rendered": False,
            })
            put(dc_meta, json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
            records.append({
                "device": family,
                "bias_v": bias,
                "phase": "dc_restart",
                "deck": _file_record(dc_deck),
                "metadata": _file_record(dc_meta),
                "parameter": _file_record(parameter_path),
                "parameter_source": _file_record(parameter_source),
                "mesh": mesh_record,
                "parent_restart": None,
            })
            if not restart_bindings:
                continue
            parent = restart_bindings[(family, bias)]
            transient_deck = case_dir / f"{family.lower()}_{bias}_let15_2p1ns.cmd"
            transient_meta = case_dir / f"{family.lower()}_{bias}_let15_2p1ns.json"
            put(transient_deck, sdevice_deck(spec, bias, "transient", mesh_path.name))
            transient_metadata = case_metadata(spec, bias, "transient")
            transient_metadata.update({
                "phase": "let15_2p1ns_reference_transient",
                "authorization_evidence": _file_record(AUTHORIZATION_EVIDENCE),
                "authorized_dsl": family_record["dsl"],
                "verified_mesh": mesh_record,
                "parent_restart_ids": [parent["run_id"]],
                "parent_restart_hashes": [parent["restart_main"]["sha256"], parent["restart_circuit"]["sha256"]],
                "parent_restart_main": parent["restart_main"],
                "parent_restart_circuit": parent["restart_circuit"],
                "parent_restart_actual_bias_v": parent["actual_bias_v"],
                "restart_binding_set": _file_record(restart_bindings_path),
                "termination_reason": "PENDING_LET15_2P1NS_RUN",
                "heavy_ion_authorized": True,
                "transient_rendered": True,
            })
            put(transient_meta, json.dumps(transient_metadata, ensure_ascii=False, indent=2) + "\n")
            records.append({
                "device": family,
                "bias_v": bias,
                "phase": "let15_2p1ns_reference_transient",
                "deck": _file_record(transient_deck),
                "metadata": _file_record(transient_meta),
                "parameter": _file_record(parameter_path),
                "mesh": mesh_record,
                "parent_restart": parent,
            })

    manifest = {
        "schema_version": "650v_post_static_render_manifest/v1",
        "authorization_evidence": _file_record(AUTHORIZATION_EVIDENCE),
        "restart_binding_set": _file_record(restart_bindings_path) if restart_bindings_path else None,
        "dc_restart_cases_rendered": True,
        "transient_cases_rendered": bool(restart_bindings),
        "transient_block_state": None if restart_bindings else "BLOCKED_UNTIL_ALL_SIX_EXACT_RESTART_BINDINGS_EXIST",
        "records": records,
    }
    manifest_path = output_root / "post_static_render_manifest.json"
    put(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(
        f"post_static_render={output_root} dc_cases=6 "
        f"transient_cases={6 if restart_bindings else 0} manifest={manifest_path}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--mesh-variant", default="baseline")
    parser.add_argument("--device-family", choices=("IGBT", "MOSFET"), help="render only one device family")
    parser.add_argument("--mesh-attempt-config", type=Path)
    parser.add_argument(
        "--include-post-static-cases",
        action="store_true",
        help="render hash-bound DC restart inputs after exact authorization; transient inputs require --restart-bindings",
    )
    parser.add_argument(
        "--restart-bindings",
        type=Path,
        help="exact six-parent restart binding set required before rendering any LET15 transient deck",
    )
    args = parser.parse_args()
    if args.mesh_attempt_config and args.mesh_variant != "baseline":
        raise ValueError("physical mesh attempts use the baseline mesh profile")
    if args.include_post_static_cases and args.mesh_variant != "baseline":
        raise ValueError("refined rendering is static-only and cannot render post-static cases")
    if args.restart_bindings and not args.include_post_static_cases:
        raise ValueError("--restart-bindings requires --include-post-static-cases")
    specs = [(path, read_json(path)) for path in DEVICE_FILES]
    if args.device_family:
        specs = [(path, spec) for path, spec in specs if spec["device_family"] == args.device_family]
    for source, spec in specs:
        validate(spec, source)
        sdevice_parameter_deck(spec)
    if args.include_post_static_cases:
        blocked = [spec["device_family"] for _, spec in specs if not post_static_gate_ready(spec)]
        if blocked:
            raise ValueError(f"post-static cases are blocked by static/mesh gates: {','.join(blocked)}")
    if args.validate_only:
        families = ",".join(spec["device_family"] for _, spec in specs)
        print(f"validated={len(specs)} devices={families} mesh_variant={args.mesh_variant}")
        return
    if args.include_post_static_cases:
        render_post_static_cases(args.runtime, specs, args.restart_bindings)
        return
    if args.mesh_attempt_config:
        attempt = read_json(args.mesh_attempt_config)
        required = {"attempt_id", "device_family", "parent_attempt_id", "single_variable_change", "hypothesis"}
        missing = required - attempt.keys()
        if missing:
            raise ValueError(f"mesh attempt config missing {sorted(missing)}")
        attempt_id = str(attempt["attempt_id"])
        if not attempt_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for character in attempt_id):
            raise ValueError("mesh attempt_id must be portable")
        matches = [(source, spec) for source, spec in specs if spec["device_family"] == attempt["device_family"]]
        if len(matches) != 1:
            raise ValueError("mesh attempt config has an unknown device_family")
        source, spec = matches[0]
        change = attempt["single_variable_change"]
        if set(change) != {"parameter", "old_value", "new_value"}:
            raise ValueError("single_variable_change must contain parameter, old_value, and new_value only")
        parameter = change["parameter"]
        if parameter not in spec["parameters"]:
            raise ValueError(f"unknown changed parameter: {parameter}")
        if change["old_value"] == change["new_value"]:
            raise ValueError("mesh attempt must change one physical value")
        if value(spec, parameter) != change["new_value"]:
            raise ValueError(f"DSL resolved value for {parameter} does not match attempt new_value")
        attempt_dir = args.runtime / "mesh_attempts" / attempt_id
        if attempt_dir.exists():
            raise FileExistsError(f"refusing existing mesh attempt directory: {attempt_dir}")
        deck = attempt_dir / f"{spec['device_family'].lower()}_650v_seed.scm"
        put(deck, sde_deck(spec, "baseline"))
        manifest = {
            "attempt_id": attempt_id,
            "status": "PREPARED",
            "parent_attempt_id": attempt["parent_attempt_id"],
            "single_variable_change": change,
            "hypothesis": attempt["hypothesis"],
            "device_dsl_path": str(source.relative_to(ROOT)).replace("\\", "/"),
            "device_dsl_sha256": sha(source),
            "generated_deck_sha256": sha(deck),
            "resolved_parameters": {name: value(spec, name) for name in spec["parameters"]},
            "derived_metrics": derived_metrics(spec),
            "result": "PENDING_SDE",
        }
        put(attempt_dir / "attempt_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        print(f"mesh_attempt={attempt_id} deck={deck}")
        return
    records = []
    mesh_variant = args.mesh_variant
    for source, spec in specs:
        stem = spec["device_family"].lower()
        generated_root = args.runtime / "generated"
        device_dir = generated_root / stem if mesh_variant == "baseline" else generated_root / mesh_variant / stem
        sde_name = f"{stem}_650v_seed.scm" if mesh_variant == "baseline" else f"{stem}_650v_{mesh_variant}.scm"
        sde = device_dir / sde_name
        put(sde, sde_deck(spec, mesh_variant))
        records.append({
            "device": spec["device_family"],
            "phase": "sde_mesh",
            "mesh_variant": mesh_variant,
            "mesh_profile": mesh_profile(spec, mesh_variant),
            "deck": str(sde.relative_to(args.runtime)).replace("\\", "/"),
            "deck_sha256": sha(sde),
        })
        calibration_root = args.runtime / "calibration_inputs" / stem
        calibration_dir = calibration_root if mesh_variant == "baseline" else calibration_root / mesh_variant
        parameter_text, parameter_source = sdevice_parameter_deck(spec)
        parameter_path = calibration_dir / "sdevice.par"
        put(parameter_path, parameter_text)
        records.append({
            "device": spec["device_family"],
            "phase": "sdevice_parameters",
            "mesh_variant": mesh_variant,
            "source": str(parameter_source.relative_to(ROOT)).replace("\\", "/"),
            "source_sha256": sha(parameter_source),
            "parameter": str(parameter_path.relative_to(args.runtime)).replace("\\", "/"),
            "parameter_sha256": sha(parameter_path),
        })
        bv_stem = f"{stem}_bv_seed" if mesh_variant == "baseline" else f"{stem}_bv_{mesh_variant}"
        bv_deck = calibration_dir / f"{bv_stem}.cmd"
        bv_meta = calibration_dir / f"{bv_stem}.json"
        put(bv_deck, static_bv_deck(spec, mesh_variant))
        put(bv_meta, json.dumps(static_metadata(spec, "BV", mesh_variant), ensure_ascii=False, indent=2) + "\n")
        records.append({
            "device": spec["device_family"],
            "phase": "static_bv",
            "mesh_variant": mesh_variant,
            "deck": str(bv_deck.relative_to(args.runtime)).replace("\\", "/"),
            "deck_sha256": sha(bv_deck),
            "parameter": str(parameter_path.relative_to(args.runtime)).replace("\\", "/"),
            "parameter_sha256": sha(parameter_path),
            "metadata": str(bv_meta.relative_to(args.runtime)).replace("\\", "/"),
            "metadata_sha256": sha(bv_meta),
        })
        for test_kind, deck_text in static_case_decks(spec, mesh_variant).items():
            static_deck = calibration_dir / f"{stem}_{test_kind}_{mesh_variant}.cmd"
            static_meta = calibration_dir / f"{stem}_{test_kind}_{mesh_variant}.json"
            put(static_deck, deck_text)
            put(static_meta, json.dumps(static_metadata(spec, test_kind, mesh_variant), ensure_ascii=False, indent=2) + "\n")
            records.append({
                "device": spec["device_family"],
                "phase": f"static_{test_kind}",
                "mesh_variant": mesh_variant,
                "deck": str(static_deck.relative_to(args.runtime)).replace("\\", "/"),
                "deck_sha256": sha(static_deck),
                "parameter": str(parameter_path.relative_to(args.runtime)).replace("\\", "/"),
                "parameter_sha256": sha(parameter_path),
                "metadata": str(static_meta.relative_to(args.runtime)).replace("\\", "/"),
                "metadata_sha256": sha(static_meta),
            })
        if not args.include_post_static_cases:
            continue
        for bias in BIASES:
            for phase in ("dc_restart", "transient"):
                stem = f"{spec['device_family'].lower()}_{bias}_{phase}"
                deck = device_dir / f"{stem}.cmd"
                meta = device_dir / f"{stem}.json"
                put(deck, sdevice_deck(spec, bias, "transient" if phase == "transient" else "dc"))
                metadata = case_metadata(spec, bias, phase)
                put(meta, json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
                records.append({"device": spec["device_family"], "bias_v": bias, "phase": phase, "deck": str(deck.relative_to(args.runtime)).replace("\\", "/"), "deck_sha256": sha(deck), "metadata": str(meta.relative_to(args.runtime)).replace("\\", "/"), "metadata_sha256": sha(meta)})
    manifest = {
        "schema_version": "650v_campaign_render_manifest/v2",
        "mesh_variant": mesh_variant,
        "source_dsl": [{"path": str(p.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(p)} for p, _ in specs],
        "records": records,
    }
    target_name = "render_manifest.json" if mesh_variant == "baseline" else f"render_manifest_{mesh_variant}.json"
    target = args.runtime / "generated" / target_name
    put(target, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"rendered={len(records)} manifest={target}")


if __name__ == "__main__":
    main()