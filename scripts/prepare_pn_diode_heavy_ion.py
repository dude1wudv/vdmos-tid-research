#!/usr/bin/env python3
"""Generate the auditable 2D PN-diode HeavyIon Sentaurus campaign."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "local_runtime" / "pn_diode_heavy_ion" / "generated"
SOURCE = (
    ROOT
    / "local_runtime"
    / "pn_diode_heavy_ion"
    / "official_source_20260721T131859"
    / "sde_dvs.cmd"
)
LETS = (1.0, 10.0, 50.0)
LET_TO_PC_UM = 0.0103667

SDE = r'''; 2D projection of the official Sentaurus 3Ddiode_demo.
(sde:clear)
(sdegeo:set-default-boolean "BAB")
(sdegeo:create-rectangle (position 0 0 0) (position 10 1 0) "Silicon" "R.Silicon")

(sdegeo:define-contact-set "top" 4 (color:rgb 1 0 0) "##")
(sdegeo:define-contact-set "bottom" 4 (color:rgb 0 0 1) "##")
(sdegeo:define-2d-contact (find-edge-id (position 10 0.5 0)) "top")
(sdegeo:define-2d-contact (find-edge-id (position 0 0.5 0)) "bottom")

; Preserve the official top boron Gaussian profile and project it inward.
(sdedr:define-refeval-window "BaseLine.Top" "Line"
  (position 10 0 0) (position 10 1 0))
(sdedr:define-gaussian-profile "Impl.Top"
  "BoronActiveConcentration"
  "PeakPos" 0 "PeakVal" 1e18
  "ValueAtDepth" 1e10 "Depth" 8
  "Gauss" "Factor" 0.8)
(sdedr:define-analytical-profile-placement "Place.Top"
  "Impl.Top" "BaseLine.Top" "Negative" "NoReplace" "Eval")

; Preserve the official bottom phosphorus Gaussian profile and project it inward.
(sdedr:define-refeval-window "BaseLine.Bottom" "Line"
  (position 0 0 0) (position 0 1 0))
(sdedr:define-gaussian-profile "Impl.Bottom"
  "PhosphorusActiveConcentration"
  "PeakPos" 0 "PeakVal" 1e18
  "ValueAtDepth" 1e10 "Depth" 8
  "Gauss" "Factor" 0.8)
(sdedr:define-analytical-profile-placement "Place.Bottom"
  "Impl.Bottom" "BaseLine.Bottom" "Positive" "NoReplace" "Eval")

(sdedr:define-refeval-window "RW.Global" "Rectangle"
  (position 0 0 0) (position 10 1 0))
(sdedr:define-refinement-size "Ref.Global" 0.25 0.10 0.05 0.02)
(sdedr:define-refinement-placement "Place.Global" "Ref.Global" "RW.Global")
(sdedr:define-refinement-function "Ref.Global" "DopingConcentration" "MaxTransDiff" 1)

; Resolve the projected junction and the center HeavyIon track.
(sdedr:define-refeval-window "RW.Junction" "Rectangle"
  (position 3.5 0 0) (position 6.5 1 0))
(sdedr:define-refinement-size "Ref.Junction" 0.10 0.05 0.02 0.01)
(sdedr:define-refinement-placement "Place.Junction" "Ref.Junction" "RW.Junction")
(sdedr:define-refinement-function "Ref.Junction" "DopingConcentration" "MaxTransDiff" 0.5)

(sdedr:define-refeval-window "RW.Track" "Rectangle"
  (position 0 0.35 0) (position 10 0.65 0))
(sdedr:define-refinement-size "Ref.Track" 0.10 0.025 0.02 0.005)
(sdedr:define-refinement-placement "Place.Track" "Ref.Track" "RW.Track")

(sde:build-mesh "pn2d")
'''

COMMON_PHYSICS = r'''Physics {
  Temperature = 300
  Mobility(PhuMob HighFieldSaturation(GradQuasiFermi))
  Recombination(SRH Avalanche)
  EffectiveIntrinsicDensity(BandGapNarrowing(oldSlotboom))
  Fermi
}
Plot {
  eDensity hDensity eMobility hMobility
  TotalCurrent/Vector eCurrent/Vector hCurrent/Vector
  ElectricField/Vector Potential SpaceCharge
  HeavyIonGeneration HeavyIonChargeDensity
  AvalancheGeneration eAvalancheGeneration hAvalancheGeneration
  Doping DonorConcentration AcceptorConcentration
  Temperature
}
Math {
  Transient = BE
  eMobilityAveraging = ElementEdge
  hMobilityAveraging = ElementEdge
  ElementVolumeAvalanche
  AvalFlatElementExclusion = 1
  WeightedVoronoiBox
  AutoCNPMinStepFactor = 0
  AutoNPMinStepFactor = 0
  SimStats ExitOnFailure Extrapolate
  Digits = 5
  ErrRef(electron) = 1e8
  ErrRef(hole) = 1e8
  Iterations = 20
  NotDamped = 100
  RHSMin = 1e-8
  EquilibriumSolution(Iterations=100)
  Method = ParDiSo
  NumberOfThreads = 1
  Wallclock
}
'''


def file_block(prefix: str, top_resist_ohm_um: float) -> str:
    return f'''File {{
  Grid = "pn2d_msh.tdr"
  Plot = "{prefix}"
  Current = "{prefix}.plt"
  Output = "{prefix}.log"
}}
Electrode {{
  {{ Name="top" Voltage=0 Resist={top_resist_ohm_um:g} }}
  {{ Name="bottom" Voltage=0 }}
}}
'''


def quasistationary_deck(prefix: str, voltage: float, save: bool) -> str:
    save_commands = ""
    if save:
        save_commands = (
            '\n  Save(FilePrefix="pn2d_reverse100_restart")'
            '\n  Plot(FilePrefix="pn2d_reverse100_state" NoOverwrite)'
        )
    return (
        file_block(prefix, 1e7 if voltage < 0 else 1.0)
        + COMMON_PHYSICS
        + f'''Solve {{
  Coupled(Iterations=100 LineSearchDamping=1e-4) {{ Poisson }}
  Coupled(Iterations=100) {{ Poisson Electron Hole }}
  Quasistationary(
    InitialStep=1e-3 Increment=1.4 Decrement=2
    MinStep=1e-8 MaxStep=0.05
    Goal {{ Name="top" Voltage={voltage:g} }}
  ) {{ Coupled {{ Poisson Electron Hole }} }}{save_commands}
}}
'''
    )


AUDIT_TIMES_PS = (92.0, 94.0, 96.0, 97.0, 98.0, 99.0, 99.5, 100.0, 100.2, 100.5, 101.0, 102.0, 103.0, 104.0, 106.0, 108.0)


def audit_label(time_ps: float) -> str:
    return f"{time_ps:g}".replace(".", "p") + "ps"


def transient_deck(case_id: str, let_f: float, final_time_s: float) -> tuple[str, dict[str, str], str]:
    physics = COMMON_PHYSICS.replace(
        "Physics {\n",
        f'''Physics {{
  HeavyIon(
    StartPoint=(0 0.5) Direction=(1 0) Length=10 Time=1e-10
    LET_f={let_f:.7g} Wt_hi=0.1 Gaussian PicoCoulomb
  )
''',
        1,
    )
    audit_steps = []
    audit_files: dict[str, str] = {}
    previous_s = 0.0
    for time_ps in AUDIT_TIMES_PS:
        time_s = time_ps * 1e-12
        max_step = 2e-13 if 97.0 <= time_ps <= 102.0 else 1e-12
        audit_steps.append(
            f'''  Transient(
    InitialTime={previous_s:.12g} FinalTime={time_s:.12g}
    InitialStep={min(max_step, max(time_s - previous_s, 2e-13)):.12g} Increment=1.0 Decrement=2
    MinStep=1e-17 MaxStep={max_step:.12g}
  ) {{ Coupled {{ Poisson Electron Hole }} }}
  Plot(FilePrefix="{case_id}_audit_{audit_label(time_ps)}" NoOverwrite)'''
        )
        audit_files[f"{time_s:.12g}"] = f"{case_id}_audit_{audit_label(time_ps)}_des.tdr"
        previous_s = time_s
    audit_block = "\n".join(audit_steps)
    final_label = "at2p1ns" if final_time_s <= 2.1e-9 else "at100ns"
    extension = ""
    if final_time_s > 2.1e-9:
        extension = f'''
  Transient(
    InitialTime=2.1e-9 FinalTime={final_time_s:.12g}
    InitialStep=2e-11 Increment=1.5 Decrement=2
    MinStep=1e-17 MaxStep=1e-9
  ) {{
    Coupled {{ Poisson Electron Hole }}
    Plot(FilePrefix="{case_id}_long" Time=(1e-8;5e-8;1e-7) NoOverwrite)
  }}'''
    checkpoint = f'\n  Plot(FilePrefix="{case_id}_at2p1ns" NoOverwrite)' if final_time_s > 2.1e-9 else ""
    deck = (
        file_block(case_id, 1e7)
        + physics
        + f'''Solve {{
  Load(FilePrefix="pn2d_reverse100_restart")
  Plot(FilePrefix="{case_id}_pre" NoOverwrite)
{audit_block}
  Transient(
    InitialTime=1.08e-10 FinalTime=2.1e-9
    InitialStep=2e-13 Increment=1.4 Decrement=2
    MinStep=1e-17 MaxStep=2e-11
  ) {{
    Coupled {{ Poisson Electron Hole }}
    Plot(FilePrefix="{case_id}_recovery" Time=(2e-10;5e-10;1e-9;2.1e-9) NoOverwrite)
  }}{checkpoint}{extension}
  Plot(FilePrefix="{case_id}_{final_label}" NoOverwrite)
}}
'''
    )
    return deck, audit_files, f"{case_id}_{final_label}_des.tdr"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def metadata(case_id: str, phase: str, **values: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": "pn_diode_heavy_ion_case/v1",
        "campaign_id": "PN2D_HI_20260721",
        "case_id": case_id,
        "device_family": "PN_DIODE",
        "structure_id": "OFFICIAL_3DDIODE_PROJECTED_2D",
        "phase": phase,
        "t_init_k": 300.0,
        "t_steady_k": 300.0,
        "high_terminal_name": "top",
        "low_terminal_name": "bottom",
        "bias_quantity": "VR",
        "target_bias_v": 100.0 if phase != "forward" else 1.2,
        "actual_bias_v": "NA",
        "top_series_resistance_ohm_um": 1.0 if phase == "forward" else 1e7,
        "equivalent_depth_um": 1.0,
        "current_normalization": "raw_2d_and_1um_equivalent",
        "mesh_variant": "baseline_track_refined",
        "mesh_leaf": "pn2d_msh.tdr",
        "threads": 1,
        "official_source_sha256": sha256(SOURCE),
        "temporary_assumption": "The omitted third dimension is represented by 1 um depth; this is not a calibrated chip current.",
    }
    base.update(values)
    return base


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"official source missing: {SOURCE}")
    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / "pn2d_sde.cmd", SDE)
    write(OUT / "pn2d_default.par", "* Use Sentaurus material defaults; physical models are declared in each deck.\n")
    write(OUT / "pn2d_forward.cmd", quasistationary_deck("pn2d_forward", 1.2, False))
    write(OUT / "pn2d_reverse100.cmd", quasistationary_deck("pn2d_reverse100", -100.0, True))
    write(
        OUT / "pn2d_forward.json",
        json.dumps(metadata("PN2D_FORWARD", "forward"), indent=2) + "\n",
    )
    write(
        OUT / "pn2d_reverse100.json",
        json.dumps(metadata("PN2D_REVERSE100", "dc_restart"), indent=2) + "\n",
    )

    generated = []
    for let in LETS:
        slug = str(int(let))
        case_id = f"pn2d_let{slug}"
        let_f = let * LET_TO_PC_UM
        deck_path = OUT / f"{case_id}.cmd"
        metadata_path = OUT / f"{case_id}.json"
        final_time_s = 1e-7
        deck_text, audit_files, exact_final_tdr = transient_deck(case_id, let_f, final_time_s)
        write(deck_path, deck_text)
        values = metadata(
            case_id.upper(),
            "heavy_ion_transient",
            let_mev_cm2_mg=let,
            let_f_pc_um=let_f,
            track_x_um=0.0,
            track_y_um=0.5,
            direction=[1.0, 0.0],
            length_um=10.0,
            wt_hi_um=0.1,
            strike_time_s=1e-10,
            final_time_s=final_time_s,
            total_time_s=final_time_s,
            restart_prefix="pn2d_reverse100_restart",
            exact_final_tdr=exact_final_tdr,
            heavy_ion_audit_tdrs=audit_files,
        )
        write(metadata_path, json.dumps(values, indent=2) + "\n")
        generated.append(
            {
                "case_id": case_id,
                "let_mev_cm2_mg": let,
                "let_f_pc_um": let_f,
                "deck_sha256": sha256(deck_path),
                "metadata_sha256": sha256(metadata_path),
            }
        )

    audit = {
        "schema": "pn_diode_heavy_ion_input_audit/v1",
        "official_source": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "official_source_sha256": sha256(SOURCE),
        "official_parameters": {
            "geometry_3d_um": [1.0, 1.0, 10.0],
            "projected_geometry_2d_um": [10.0, 1.0],
            "top_profile": ["BoronActiveConcentration", 1e18, 1e10, 8.0, 0.8],
            "bottom_profile": ["PhosphorusActiveConcentration", 1e18, 1e10, 8.0, 0.8],
        },
        "let_conversion_pc_um_per_mev_cm2_mg": LET_TO_PC_UM,
        "equivalent_depth_um": 1.0,
        "cases": generated,
    }
    write(OUT / "input_audit.json", json.dumps(audit, indent=2) + "\n")
    print(f"generated PN campaign inputs in {OUT}")


if __name__ == "__main__":
    main()