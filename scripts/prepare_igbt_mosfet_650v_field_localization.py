#!/usr/bin/env python3
"""Prepare hash-bound 325/400/500 V field-localization decks after mesh closure."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "local_runtime" / "tcad_projects" / "igbt_mosfet_650v_seb_20260715"
DATA = ROOT / "docs" / "changes" / "2026-07-15-igbt-mosfet-650v-redesign" / "data"
PROJECT = ROOT / "projects" / "igbt_mosfet_650v_seb_20260715" / "devices"
BIASES = (325, 400, 500)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def resolved_value(spec: dict, name: str):
    item = spec["parameters"][name]
    if item["final_value"] is not None:
        return item["final_value"]
    if item.get("candidate_value") is not None:
        return item["candidate_value"]
    return item["seed_value"]


def gate_electrode(spec: dict) -> str:
    contact = spec["gate_contact"]
    if contact["electrode_model"] == "barrier_offset":
        return f'{{ Name="Gate" Voltage=0 Barrier={float(contact["barrier_ev"]):.8g} }}'
    return f'{{ Name="Gate" Voltage=0 Material="{contact["material"]}"({contact["conductivity_type"]}) }}'


def field_deck(spec: dict, bias: int, mesh_leaf: str, prefix: str) -> str:
    family = spec["device_family"]
    high = "Collector" if family == "IGBT" else "Drain"
    low = "Emitter" if family == "IGBT" else "Source"
    mobility = "DopingDep HighFieldSaturation" if family == "IGBT" else "DopingDep Enormal HighFieldSaturation"
    interface_charge = float(resolved_value(spec, "interface_fixed_charge_concentration"))
    return f'''# verified-mesh off-state field localization; no HeavyIon
File {{
  Grid = "{mesh_leaf}"
  Parameters = "sdevice.par"
  Plot = "{prefix}"
  Current = "{prefix}.plt"
  Output = "{prefix}.log"
}}
Electrode {{
  {{ Name="{low}" Voltage=0 }}
  {{ Name="{high}" Voltage=0 }}
  {gate_electrode(spec)}
}}
Physics {{ Temperature=298.15 EffectiveIntrinsicDensity(OldSlotboom) }}
Physics(Material="Silicon") {{
  Mobility({mobility})
  Recombination(SRH(DopingDependence TempDependence) Auger Avalanche(GradQuasiFermi))
}}
Physics(MaterialInterface="Silicon/Oxide") {{ Traps(FixedCharge Conc={interface_charge:.8g}) }}
Plot {{
  ElectricField/Vector Potential SpaceCharge
  eDensity hDensity TotalCurrent/Vector
  ImpactIonization eImpactIonization hImpactIonization
  Doping DonorConcentration AcceptorConcentration
}}
Math {{
  Extrapolate RelErrControl Digits=5 Iterations=35 NotDamped=80
  ErrRef(Electron)=1e10 ErrRef(Hole)=1e10
  AvalDensGradQF ElementVolumeAvalanche AvalFlatElementExclusion=1.0 ExitOnFailure
}}
Solve {{
  Poisson
  Coupled(Iterations=100 LineSearchDamping=1e-4) {{ Poisson Electron }}
  Coupled(Iterations=100 LineSearchDamping=1e-4) {{ Poisson Electron Hole }}
  Quasistationary(
    InitialStep=1e-5 Increment=1.3 MaxStep=0.005 MinStep=1e-8
    Goal {{ Name="{high}" Voltage={bias} }}
  ) {{ Coupled {{ Poisson Electron Hole }} }}
  Plot(FilePrefix="{prefix}_pre" NoOverwrite)
}}
'''


def main() -> None:
    v1_gate_path = DATA / "static_mesh_consistency.json"
    v2_gate_path = DATA / "static_mesh_consistency_v2.json"
    v1_gate = read_json(v1_gate_path)
    v2_gate = read_json(v2_gate_path)
    if v1_gate["devices"]["IGBT"]["status"] != "PASSED":
        raise ValueError("IGBT refined-v1 mesh evidence is not PASSED")
    if v2_gate.get("status") != "PASSED" or v2_gate.get("static_mesh_gate_closed") is not True:
        raise ValueError("MOSFET refined-v2 mesh evidence is not PASSED")
    if v1_gate.get("heavy_ion_authorized") is not False or v2_gate.get("heavy_ion_authorized") is not False:
        raise ValueError("field localization must precede HeavyIon authorization")

    configurations = {
        "IGBT": {
            "dsl": PROJECT / "igbt_650v.json",
            "mesh": RUNTIME / "calibration_inputs" / "igbt" / "refined" / "igbt_650v_refined_msh.tdr",
            "parameter": RUNTIME / "calibration_inputs" / "igbt" / "refined" / "sdevice.par",
            "variant": "refined",
            "expected_mesh": v1_gate["devices"]["IGBT"]["refined_mesh_sha256"],
        },
        "MOSFET": {
            "dsl": PROJECT / "mosfet_650v_sj.json",
            "mesh": RUNTIME / "calibration_inputs" / "mosfet" / "refined_v2_local" / "mosfet_650v_refined_v2_local_msh.tdr",
            "parameter": RUNTIME / "calibration_inputs" / "mosfet" / "refined_v2_local" / "sdevice.par",
            "variant": "refined_v2_local",
            "expected_mesh": v2_gate["mesh_progression"]["sha256"][-1],
        },
    }

    records = []
    output_root = RUNTIME / "field_localization_inputs"
    for family, config in configurations.items():
        spec = read_json(config["dsl"])
        if sha256(config["mesh"]) != config["expected_mesh"]:
            raise ValueError(f"{family} verified mesh hash mismatch")
        for bias in BIASES:
            case_id = f"{family}650_FIELD_V{bias}"
            prefix = case_id.lower()
            case_dir = output_root / family.lower() / str(bias)
            case_dir.mkdir(parents=True, exist_ok=True)
            deck_path = case_dir / f"{prefix}.cmd"
            metadata_path = case_dir / f"{prefix}.json"
            with deck_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(field_deck(spec, bias, config["mesh"].name, prefix))
            metadata = {
                "schema_version": "650v_field_localization_case/v1",
                "campaign_id": "igbt_mosfet_650v_seb_20260715",
                "publication_profile": spec["publication_profile"],
                "structure_id": spec["structure_id"],
                "device_family": family,
                "test_kind": "off_state_field_localization",
                "high_terminal_name": "Collector" if family == "IGBT" else "Drain",
                "low_terminal_name": "Emitter" if family == "IGBT" else "Source",
                "bias_quantity": "VCE" if family == "IGBT" else "VDS",
                "target_blocking_voltage_v": bias,
                "actual_blocking_voltage_v": None,
                "target_vce_v": bias,
                "actual_vce_v": None,
                "rated_voltage_v": 650,
                "bv_static_v": None,
                "bv_criterion": spec["static_gates"]["bv_criterion"],
                "derating_basis": "field localization on a verified mesh before HeavyIon authorization",
                "parent_restart_ids": [],
                "parent_restart_hashes": [],
                "termination_reason": "PENDING_FIELD_EXTRACTION",
                "let_mev_cm2_mg": 0,
                "mesh_variant": config["variant"],
                "mesh_sha256": config["expected_mesh"],
                "coordinate_system": {"x": "device depth from top surface", "y": "lateral cell coordinate", "unit": "um"},
                "silicon_bounds_um": {"x_min": 0.0, "x_max": float(resolved_value(spec, "drift_thickness")), "y_min": 0.0, "y_max": 6.0},
                "static_mesh_evidence": relative(v1_gate_path if family == "IGBT" else v2_gate_path),
                "static_mesh_evidence_sha256": sha256(v1_gate_path if family == "IGBT" else v2_gate_path),
                "heavy_ion_authorized": False,
                "t_init_k": 298.15,
                "t_steady_k": 298.15,
                "t_steady_max_k": 298.15,
            }
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            records.append({
                "case_id": case_id,
                "device_family": family,
                "bias_v": bias,
                "mesh_variant": config["variant"],
                "mesh": relative(config["mesh"]),
                "mesh_sha256": sha256(config["mesh"]),
                "parameter": relative(config["parameter"]),
                "parameter_sha256": sha256(config["parameter"]),
                "deck": relative(deck_path),
                "deck_sha256": sha256(deck_path),
                "metadata": relative(metadata_path),
                "metadata_sha256": sha256(metadata_path),
                "expected_tdr_leaf": f"{prefix}_pre_des.tdr",
            })
    manifest = {
        "schema_version": "650v_field_localization_prepare/v1",
        "status": "PREPARED",
        "static_mesh_gate": {"path": relative(v2_gate_path), "sha256": sha256(v2_gate_path), "status": "PASSED"},
        "heavy_ion_authorized": False,
        "records": records,
    }
    manifest_path = output_root / "field_localization_prepare_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"prepared={len(records)} manifest={manifest_path}")


if __name__ == "__main__":
    main()