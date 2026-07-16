#!/usr/bin/env python3
"""Prepare the frozen 451.15 um IGBT/MOSFET SEB paper campaign."""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "docs/changes/2026-07-14-igbt-mosfet-seb-paper-simulation"
PROJECT_ROOT = ROOT / "projects/igbt_mosfet_seb_paper_20260714"
DEFAULT_MATRIX = PROJECT_ROOT / "case_matrix.csv"
DOC_MATRIX = DOC_ROOT / "case_matrix.csv"
PLOT_SPEC = PROJECT_ROOT / "plot_2ns_spec.json"
FROZEN_MANIFEST = PROJECT_ROOT / "frozen_input_manifest.json"
PARAMETER_SNAPSHOT = PROJECT_ROOT / "parameters/sdevice_parameter_snapshot.json"
DEFAULT_PROJECT = ROOT / "local_runtime/tcad_projects/igbt_mosfet_seb_paper_20260714"
SDE_SOURCE = (
    ROOT
    / "local_runtime/igbt_seb_full_20260712_035027/cases"
    / "A01_v2500_let15_y3p5__attempt01/sde_seb.cmd"
)
HEAVY_ION_SOURCE = (
    ROOT
    / "local_runtime/igbt_seb_full_20260712_035027/cases"
    / "A01_v2500_let15_y3p5__attempt04/case.cmd"
)
PARAMETER_SOURCE = HEAVY_ION_SOURCE.with_name("sdevice.par")
EXPECTED_CASES = {
    ("IGBT", 243.15, 550.0),
    ("IGBT", 298.15, 550.0),
    ("IGBT", 323.15, 550.0),
    ("IGBT", 343.15, 550.0),
    ("IGBT", 298.15, 500.0),
    ("IGBT", 298.15, 525.0),
    ("IGBT", 298.15, 575.0),
    ("MOSFET", 298.15, 550.0),
}
AUDIT_TIMES = (
    ("092", "9.2e-11"),
    ("094", "9.4e-11"),
    ("096", "9.6e-11"),
    ("097", "9.7e-11"),
    ("098", "9.8e-11"),
    ("099", "9.9e-11"),
    ("099p5", "9.95e-11"),
    ("100", "1e-10"),
    ("100p2", "1.002e-10"),
    ("100p5", "1.005e-10"),
    ("101", "1.01e-10"),
    ("102", "1.02e-10"),
    ("103", "1.03e-10"),
    ("104", "1.04e-10"),
    ("106", "1.06e-10"),
    ("108", "1.08e-10"),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace("\r\n", "\n"))


def write_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load_matrix(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 8:
        raise ValueError(f"case_matrix must contain exactly 8 rows, found {len(rows)}")
    ids = [row["case_id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("case_matrix case_id values are not unique")
    actual = {
        (row["device_family"], float(row["t_init_k"]), float(row["target_vce_v"]))
        for row in rows
    }
    if actual != EXPECTED_CASES:
        raise ValueError(f"case_matrix points differ from the preregistered set: {actual}")
    shared = [row for row in rows if row["shared_reference"].lower() == "true"]
    if len(shared) != 1 or shared[0]["case_id"] != "IGBT_T298_V550_L15":
        raise ValueError("shared reference must be the unique IGBT 298.15 K / 550 V row")
    for row in rows:
        checks = {
            "let_mev_cm2_mg": 15.0,
            "let_f_pc_um": 0.1555,
            "track_x_um": 0.0,
            "track_y_um": 3.5,
            "direction_x": 1.0,
            "direction_y": 0.0,
            "length_um": 50.0,
            "wt_hi_um": 0.1,
            "strike_time_s": 1e-10,
            "total_time_s": 2.1e-9,
            "post_strike_time_s": 2.0e-9,
            "v_gate_v": 0.0,
            "v_emitter_source_v": 0.0,
        }
        for key, expected in checks.items():
            if float(row[key]) != expected:
                raise ValueError(f"{row['case_id']} has non-frozen {key}={row[key]}")
    return rows


def validate_sources(sde: str, heavy_ion: str) -> None:
    required_sde = (
        "(define ymax 451.15)",
        '"PeakVal" 5.0e19',
        '"ValueAtDepth" 4.0e17  "Depth" 0.5',
        '"BoronActiveConcentration"',
        '(position 451.15 0.0 0.0)',
        '"RW.SEBTrackCore"',
    )
    missing = [token for token in required_sde if token not in sde]
    if missing:
        raise ValueError(f"frozen SDE source lacks required 451.15 um facts: {missing}")
    forbidden = ("Rc=1e11", "Voltage=2500")
    if any(token in sde for token in forbidden):
        raise ValueError("frozen SDE source contains a forbidden BV/formal-result token")
    required_heavy = (
        "StartPoint=(0 3.5)",
        "Direction=(1 0)",
        "Length=50",
        "Time=1e-10",
        "LET_f=0.1555",
        "Wt_hi=0.1",
        "Gaussian PicoCoulomb",
    )
    missing_heavy = [token for token in required_heavy if token not in heavy_ion]
    if missing_heavy:
        raise ValueError(f"attempt04 HeavyIon source lacks required semantics: {missing_heavy}")


def replace_output_prefix(sde: str, stem: str) -> str:
    replacements = {
        '"igbt_seb_bnd.tdr"': f'"{stem}_bnd.tdr"',
        '"igbt_seb_msh.cmd"': f'"{stem}_msh.cmd"',
        '"snmesh -offset igbt_seb_msh"': f'"snmesh -offset {stem}_msh"',
    }
    for old, new in replacements.items():
        if old not in sde:
            raise ValueError(f"frozen SDE source missing output token: {old}")
        sde = sde.replace(old, new, 1)
    return sde


def derive_mosfet(sde: str) -> str:
    replacements = {
        '(sdegeo:define-contact-set "Collector"': '(sdegeo:define-contact-set "Drain"',
        '"Collector")\n(sdegeo:define-2d-contact (find-edge-id (position -0.3': '"Drain")\n(sdegeo:define-2d-contact (find-edge-id (position -0.3',
        '(sdedr:define-refeval-window "BaseLine.collector"': '(sdedr:define-refeval-window "BaseLine.drain"',
        '(sdedr:define-gaussian-profile "Impl.collectorprof"': '(sdedr:define-gaussian-profile "Impl.drainprof"',
        '"BoronActiveConcentration"\n "PeakPos" 0.0  "PeakVal" 5.0e19': '"ArsenicActiveConcentration"\n "PeakPos" 0.0  "PeakVal" 5.0e19',
        '(sdedr:define-analytical-profile-placement "Impl.collector"\n "Impl.collectorprof" "BaseLine.collector"': '(sdedr:define-analytical-profile-placement "Impl.drain"\n "Impl.drainprof" "BaseLine.drain"',
    }
    for old, new in replacements.items():
        if sde.count(old) != 1:
            raise ValueError(f"strict MOSFET derivation expected exactly one token: {old}")
        sde = sde.replace(old, new, 1)
    return sde


def refine_track_core(sde: str) -> str:
    old = '(sdedr:define-refinement-size "Ref.SEBTrackCore"\n  0.2 0.025\n  0.02 0.005)'
    new = '(sdedr:define-refinement-size "Ref.SEBTrackCore"\n  0.1 0.0125\n  0.01 0.0025)'
    if sde.count(old) != 1:
        raise ValueError("track-core refinement block differs from the frozen source")
    return sde.replace(old, new, 1)


def canonical_sde(text: str) -> str:
    text = re.sub(r'"(?:igbt|mosfet)_(?:baseline|track_refined)_(?:bnd\.tdr|msh\.cmd)"', '"OUTPUT"', text)
    text = re.sub(r'"snmesh -offset (?:igbt|mosfet)_(?:baseline|track_refined)_msh"', '"OUTPUT_COMMAND"', text)
    text = text.replace('"Drain"', '"Collector"')
    text = text.replace('"BaseLine.drain"', '"BaseLine.collector"')
    text = text.replace('"Impl.drainprof"', '"Impl.collectorprof"')
    text = text.replace('"Impl.drain"', '"Impl.collector"')
    text = text.replace(
        '"ArsenicActiveConcentration"\n "PeakPos" 0.0  "PeakVal" 5.0e19',
        '"BoronActiveConcentration"\n "PeakPos" 0.0  "PeakVal" 5.0e19',
    )
    return text


def make_sde_decks(source: str) -> tuple[dict[str, str], dict[str, object]]:
    decks: dict[str, str] = {}
    igbt_baseline = replace_output_prefix(source, "igbt_baseline")
    mosfet_baseline = replace_output_prefix(derive_mosfet(source), "mosfet_baseline")
    decks["igbt_baseline"] = igbt_baseline
    decks["mosfet_baseline"] = mosfet_baseline
    decks["igbt_track_refined"] = replace_output_prefix(refine_track_core(source), "igbt_track_refined")
    decks["mosfet_track_refined"] = replace_output_prefix(refine_track_core(derive_mosfet(source)), "mosfet_track_refined")
    if canonical_sde(igbt_baseline) != canonical_sde(mosfet_baseline):
        diff = "\n".join(
            difflib.unified_diff(
                canonical_sde(igbt_baseline).splitlines(),
                canonical_sde(mosfet_baseline).splitlines(),
                lineterm="",
            )
        )
        raise ValueError("MOSFET strict derivation changed non-approved content:\n" + diff)
    source_canonical = canonical_sde(replace_output_prefix(source, "igbt_baseline"))
    if canonical_sde(igbt_baseline) != source_canonical:
        raise ValueError("IGBT baseline is not a pure output-prefix derivation")
    audit = {
        "structure_height_um": 451.15,
        "bottom_profile_depth_um": 0.5,
        "bottom_peak_cm3": 5e19,
        "igbt_bottom_species": "BoronActiveConcentration",
        "mosfet_bottom_species": "ArsenicActiveConcentration",
        "igbt_bottom_contact": "Collector",
        "mosfet_bottom_contact": "Drain",
        "frozen_regions": ["R.Si", "R.Gox", "R.LOCOS", "R.Spacer", "R.PolyGate", "R.PolyCont"],
        "si_sio2_interface_segments_um": [
            [[0.0, 1.98], [3.22, 2.08]],
            [[3.22, 2.08], [3.22, 2.72]],
            [[3.22, 2.72], [0.0, 2.82]],
            [[0.02, 2.0], [0.02, 1.5]],
            [[0.02, 1.5], [0.22, 1.3]],
            [[0.22, 1.3], [0.22, 0.0]],
        ],
        "refinement_only_change": {
            "window_um": [[0.0, 3.3], [55.0, 3.7]],
            "baseline_steps_um": [0.2, 0.025, 0.02, 0.005],
            "refined_steps_um": [0.1, 0.0125, 0.01, 0.0025],
            "local_grid_scale_um": 0.01,
        },
        "mosfet_wording": "结构匹配的派生对照器件",
        "strict_derivation_pass": True,
    }
    return decks, audit


def contact_names(device: str) -> tuple[str, str]:
    return ("Collector", "Emitter") if device == "IGBT" else ("Drain", "Emitter")


def plot_block(include_heavy_ion: bool) -> str:
    fields = [
        "eDensity hDensity",
        "eMobility hMobility",
        "TotalCurrent/Vector eCurrent/Vector hCurrent/Vector",
        "ElectricField/Vector Potential SpaceCharge",
        "Temperature JouleHeat TotalHeat",
        "AvalancheGeneration eAvalancheGeneration hAvalancheGeneration",
        "Doping DonorConcentration AcceptorConcentration",
    ]
    if include_heavy_ion:
        fields.insert(5, "HeavyIonGeneration HeavyIonChargeDensity")
    return "Plot {\n  " + "\n  ".join(fields) + "\n}"


def common_header(row: dict[str, str], mesh_leaf: str, prefix: str, transient: bool) -> str:
    device = row["device_family"]
    high, low = contact_names(device)
    temperature = row["t_init_k"]
    heavy = ""
    if transient:
        heavy = """
  HeavyIon(
    StartPoint=(0 3.5) Direction=(1 0) Length=50 Time=1e-10
    LET_f=0.1555 Wt_hi=0.1 Gaussian PicoCoulomb
  )"""
    return f'''File {{
  Grid = "{mesh_leaf}"
  Parameters = "sdevice.par"
  Plot = "{prefix}"
  Current = "{prefix}.plt"
  Output = "{prefix}.log"
}}
Electrode {{
  {{ Name="Gate" Voltage=0 }}
  {{ Name="{low}" Voltage=0 }}
  {{ Name="{high}" Voltage=0 }}
}}
Thermode {{
  {{ Name="Gate" Temperature={temperature} }}
  {{ Name="{low}" Temperature={temperature} }}
  {{ Name="{high}" Temperature={temperature} }}
}}
Physics {{
  Temperature={temperature}
  EffectiveIntrinsicDensity(BandGapNarrowing(Slotboom))
  Thermodynamic
  AnalyticTEP{heavy}
}}
Physics(Material="Silicon") {{
  Mobility(DopingDep HighFieldSaturation)
  Recombination(SRH(DopingDependence TempDependence) Auger Avalanche(Lackner))
}}
{plot_block(transient)}
'''


def dc_deck(row: dict[str, str], mesh_leaf: str, prefix: str, restart_prefix: str) -> str:
    high, _ = contact_names(row["device_family"])
    return common_header(row, mesh_leaf, prefix, False) + f'''Math {{
  Extrapolate Notdamped=50 Iterations=25 ExitOnFailure
  Digits=5 ErrRef(electron)=1e10 ErrRef(hole)=1e10
}}
Solve {{
  Poisson
  Coupled {{ Poisson Electron Hole }}
  Quasistationary(
    InitialStep=1e-3 Increment=1.5 Decrement=2
    MinStep=1e-9 MaxStep=0.05
    Goal {{ Name={high} Voltage={row["target_vce_v"]} }}
  ) {{ Coupled {{ Poisson Electron Hole Temperature }} }}
  Save(FilePrefix="{restart_prefix}")
  Plot(FilePrefix="{prefix}_pre" NoOverwrite)
}}
'''


def transient_deck(row: dict[str, str], mesh_leaf: str, prefix: str, restart_prefix: str) -> str:
    pieces = [common_header(row, mesh_leaf, prefix, True)]
    pieces.append('''Math {
  Extrapolate Transient=BE Notdamped=50 Iterations=25 ExitOnFailure
  Digits=5 ErrRef(electron)=1e10 ErrRef(hole)=1e10
  BreakCriteria { LatticeTemperature(MaxVal=2500) }
}
Solve {
''')
    pieces.append(f'  Load(FilePrefix="{restart_prefix}")\n')
    pieces.append(f'  Plot(FilePrefix="{prefix}_pre" NoOverwrite)\n')
    pieces.append(f'  NewCurrentPrefix="{prefix}_transient_"\n')
    previous = "0"
    for index, (label, time_s) in enumerate(AUDIT_TIMES):
        if index == 0:
            controls = "InitialStep=1e-13 Increment=1.5 Decrement=2 MinStep=1e-17 MaxStep=1e-11"
        elif 4 <= index <= 11:
            controls = "InitialStep=2e-13 Increment=1.0 Decrement=2 MinStep=1e-17 MaxStep=2e-13"
        else:
            controls = "InitialStep=1e-12 Increment=1.4 Decrement=2 MinStep=1e-17 MaxStep=1e-12"
        pieces.append(
            f'''  Transient(InitialTime={previous} FinalTime={time_s} {controls}) {{
    Coupled {{ Poisson Electron Hole Temperature }}
  }}
  Plot(FilePrefix="{prefix}_audit_{label}ps" NoOverwrite)
'''
        )
        previous = time_s
    pieces.append(
        f'''  Transient(
    InitialTime=1.08e-10 FinalTime=2.1e-9
    InitialStep=2e-13 Increment=1.4 Decrement=2
    MinStep=1e-17 MaxStep=1e-10
  ) {{ Coupled {{ Poisson Electron Hole Temperature }} }}
  Plot(FilePrefix="{prefix}_at2p1ns" NoOverwrite)
}}
'''
    )
    return "".join(pieces)


def metadata_for(
    row: dict[str, str],
    phase: str,
    mesh_variant: str,
    mesh_leaf: str,
    restart_prefix: str,
    exact_tdr: str = "NA",
) -> dict[str, object]:
    return {
        "schema": "igbt_mosfet_seb_case/v1",
        "case_id": row["case_id"],
        "device_family": row["device_family"],
        "device_role": row["device_role"],
        "phase": phase,
        "t_init_k": float(row["t_init_k"]),
        "t_steady_k": "NA",
        "t_steady_max_k": "NA",
        "target_vce_v": float(row["target_vce_v"]),
        "actual_vce_v": "NA",
        "let_mev_cm2_mg": float(row["let_mev_cm2_mg"]),
        "let_f_pc_um": float(row["let_f_pc_um"]),
        "track_x_um": float(row["track_x_um"]),
        "track_y_um": float(row["track_y_um"]),
        "direction": [float(row["direction_x"]), float(row["direction_y"])],
        "length_um": float(row["length_um"]),
        "wt_hi_um": float(row["wt_hi_um"]),
        "strike_time_s": float(row["strike_time_s"]),
        "total_time_s": float(row["total_time_s"]),
        "post_strike_time_s": float(row["post_strike_time_s"]),
        "mesh_variant": mesh_variant,
        "mesh_leaf": mesh_leaf,
        "restart_prefix": restart_prefix,
        "exact_2p1ns_tdr": exact_tdr,
        "threads": 1,
        "source_structure": SDE_SOURCE.relative_to(ROOT).as_posix(),
        "source_heavy_ion": HEAVY_ION_SOURCE.relative_to(ROOT).as_posix(),
        "formal_result_eligible": phase == "transient" and mesh_variant == "baseline",
    }


def build_case_inputs(
    row: dict[str, str],
    mesh_variant: str,
    case_id: str | None = None,
) -> dict[str, object]:
    case_id = case_id or row["case_id"]
    effective = dict(row)
    effective["case_id"] = case_id
    device_slug = row["device_family"].lower()
    mesh_stem = f"{device_slug}_{mesh_variant}"
    mesh_leaf = f"{mesh_stem}_msh.tdr"
    restart_prefix = f"{case_id}_restart"
    dc_prefix = f"{case_id}_dc"
    transient_prefix = f"{case_id}_tr"
    return {
        "case_id": case_id,
        "row": effective,
        "mesh_variant": mesh_variant,
        "mesh_leaf": mesh_leaf,
        "restart_prefix": restart_prefix,
        "dc_prefix": dc_prefix,
        "transient_prefix": transient_prefix,
        "dc_deck": dc_deck(effective, mesh_leaf, dc_prefix, restart_prefix),
        "transient_deck": transient_deck(effective, mesh_leaf, transient_prefix, restart_prefix),
        "dc_metadata": metadata_for(effective, "dc_restart", mesh_variant, mesh_leaf, restart_prefix),
        "transient_metadata": metadata_for(
            effective,
            "transient",
            mesh_variant,
            mesh_leaf,
            restart_prefix,
            f"{transient_prefix}_at2p1ns_des.tdr",
        ),
    }


def frozen_file_records(root: Path, excluded: set[str] | None = None) -> list[dict[str, object]]:
    excluded = excluded or set()
    records = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        records.append(
            {
                "relative_path": relative,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return records


def remove_stale_case_inputs(case_root: Path, expected_case_ids: set[str]) -> None:
    """Keep generated case inputs aligned exactly with the frozen 8+2 manifest."""
    if not case_root.exists():
        return
    for path in case_root.iterdir():
        if path.is_dir() and path.name not in expected_case_ids:
            shutil.rmtree(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    rows = load_matrix(args.matrix)
    required_tracked = (DOC_MATRIX, PLOT_SPEC, FROZEN_MANIFEST, PARAMETER_SNAPSHOT)
    missing_tracked = [path for path in required_tracked if not path.is_file()]
    if missing_tracked:
        raise ValueError(f"tracked campaign input missing: {missing_tracked}")
    if args.matrix.resolve() == DEFAULT_MATRIX.resolve() and args.matrix.read_bytes() != DOC_MATRIX.read_bytes():
        raise ValueError("tracked project and requirement case_matrix copies differ")
    sde_source = SDE_SOURCE.read_text(encoding="utf-8")
    heavy_ion_source = HEAVY_ION_SOURCE.read_text(encoding="utf-8")
    validate_sources(sde_source, heavy_ion_source)
    sde_decks, derivation_audit = make_sde_decks(sde_source)
    main_cases = [build_case_inputs(row, "baseline") for row in rows]
    reference_rows = {
        row["device_family"]: row
        for row in rows
        if float(row["t_init_k"]) == 298.15 and float(row["target_vce_v"]) == 550.0
    }
    validation_cases = [
        build_case_inputs(
            reference_rows[device],
            "track_refined",
            f"VAL_{device}_T298_V550_L15_track_refined",
        )
        for device in ("IGBT", "MOSFET")
    ]
    all_cases = main_cases + validation_cases
    for case in all_cases:
        if "FinalTime=2.1e-9" not in case["transient_deck"]:
            raise ValueError(f"{case['case_id']} lacks exact 2.1 ns final segment")
        if case["transient_deck"].count("LET_f=0.1555") != 1:
            raise ValueError(f"{case['case_id']} HeavyIon semantics drifted")
        if "eMobility hMobility" not in case["transient_deck"]:
            raise ValueError(f"{case['case_id']} lacks separate mobility outputs")

    summary = {
        "status": "VALID",
        "matrix_path": args.matrix.resolve().as_posix(),
        "matrix_sha256": sha256_file(args.matrix),
        "tracked_project_hashes": {
            "frozen_input_manifest": sha256_file(FROZEN_MANIFEST),
            "plot_2ns_spec": sha256_file(PLOT_SPEC),
            "parameter_snapshot": sha256_file(PARAMETER_SNAPSHOT),
        },
        "main_case_count": len(main_cases),
        "validation_case_count": len(validation_cases),
        "source_hashes": {
            "sde_seb_cmd": sha256_file(SDE_SOURCE),
            "heavy_ion_case_cmd": sha256_file(HEAVY_ION_SOURCE),
            "sdevice_par": sha256_file(PARAMETER_SOURCE),
        },
        "derivation_audit": derivation_audit,
    }
    if args.validate_only:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    project = args.project_root
    input_root = project / "inputs"
    sde_root = input_root / "sde"
    case_root = input_root / "cases"
    for path in (
        sde_root,
        case_root,
        project / "mesh",
        project / "dc",
        project / "transient",
        project / "runs",
        project / "extracts",
        project / "figures",
        project / "logs",
    ):
        path.mkdir(parents=True, exist_ok=True)
    remove_stale_case_inputs(case_root, {str(case["case_id"]) for case in all_cases})
    for stem, deck in sde_decks.items():
        write_text(sde_root / f"{stem}_sde.cmd", deck)
    shutil.copy2(PARAMETER_SOURCE, input_root / "sdevice.par")
    shutil.copy2(args.matrix, input_root / "case_matrix.csv")
    shutil.copy2(PLOT_SPEC, input_root / "plot_2ns_spec.json")
    shutil.copy2(FROZEN_MANIFEST, input_root / "frozen_input_manifest.json")
    shutil.copy2(PARAMETER_SNAPSHOT, input_root / "sdevice_parameter_snapshot.json")
    manifest_cases = []
    for case in all_cases:
        directory = case_root / str(case["case_id"])
        write_text(directory / f"{case['case_id']}_dc.cmd", str(case["dc_deck"]))
        write_text(directory / f"{case['case_id']}_transient.cmd", str(case["transient_deck"]))
        write_json(directory / f"{case['case_id']}_dc.json", case["dc_metadata"])
        write_json(directory / f"{case['case_id']}_transient.json", case["transient_metadata"])
        manifest_cases.append(
            {
                "case_id": case["case_id"],
                "run_class": "paper_main" if case in main_cases else "validation_only",
                "device_family": case["row"]["device_family"],
                "mesh_variant": case["mesh_variant"],
                "mesh_leaf": case["mesh_leaf"],
                "restart_prefix": case["restart_prefix"],
                "dc_deck": (directory / f"{case['case_id']}_dc.cmd").relative_to(project).as_posix(),
                "transient_deck": (directory / f"{case['case_id']}_transient.cmd").relative_to(project).as_posix(),
                "dc_metadata": (directory / f"{case['case_id']}_dc.json").relative_to(project).as_posix(),
                "transient_metadata": (directory / f"{case['case_id']}_transient.json").relative_to(project).as_posix(),
                "exact_2p1ns_tdr": case["transient_metadata"]["exact_2p1ns_tdr"],
            }
        )
    write_json(input_root / "source_and_derivation_audit.json", summary)
    write_json(
        input_root / "campaign_manifest.json",
        {
            "schema": "igbt_mosfet_seb_campaign/v1",
            "remote_root": "/home/tcad/codex_runs/igbt_mosfet_seb_paper_20260714",
            "main_case_count": 8,
            "validation_case_count": 2,
            "fail_closed_reference": "IGBT_T298_V550_L15",
            "cases": manifest_cases,
        },
    )
    write_json(
        input_root / "frozen_input_hashes.json",
        {
            "schema": "igbt_mosfet_seb_frozen_runtime/v1",
            "campaign": "igbt_mosfet_seb_paper_20260714",
            "records": frozen_file_records(input_root, {"frozen_input_hashes.json"}),
        },
    )
    print(f"PREPARED main=8 validation=2 project={project}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())