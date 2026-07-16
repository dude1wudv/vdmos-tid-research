#!/usr/bin/env python3
"""Prepare and audit the hash-bound IGBT 400 V numerical recovery chain."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "local_runtime" / "tcad_projects" / "igbt_mosfet_650v_seb_20260715"
REPORT_DATA = ROOT / "docs" / "changes" / "2026-07-15-igbt-mosfet-650v-redesign" / "data"
RUNS = RUNTIME / "runs"
FAILED_RUN_ID = "IGBT650_LET15_2P1NS_V400__authorized_55a3a83a_restart_a5f0194b_reference_v1__20260716T061941348Z__452be836"
PARENT_RUN_ID = "IGBT650_DC_RESTART_V400__authorized_55a3a83a_chain_v1__20260716T045835700Z__80fe2d4a"
FAILED_RUN = RUNS / FAILED_RUN_ID
PARENT_RUN = RUNS / PARENT_RUN_ID
BASE_DECK = FAILED_RUN / "inputs" / "igbt_400_let15_2p1ns.cmd"
BASE_METADATA = FAILED_RUN / "inputs" / "igbt_400_let15_2p1ns.json"
PARAMETER = FAILED_RUN / "inputs" / "sdevice.par"
MESH = FAILED_RUN / "inputs" / "igbt_650v_refined_msh.tdr"
PARENT_MAIN = PARENT_RUN / "artifacts" / "IGBT650_V400_restart_des.sav"
PARENT_CIRCUIT = PARENT_RUN / "artifacts" / "IGBT650_V400_restart_circuit_des.sav"
AUTHORIZATION = REPORT_DATA / "heavy_ion_authorization.json"
BINDING_SET = REPORT_DATA / "restart_binding_set.json"
CLAIM_LEDGER = REPORT_DATA / "claim_ledger.json"
FAILED_MANIFEST = FAILED_RUN / "run_manifest.json"
FAILED_LOG = FAILED_RUN / "artifacts" / "IGBT650_V400_transient.log_des.log"
FAILED_PLT = FAILED_RUN / "artifacts" / "IGBT650_V400_tr_transient_IGBT650_V400_transient.plt"
PROFILE = "IGBT400_PRESTRIKE_THERMAL_DAMPED_SEGMENTED_V1"
SCOPE = "NUMERICAL_DIAGNOSTIC_ONLY"
FAILURE_TIME_S = 1.3587637114587e-11
STRIKE_TIME_S = 1.0e-10
CANONICAL_END_S = 2.1e-9
HEAVY_ION_BLOCK = (
    "HeavyIon(StartPoint=(3.22 2.1488228) Direction=(1 0) Length=70.77 "
    "Time=1e-10 LET_f=0.1555 Wt_hi=0.1 Gaussian PicoCoulomb)"
)
EXPECTED_HASHES = {
    "authorization": "55a3a83abba3a9d76e0a3c80e6d88015114dc42796887fdcd6e51b388a0b3c06",
    "binding_set": "a5f0194b3c15cefd10085fe43b4f1a96d435026f8e59293704cb77cbb86e644e",
    "parent_manifest": "3ff265f9a3209a595994acaa3cfa6e781160595b1247f3c8f8e2eb5039e0e336",
    "parent_restart_gate": "14ffeb5768d99f7eba6217ceab6069afc0a637051fe3f62c08383e11fb94202e",
    "parent_main": "401882ef499aa46b16c903538fe88a869f47f12b4e48962a3ef38eaead7ac146",
    "parent_circuit": "3f35a68b78eaacca5c4cc995ab0be8ddb49fbac9ded5e499a65e9851781fcba5",
    "mesh": "84d24e1dc14052ee3ef3525ced567ee9337c97ba0e5e55eefc1d0ddde09fd755",
    "parameter": "6aa6b189214b6b6342417a8f4b7a9b973e861c8dbb1a4186a537b41fa455f859",
    "failed_manifest": "0ca326d59718892676e84f73ca986026d34501ab4c6c7891f4c9f72ee21d8109",
    "failed_deck": "ffbeacca27490a80b0270cd49d41c05c7b5b28a9c9121fba4c099a138485c324",
    "failed_metadata": "0b007bc02c17940b74bbf3bf3b71bb2839d865f3d0320c69c53f29290fd08a28",
}
FLOAT = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?")
AUDIT_POINTS = (
    ("092ps", 9.2e-11), ("094ps", 9.4e-11), ("096ps", 9.6e-11), ("097ps", 9.7e-11),
    ("098ps", 9.8e-11), ("099ps", 9.9e-11), ("099p5ps", 9.95e-11), ("100ps", 1.0e-10),
    ("100p2ps", 1.002e-10), ("100p5ps", 1.005e-10), ("101ps", 1.01e-10),
    ("102ps", 1.02e-10), ("103ps", 1.03e-10), ("104ps", 1.04e-10),
    ("106ps", 1.06e-10), ("108ps", 1.08e-10),
)
STAGE_ORDER = ("P0", "P1", "P2", "P3")
STAGES: dict[str, dict[str, Any]] = {
    "P0": {
        "start_s": 0.0,
        "end_s": 1.5e-11,
        "checkpoint_prefix": "IGBT650_V400_recovery_p0_checkpoint",
        "final_plot_prefix": "IGBT650_V400_recovery_p0_at15ps",
        "segments": [
            (0.0, 1.2e-11, 1e-14, 1.15, 2.0, 1e-13, 1e-20, None, "IGBT650_V400_recovery_p0_at12ps"),
            (1.2e-11, 1.5e-11, 2e-15, 1.10, 2.0, 2e-14, 1e-20, 0.5, "IGBT650_V400_recovery_p0_at15ps"),
        ],
    },
    "P1": {
        "start_s": 1.5e-11,
        "end_s": 9.2e-11,
        "checkpoint_prefix": "IGBT650_V400_recovery_p1_checkpoint",
        "final_plot_prefix": "IGBT650_V400_recovery_p1_at92ps",
        "segments": [
            (1.5e-11, 2.0e-11, 2e-15, 1.10, 2.0, 2e-14, 1e-20, 0.5, "IGBT650_V400_recovery_p1_at20ps"),
            (2.0e-11, 5.0e-11, 2e-14, 1.20, 2.0, 2e-13, 1e-19, None, "IGBT650_V400_recovery_p1_at50ps"),
            (5.0e-11, 9.2e-11, 5e-14, 1.25, 2.0, 5e-13, 1e-19, None, "IGBT650_V400_recovery_p1_at92ps"),
        ],
    },
    "P2": {
        "start_s": 9.2e-11,
        "end_s": 1.08e-10,
        "checkpoint_prefix": "IGBT650_V400_recovery_p2_checkpoint",
        "final_plot_prefix": "IGBT650_V400_tr_audit_108ps",
        "segments": [],
    },
    "P3": {
        "start_s": 1.08e-10,
        "end_s": CANONICAL_END_S,
        "checkpoint_prefix": None,
        "final_plot_prefix": "IGBT650_V400_tr_at2p1ns",
        "segments": [
            (1.08e-10, CANONICAL_END_S, 2e-13, 1.35, 2.0, 1e-11, 1e-19, None, "IGBT650_V400_tr_at2p1ns"),
        ],
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")


def record(path: Path) -> dict[str, Any]:
    return {"path": relative(path), "sha256": sha256(path), "size_bytes": path.stat().st_size}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_new(path: Path, payload: str) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable recovery evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload.replace("\r\n", "\n"))


def expect_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"missing {label}: {path}")
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"{label} SHA-256 mismatch: expected {expected}, got {actual}")


def physical_sections(deck_text: str) -> str:
    return deck_text[deck_text.index("Electrode {"):deck_text.index("Math {")]


def parse_plt(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    info, data_text = text.split("Data {", 1)
    datasets_text = info.split("datasets", 1)[1].split("functions", 1)[0]
    names = re.findall(r'"([^"]+)"', datasets_text)
    values = [float(item) for item in FLOAT.findall(data_text.rsplit("}", 1)[0])]
    if not names or len(values) % len(names):
        raise ValueError(f"cannot parse complete PLT rows: {path}")
    rows = [values[index:index + len(names)] for index in range(0, len(values), len(names))]
    indexes = {name: names.index(name) for name in ("time", "Collector InnerVoltage", "Collector TotalCurrent", "Tmin", "Tave", "Tmax")}
    last = rows[-1]
    return {
        "sample_count": len(rows),
        "time_start_s": rows[0][indexes["time"]],
        "time_end_s": last[indexes["time"]],
        "collector_inner_voltage_v": last[indexes["Collector InnerVoltage"]],
        "collector_total_current_a_per_um": last[indexes["Collector TotalCurrent"]],
        "tmin_k": min(row[indexes["Tmin"]] for row in rows),
        "tmax_k": max(row[indexes["Tmax"]] for row in rows),
        "all_values_finite": all(math.isfinite(item) for row in rows for item in row),
    }


def validate_frozen_inputs() -> dict[str, Any]:
    checks = {
        "authorization": (AUTHORIZATION, EXPECTED_HASHES["authorization"]),
        "restart_binding_set": (BINDING_SET, EXPECTED_HASHES["binding_set"]),
        "parent_manifest": (PARENT_RUN / "run_manifest.json", EXPECTED_HASHES["parent_manifest"]),
        "parent_restart_gate": (PARENT_RUN / "restart_gate.json", EXPECTED_HASHES["parent_restart_gate"]),
        "parent_restart_main": (PARENT_MAIN, EXPECTED_HASHES["parent_main"]),
        "parent_restart_circuit": (PARENT_CIRCUIT, EXPECTED_HASHES["parent_circuit"]),
        "verified_mesh": (MESH, EXPECTED_HASHES["mesh"]),
        "sdevice_parameter": (PARAMETER, EXPECTED_HASHES["parameter"]),
        "failed_manifest": (FAILED_MANIFEST, EXPECTED_HASHES["failed_manifest"]),
        "failed_deck": (BASE_DECK, EXPECTED_HASHES["failed_deck"]),
        "failed_metadata": (BASE_METADATA, EXPECTED_HASHES["failed_metadata"]),
    }
    for label, (path, expected) in checks.items():
        expect_hash(path, expected, label)
    failed_manifest = read_json(FAILED_MANIFEST)
    parent_manifest = read_json(PARENT_RUN / "run_manifest.json")
    binding = read_json(BINDING_SET)
    claim_ledger = read_json(CLAIM_LEDGER)
    base_metadata = read_json(BASE_METADATA)
    base_deck = BASE_DECK.read_text(encoding="utf-8")
    failed_log = FAILED_LOG.read_text(encoding="utf-8", errors="replace")
    binding_record = next(
        item for item in binding["records"]
        if item["device_family"] == "IGBT" and int(item["bias_v"]) == 400
    )
    ledger_binding = claim_ledger["evidence_bindings"]["restart_binding_set"]
    ledger_failed = claim_ledger["evidence_bindings"]["igbt_400_transient_failed_manifest"]
    invariants = {
        "failed_run_id_exact": failed_manifest.get("run_id") == FAILED_RUN_ID,
        "failed_run_retained": FAILED_RUN.is_dir(),
        "failed_parent_exact": failed_manifest.get("parent_run_id") == PARENT_RUN_ID,
        "parent_succeeded": parent_manifest.get("run_id") == PARENT_RUN_ID and parent_manifest.get("lifecycle") == "SUCCEEDED",
        "parent_bias_exact": float(binding_record["actual_bias_v"]) == 400.0,
        "parent_main_exact": binding_record["restart_main"]["sha256"] == EXPECTED_HASHES["parent_main"],
        "parent_circuit_exact": binding_record["restart_circuit"]["sha256"] == EXPECTED_HASHES["parent_circuit"],
        "mesh_exact": binding_record["mesh_sha256"] == EXPECTED_HASHES["mesh"],
        "authorization_exact": binding.get("authorization_sha256") == EXPECTED_HASHES["authorization"],
        "binding_exact": ledger_binding["sha256"] == EXPECTED_HASHES["binding_set"],
        "failed_claim_unmodified": ledger_failed["sha256"] == EXPECTED_HASHES["failed_manifest"],
        "heavy_ion_block_exact": HEAVY_ION_BLOCK in base_deck,
        "bias_exact": 'Name="Collector" Voltage=0' in base_deck and 'Name="Gate" Voltage=0 Barrier=-0.5' in base_deck,
        "fully_coupled_exact": "Coupled { Poisson Electron Hole Temperature }" in base_deck,
        "strike_time_exact": float(base_metadata["strike_time_s"]) == STRIKE_TIME_S,
        "canonical_end_exact": float(base_metadata["total_time_s"]) == CANONICAL_END_S,
        "failure_signature_exact": (
            "Solution/update out of range for variable LatticeTemperature." in failed_log
            and "Step-size is too small." in failed_log
        ),
    }
    if not all(invariants.values()):
        failed = [name for name, passed in invariants.items() if not passed]
        raise ValueError("frozen-input verification failed: " + ", ".join(failed))
    return {
        "checks": invariants,
        "records": {label: record(path) for label, (path, _) in checks.items()},
        "failed_terminal": parse_plt(FAILED_PLT),
        "physical_sections_sha256": hashlib.sha256(physical_sections(base_deck).encode("utf-8")).hexdigest(),
    }


def transient_block(segment: tuple[Any, ...]) -> str:
    start, end, initial, increment, decrement, maximum, minimum, damping, plot_prefix = segment
    coupled = "Coupled(Iterations=100"
    if damping is not None:
        coupled += f" LineSearchDamping={damping:.8g}"
    coupled += ") { Poisson Electron Hole Temperature }"
    return (
        f"  Transient(InitialTime={start:.12g} FinalTime={end:.12g} InitialStep={initial:.12g} "
        f"Increment={increment:.8g} Decrement={decrement:.8g} MaxStep={maximum:.12g} MinStep={minimum:.12g}) {{\n"
        f"    {coupled}\n"
        "  }\n"
        f"  Plot(FilePrefix=\"{plot_prefix}\" NoOverwrite)\n"
    )


def p2_solve(load_prefix: str, checkpoint_prefix: str) -> str:
    lines = [
        f'  Load(FilePrefix="{load_prefix}")',
        '  Plot(FilePrefix="IGBT650_V400_tr_audit_092ps" NoOverwrite)',
        '  NewCurrentPrefix="IGBT650_V400_recovery_p2_"',
    ]
    for index in range(len(AUDIT_POINTS) - 1):
        _, start = AUDIT_POINTS[index]
        suffix, end = AUDIT_POINTS[index + 1]
        near_strike = 9.7e-11 <= start <= 1.02e-10
        initial = 2e-14 if near_strike else min(1e-13, (end - start) / 2)
        maximum = 5e-14 if near_strike else min(5e-13, end - start)
        damping = 0.5 if near_strike else None
        segment = (start, end, initial, 1.15, 2.0, maximum, 1e-20, damping, f"IGBT650_V400_tr_audit_{suffix}")
        lines.append(transient_block(segment).rstrip())
    lines.append(f'  Save(FilePrefix="{checkpoint_prefix}")')
    return "\n".join(lines) + "\n"


def render_deck(stage: str, load_prefix: str) -> str:
    base = BASE_DECK.read_text(encoding="utf-8")
    prefix = base.split("Math {", 1)[0]
    output = f"IGBT650_V400_recovery_{stage.lower()}"
    prefix = prefix.replace(
        'Plot="IGBT650_V400_transient" Current="IGBT650_V400_transient.plt" Output="IGBT650_V400_transient.log"',
        f'Plot="{output}" Current="{output}.plt" Output="{output}.log"',
    )
    prefix = prefix.replace("# generated;", f"# recovery_attempt profile={PROFILE} stage={stage};")
    math_block = (
        "Math { Extrapolate Transient=BE Iterations=100 Notdamped=0 Digits=5 "
        "ErrRef(Electron)=1e10 ErrRef(Hole)=1e10 ExitOnFailure "
        "BreakCriteria { LatticeTemperature(MaxVal=2500) } }\n"
    )
    checkpoint_prefix = STAGES[stage]["checkpoint_prefix"]
    solve = ["Solve {", f'  Load(FilePrefix="{load_prefix}")']
    if stage == "P0":
        solve.extend([
            '  Plot(FilePrefix="IGBT650_V400_tr_pre" NoOverwrite)',
            '  NewCurrentPrefix="IGBT650_V400_recovery_p0_"',
        ])
    elif stage != "P2":
        solve.append(f'  NewCurrentPrefix="IGBT650_V400_recovery_{stage.lower()}_"')
    if stage == "P2":
        solve_text = "Solve {\n" + p2_solve(load_prefix, checkpoint_prefix) + "}\n"
    else:
        for segment in STAGES[stage]["segments"]:
            solve.append(transient_block(segment).rstrip())
        if checkpoint_prefix:
            solve.append(f'  Save(FilePrefix="{checkpoint_prefix}")')
        solve.append("}")
        solve_text = "\n".join(solve) + "\n"
    rendered = prefix + math_block + solve_text
    if physical_sections(rendered) != physical_sections(base):
        raise ValueError("recovery deck changed a physical section")
    if rendered.count("Poisson Electron Hole Temperature") < 1 or HEAVY_ION_BLOCK not in rendered:
        raise ValueError("recovery deck lost full coupling or canonical HeavyIon block")
    return rendered


def numerical_delta(stage: str) -> dict[str, Any]:
    return {
        "allowed_axes_only": ["time_step", "nonlinear_iterations", "damping", "segmentation", "checkpoint", "output"],
        "time_integration": "BE_UNCHANGED",
        "global_iterations": {"from": 30, "to": 100},
        "notdamped": {"from": 50, "to": 0},
        "coupled_line_search_damping": "0.5 only in the controlled failure/strike neighborhoods",
        "stage_start_s": STAGES[stage]["start_s"],
        "stage_end_s": STAGES[stage]["end_s"],
        "segments": [
            {
                "initial_time_s": item[0], "final_time_s": item[1], "initial_step_s": item[2],
                "increment": item[3], "decrement": item[4], "max_step_s": item[5],
                "min_step_s": item[6], "line_search_damping": item[7], "plot_prefix": item[8],
            }
            for item in STAGES[stage]["segments"]
        ],
        "checkpoint_prefix": STAGES[stage]["checkpoint_prefix"],
        "canonical_chain_final_time_s": CANONICAL_END_S,
    }


def physical_invariance(freeze: dict[str, Any], rendered_deck: Path) -> dict[str, Any]:
    return {
        "status": "PASS",
        "canonical_heavy_ion_block": HEAVY_ION_BLOCK,
        "bias_v": 400.0,
        "fully_coupled_equations": ["Poisson", "Electron", "Hole", "Temperature"],
        "thermal_boundary": "Gate/Emitter/Collector Thermode Temperature=298.15 K unchanged",
        "canonical_strike_time_s": STRIKE_TIME_S,
        "canonical_chain_final_time_s": CANONICAL_END_S,
        "authorization_sha256": EXPECTED_HASHES["authorization"],
        "restart_binding_set_sha256": EXPECTED_HASHES["binding_set"],
        "parent_restart_main_sha256": EXPECTED_HASHES["parent_main"],
        "parent_restart_circuit_sha256": EXPECTED_HASHES["parent_circuit"],
        "mesh_sha256": EXPECTED_HASHES["mesh"],
        "sdevice_parameter_sha256": EXPECTED_HASHES["parameter"],
        "original_physical_sections_sha256": freeze["physical_sections_sha256"],
        "recovery_physical_sections_sha256": hashlib.sha256(
            physical_sections(rendered_deck.read_text(encoding="utf-8")).encode("utf-8")
        ).hexdigest(),
    }


def stage_metadata(
    attempt_id: str,
    stage: str,
    freeze: dict[str, Any],
    deck: Path,
    restart_main: Path,
    restart_circuit: Path,
    parent_run_id: str,
    previous_result: dict[str, Any] | None,
) -> dict[str, Any]:
    metadata = copy.deepcopy(read_json(BASE_METADATA))
    audit_tdrs = {
        f"{time_s:.12g}": f"IGBT650_V400_tr_audit_{suffix}_des.tdr"
        for suffix, time_s in AUDIT_POINTS
    } if stage == "P2" else {}
    metadata.update({
        "phase": f"igbt_400v_prestrike_recovery_{stage.lower()}",
        "termination_reason": "DIAGNOSTIC_PENDING",
        "scope": SCOPE,
        "recovery_attempt_id": attempt_id,
        "profile": PROFILE,
        "stage": stage,
        "stage_start_s": STAGES[stage]["start_s"],
        "stage_end_s": STAGES[stage]["end_s"],
        "total_time_s": STAGES[stage]["end_s"],
        "canonical_total_time_s": CANONICAL_END_S,
        "parent_restart_ids": [parent_run_id],
        "parent_restart_hashes": [sha256(restart_main), sha256(restart_circuit)],
        "parent_restart_main": record(restart_main),
        "parent_restart_circuit": record(restart_circuit),
        "parent_restart_actual_bias_v": 400.0,
        "heavy_ion_audit_tdrs": audit_tdrs,
        "exact_2p1ns_tdr": "IGBT650_V400_tr_at2p1ns_des.tdr" if stage == "P3" else None,
        "recovery_stage_tdr": f"{STAGES[stage]['final_plot_prefix']}_des.tdr",
        "expected_checkpoint_main_leaf": f"{STAGES[stage]['checkpoint_prefix']}_des.sav" if STAGES[stage]["checkpoint_prefix"] else None,
        "expected_checkpoint_circuit_leaf": f"{STAGES[stage]['checkpoint_prefix']}_circuit_des.sav" if STAGES[stage]["checkpoint_prefix"] else None,
        "physical_input_invariance": physical_invariance(freeze, deck),
        "numerical_delta": numerical_delta(stage),
        "physics_delta": [],
        "failure_signature": {
            "original_run_id": FAILED_RUN_ID,
            "time_s": FAILURE_TIME_S,
            "pre_strike": True,
            "signals": ["LatticeTemperature update out of range", "Step-size too small"],
            "interpretation": "NUMERICAL_PRESTRIKE_NOT_SEB",
        },
        "checkpoint_chain": {
            "original_parent_run_id": PARENT_RUN_ID,
            "original_parent_main_sha256": EXPECTED_HASHES["parent_main"],
            "original_parent_circuit_sha256": EXPECTED_HASHES["parent_circuit"],
            "previous_stage_result": previous_result,
        },
        "stage_gate": {
            "status": "DIAGNOSTIC_PENDING",
            "required_time_s": STAGES[stage]["end_s"],
            "must_cross_original_failure_time": stage == "P0",
            "requires_finite_terminal_and_temperature": True,
            "forbidden_signals": ["Solution/update out of range for variable LatticeTemperature.", "Step-size is too small."],
        },
        "source_failed_deck": freeze["records"]["failed_deck"],
        "source_failed_manifest": freeze["records"]["failed_manifest"],
        "recovery_deck": record(deck),
    })
    return metadata


def prepare_stage(
    attempt_root: Path,
    attempt_id: str,
    stage: str,
    freeze: dict[str, Any],
    restart_main: Path,
    restart_circuit: Path,
    parent_run_id: str,
    previous_result: dict[str, Any] | None,
) -> dict[str, Any]:
    stage_dir = attempt_root / "stage_inputs" / stage
    if stage_dir.exists():
        raise FileExistsError(f"stage input already exists: {stage_dir}")
    load_prefix = restart_main.name.removesuffix("_des.sav")
    deck = stage_dir / f"igbt_400_recovery_{stage.lower()}.cmd"
    write_new(deck, render_deck(stage, load_prefix))
    metadata_path = stage_dir / f"igbt_400_recovery_{stage.lower()}.json"
    metadata = stage_metadata(
        attempt_id, stage, freeze, deck, restart_main, restart_circuit, parent_run_id, previous_result
    )
    write_new(metadata_path, json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    stage_manifest = {
        "schema_version": "igbt_400v_recovery_stage_input/v1",
        "recovery_attempt_id": attempt_id,
        "profile": PROFILE,
        "scope": SCOPE,
        "stage": stage,
        "status": "DIAGNOSTIC_PENDING",
        "deck": record(deck),
        "metadata": record(metadata_path),
        "parameter": record(PARAMETER),
        "mesh": record(MESH),
        "restart_main": record(restart_main),
        "restart_circuit": record(restart_circuit),
        "parent_run_id": parent_run_id,
        "physical_input_invariance": metadata["physical_input_invariance"],
        "numerical_delta": metadata["numerical_delta"],
        "physics_delta": [],
        "failure_signature": metadata["failure_signature"],
        "checkpoint_chain": metadata["checkpoint_chain"],
        "stage_gate": metadata["stage_gate"],
    }
    stage_manifest_path = stage_dir / "stage_input_manifest.json"
    write_new(stage_manifest_path, json.dumps(stage_manifest, ensure_ascii=False, indent=2) + "\n")
    return {"stage_dir": str(stage_dir), "stage_manifest": record(stage_manifest_path)}


def prepare_attempt(args: argparse.Namespace) -> None:
    freeze = validate_frozen_inputs()
    attempt_id = args.attempt_id or (
        "igbt400_prestrike_thermal_v1__" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", attempt_id):
        raise ValueError("attempt ID must be portable")
    attempt_root = (args.output_root or (RUNTIME / "recovery")) / attempt_id
    if attempt_root.exists():
        raise FileExistsError(f"refusing existing recovery attempt: {attempt_root}")
    (attempt_root / "runs").mkdir(parents=True)
    (attempt_root / "stage_results").mkdir()
    p0 = prepare_stage(
        attempt_root, attempt_id, "P0", freeze, PARENT_MAIN, PARENT_CIRCUIT, PARENT_RUN_ID, None
    )
    manifest = {
        "schema_version": "igbt_400v_prestrike_recovery/v1",
        "recovery_attempt_id": attempt_id,
        "profile": PROFILE,
        "scope": SCOPE,
        "status": "DIAGNOSTIC_PENDING",
        "created_at": utc_now(),
        "original_failure_claim_immutable": True,
        "freeze_verification": freeze,
        "physical_input_invariance": read_json(ROOT / p0["stage_manifest"]["path"])["physical_input_invariance"],
        "numerical_delta": {stage: numerical_delta(stage) for stage in STAGE_ORDER},
        "physics_delta": [],
        "failure_signature": {
            "run_id": FAILED_RUN_ID,
            "time_s": FAILURE_TIME_S,
            "strike_time_s": STRIKE_TIME_S,
            "pre_strike": True,
            "signals": ["LatticeTemperature update out of range", "Step-size too small"],
            "interpretation": "NUMERICAL_PRESTRIKE_NOT_SEB",
        },
        "checkpoint_chain": [
            {"stage": "P0", "range_s": [0.0, 1.5e-11], "state": "DIAGNOSTIC_PENDING"},
            {"stage": "P1", "range_s": [1.5e-11, 9.2e-11], "state": "NOT_RUN"},
            {"stage": "P2", "range_s": [9.2e-11, 1.08e-10], "state": "NOT_RUN"},
            {"stage": "P3", "range_s": [1.08e-10, CANONICAL_END_S], "state": "NOT_RUN"},
        ],
        "stage_gate": {
            "P0": "must pass before P1+; cross 13.587637 ps with finite terminal/temperature and no forbidden signal",
            "P1": "must reach 92 ps before strike-window audit",
            "P2": "must preserve all 92-108 ps audit points before P3",
            "P3": "must reach exact 2.1 ns before existing extractor is allowed",
        },
        "stage_inputs": {"P0": p0["stage_manifest"]},
        "run_root": relative(attempt_root / "runs"),
    }
    manifest_path = attempt_root / "recovery_manifest.json"
    write_new(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"recovery_attempt_id={attempt_id}")
    print(f"attempt_root={attempt_root}")
    print(f"recovery_manifest_sha256={sha256(manifest_path)}")


def prepare_next(args: argparse.Namespace) -> None:
    attempt_root = args.attempt_root.resolve()
    manifest = read_json(attempt_root / "recovery_manifest.json")
    attempt_id = manifest["recovery_attempt_id"]
    stage = args.stage
    index = STAGE_ORDER.index(stage)
    if index == 0:
        raise ValueError("P0 is created with prepare")
    prior = STAGE_ORDER[index - 1]
    result_path = attempt_root / "stage_results" / f"{prior}.json"
    result = read_json(result_path)
    if result.get("status") != "PASSED_NUMERICAL_ONLY":
        raise ValueError(f"{stage} blocked: {prior} did not pass")
    run_dir = ROOT / result["run_manifest"]["path"]
    run_manifest = read_json(run_dir)
    restart_main = ROOT / result["checkpoint_main"]["path"]
    restart_circuit = ROOT / result["checkpoint_circuit"]["path"]
    freeze = validate_frozen_inputs()
    prepared = prepare_stage(
        attempt_root, attempt_id, stage, freeze, restart_main, restart_circuit,
        run_manifest["run_id"], record(result_path),
    )
    print(f"prepared_stage={stage}")
    print(f"stage_manifest={ROOT / prepared['stage_manifest']['path']}")


def artifact_by_suffix(run_dir: Path, suffix: str) -> Path | None:
    matches = sorted((run_dir / "artifacts").glob(f"*{suffix}"))
    return matches[0] if len(matches) == 1 else None


def audit_stage(args: argparse.Namespace) -> None:
    attempt_root = args.attempt_root.resolve()
    run_dir = args.run_dir.resolve()
    stage = args.stage
    validate_frozen_inputs()
    attempt_manifest = read_json(attempt_root / "recovery_manifest.json")
    stage_manifest_path = attempt_root / "stage_inputs" / stage / "stage_input_manifest.json"
    stage_manifest = read_json(stage_manifest_path)
    run_manifest_path = run_dir / "run_manifest.json"
    run_manifest = read_json(run_manifest_path)
    input_hashes = {Path(item["relative_path"]).name: item["sha256"] for item in run_manifest.get("inputs", [])}
    deck_name = Path(stage_manifest["deck"]["path"]).name
    metadata_name = Path(stage_manifest["metadata"]["path"]).name
    log_path = artifact_by_suffix(run_dir, ".log_des.log")
    plt_path = artifact_by_suffix(run_dir, ".plt")
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path else ""
    plt_summary = parse_plt(plt_path) if plt_path else None
    forbidden = {
        "lattice_temperature_out_of_range": "Solution/update out of range for variable LatticeTemperature." in log_text,
        "step_size_too_small": "Step-size is too small." in log_text,
        "exit_due_to_failure": "Exit due to failure" in log_text,
    }
    scheduler = run_manifest.get("scheduling_evidence", {})
    checks = {
        "attempt_id_bound": stage_manifest["recovery_attempt_id"] == attempt_manifest["recovery_attempt_id"],
        "stage_bound": stage_manifest["stage"] == stage,
        "deck_hash_bound": input_hashes.get(deck_name) == stage_manifest["deck"]["sha256"],
        "metadata_hash_bound": input_hashes.get(metadata_name) == stage_manifest["metadata"]["sha256"],
        "parameter_hash_invariant": input_hashes.get(PARAMETER.name) == EXPECTED_HASHES["parameter"],
        "mesh_hash_invariant": input_hashes.get(MESH.name) == EXPECTED_HASHES["mesh"],
        "physics_delta_empty": stage_manifest.get("physics_delta") == [],
        "lifecycle_succeeded": run_manifest.get("lifecycle") == "SUCCEEDED" and str(run_manifest.get("exit_code")) == "0",
        "auto_lease": scheduler.get("allocation_mode") == "AUTO_LEASE",
        "one_thread": scheduler.get("sdevice_threads") == 1,
        "lease_closed": scheduler.get("lease_acquired") is True and scheduler.get("lease_released") is True,
        "affinity_verified": scheduler.get("affinity_verification") == "VERIFIED",
        "plt_present": plt_summary is not None,
        "plt_reaches_stage_end": bool(plt_summary and math.isclose(
            plt_summary["time_end_s"], STAGES[stage]["end_s"], rel_tol=0.0, abs_tol=1e-16
        )),
        "all_values_finite": bool(plt_summary and plt_summary["all_values_finite"]),
        "collector_voltage_finite_400v": bool(
            plt_summary and math.isfinite(plt_summary["collector_inner_voltage_v"])
            and math.isclose(plt_summary["collector_inner_voltage_v"], 400.0, rel_tol=0.0, abs_tol=1e-6)
        ),
        "collector_current_finite": bool(plt_summary and math.isfinite(plt_summary["collector_total_current_a_per_um"])),
        "temperature_finite_in_range": bool(
            plt_summary and math.isfinite(plt_summary["tmin_k"]) and math.isfinite(plt_summary["tmax_k"])
            and 0.0 < plt_summary["tmin_k"] <= plt_summary["tmax_k"] < 2500.0
        ),
        "no_forbidden_failure_signal": not any(forbidden.values()),
    }
    if stage == "P0":
        checks["crossed_original_failure_time"] = bool(plt_summary and plt_summary["time_end_s"] > FAILURE_TIME_S)
        checks["remained_pre_strike"] = bool(plt_summary and plt_summary["time_end_s"] < STRIKE_TIME_S)
    checkpoint_main = None
    checkpoint_circuit = None
    if STAGES[stage]["checkpoint_prefix"]:
        checkpoint_main = run_dir / "artifacts" / f"{STAGES[stage]['checkpoint_prefix']}_des.sav"
        checkpoint_circuit = run_dir / "artifacts" / f"{STAGES[stage]['checkpoint_prefix']}_circuit_des.sav"
        checks["checkpoint_main_present"] = checkpoint_main.is_file()
        checks["checkpoint_circuit_present"] = checkpoint_circuit.is_file()
    stage_tdr = run_dir / "artifacts" / f"{STAGES[stage]['final_plot_prefix']}_des.tdr"
    checks["stage_tdr_present"] = stage_tdr.is_file()
    status = "PASSED_NUMERICAL_ONLY" if all(checks.values()) else "FAILED_NUMERICAL_ONLY"
    result: dict[str, Any] = {
        "schema_version": "igbt_400v_recovery_stage_result/v1",
        "recovery_attempt_id": attempt_manifest["recovery_attempt_id"],
        "profile": PROFILE,
        "scope": SCOPE,
        "stage": stage,
        "status": status,
        "audited_at": utc_now(),
        "run_id": run_manifest.get("run_id"),
        "run_manifest": record(run_manifest_path),
        "stage_input_manifest": record(stage_manifest_path),
        "checks": checks,
        "scheduler_evidence": scheduler,
        "plt_summary": plt_summary,
        "failure_signals": forbidden,
        "log": record(log_path) if log_path else None,
        "plt": record(plt_path) if plt_path else None,
        "stage_tdr": record(stage_tdr) if stage_tdr.is_file() else None,
        "physical_input_invariance": stage_manifest["physical_input_invariance"],
        "numerical_delta": stage_manifest["numerical_delta"],
        "physics_delta": [],
        "failure_signature": stage_manifest["failure_signature"],
        "checkpoint_chain": stage_manifest["checkpoint_chain"],
        "stage_gate": {
            "status": status,
            "pass_is_numerical_only": True,
            "seb_conclusion_allowed": False,
        },
    }
    if checkpoint_main and checkpoint_main.is_file():
        result["checkpoint_main"] = record(checkpoint_main)
    if checkpoint_circuit and checkpoint_circuit.is_file():
        result["checkpoint_circuit"] = record(checkpoint_circuit)
    result_path = attempt_root / "stage_results" / f"{stage}.json"
    write_new(result_path, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"stage={stage} status={status}")
    print(f"stage_result={result_path}")
    if plt_summary:
        print(
            f"time_end_s={plt_summary['time_end_s']:.15g} collector_v={plt_summary['collector_inner_voltage_v']:.15g} "
            f"collector_i_a_um={plt_summary['collector_total_current_a_per_um']:.15g} tmax_k={plt_summary['tmax_k']:.15g}"
        )
    if status != "PASSED_NUMERICAL_ONLY":
        raise SystemExit(2)


def verify_attempt(args: argparse.Namespace) -> None:
    validate_frozen_inputs()
    attempt_root = args.attempt_root.resolve()
    manifest_path = attempt_root / "recovery_manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("scope") != SCOPE or manifest.get("physics_delta") != []:
        raise ValueError("recovery manifest scope or physics delta is invalid")
    for stage_dir in sorted((attempt_root / "stage_inputs").glob("P*")):
        stage_manifest_path = stage_dir / "stage_input_manifest.json"
        stage_manifest = read_json(stage_manifest_path)
        for key in ("deck", "metadata", "parameter", "mesh", "restart_main", "restart_circuit"):
            item = stage_manifest[key]
            path = ROOT / item["path"]
            if not path.is_file() or sha256(path) != item["sha256"] or path.stat().st_size != item["size_bytes"]:
                raise ValueError(f"stage binding mismatch: {stage_dir.name}:{key}")
        if stage_manifest.get("physics_delta") != []:
            raise ValueError(f"nonempty physics delta: {stage_dir.name}")
    print(f"verified_attempt={manifest['recovery_attempt_id']} manifest_sha256={sha256(manifest_path)}")


def close_attempt(args: argparse.Namespace) -> None:
    attempt_root = args.attempt_root.resolve()
    attempt_manifest_path = attempt_root / "recovery_manifest.json"
    attempt_manifest = read_json(attempt_manifest_path)
    p0_path = attempt_root / "stage_results" / "P0.json"
    p0 = read_json(p0_path)
    run_manifest = read_json(ROOT / p0["run_manifest"]["path"])
    log_path = ROOT / p0["log"]["path"]
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    attempted_steps = [float(item) for item in re.findall(r"Stepsize: ([0-9.eE+-]+) s", log_text)]
    attempted_ranges = re.findall(
        r"Computing BE-step from ([0-9.eE+-]+) s to ([0-9.eE+-]+) s", log_text
    )
    claim_ledger = read_json(CLAIM_LEDGER)
    original_claim = next(
        item for item in claim_ledger["claims"] if item["claim_id"] == "let15_reference_transient_gate"
    )
    frozen_after = validate_frozen_inputs()
    closure = {
        "schema_version": "igbt_400v_prestrike_recovery_closure/v1",
        "recovery_attempt_id": attempt_manifest["recovery_attempt_id"],
        "profile": PROFILE,
        "scope": SCOPE,
        "status": p0["status"],
        "closed_at": utc_now(),
        "earliest_auditable_stage": "P0",
        "stage_status": {
            "P0": p0["status"],
            "P1": "NOT_RUN",
            "P2": "NOT_RUN",
            "P3": "NOT_RUN",
        },
        "stop_rule": "P0 failed; P1/P2/P3 and the existing 2.1 ns extractor are prohibited",
        "original_failure_claim": {
            "claim_id": original_claim["claim_id"],
            "status": original_claim["status"],
            "run_id": original_claim["failed_run_id"],
            "manifest_sha256": EXPECTED_HASHES["failed_manifest"],
            "deck_sha256": EXPECTED_HASHES["failed_deck"],
            "retained_independently": True,
            "not_reinterpreted_as_seb": True,
        },
        "recovery_run": {
            "run_id": p0["run_id"],
            "run_manifest": p0["run_manifest"],
            "lifecycle": run_manifest["lifecycle"],
            "exit_code": run_manifest["exit_code"],
            "wall_time_seconds": run_manifest["wall_time_seconds"],
            "scheduler_evidence": p0["scheduler_evidence"],
            "last_accepted_time_s": p0["plt_summary"]["time_end_s"],
            "last_accepted_time_ps": p0["plt_summary"]["time_end_s"] * 1e12,
            "crossed_original_failure_time": p0["checks"]["crossed_original_failure_time"],
            "reached_p0_target_15ps": p0["checks"]["plt_reaches_stage_end"],
            "collector_inner_voltage_v": p0["plt_summary"]["collector_inner_voltage_v"],
            "collector_total_current_a_per_um": p0["plt_summary"]["collector_total_current_a_per_um"],
            "tmax_k": p0["plt_summary"]["tmax_k"],
            "all_terminal_and_temperature_values_finite": p0["plt_summary"]["all_values_finite"],
            "lattice_temperature_out_of_range_count": log_text.count(
                "Solution/update out of range for variable LatticeTemperature."
            ),
            "minimum_attempted_step_s": min(attempted_steps) if attempted_steps else None,
            "last_attempted_step_range_s": [float(item) for item in attempted_ranges[-1]] if attempted_ranges else None,
            "step_size_too_small_observed": "Step-size is too small." in log_text,
            "termination": "FAIL_CLOSED_INTERRUPT_AFTER_REPEATED_FORBIDDEN_SIGNAL_AND_ASYMPTOTIC_PROGRESS",
            "checkpoint_main_present": p0["checks"]["checkpoint_main_present"],
            "checkpoint_circuit_present": p0["checks"]["checkpoint_circuit_present"],
            "stage_tdr_present": p0["checks"]["stage_tdr_present"],
            "plt": p0["plt"],
            "log": p0["log"],
        },
        "physical_input_invariance": p0["physical_input_invariance"],
        "numerical_delta": p0["numerical_delta"],
        "physics_delta": [],
        "failure_signature": p0["failure_signature"],
        "checkpoint_chain": {
            "P0": "FAILED_NUMERICAL_ONLY; no checkpoint produced",
            "P1": "NOT_RUN",
            "P2": "NOT_RUN",
            "P3": "NOT_RUN",
        },
        "stage_gate": p0["stage_gate"],
        "hash_invariance_postrun": frozen_after["checks"],
        "sibling_reference_runs_preserved": original_claim["sibling_success_run_ids"],
        "preflight": {
            "sentaurus_release": "W-2024.09",
            "license_server": "UP",
            "vendor_daemon": "UP",
            "online_cores": 24,
            "lease_count_before": 0,
            "unmanaged_sdevice_observed": {"pid": 12620, "core": 1, "action": "left untouched"},
        },
        "postrun": {
            "lease_count": 0,
            "recovery_process_present": False,
            "unmanaged_sdevice_pid_12620_left_untouched": True,
        },
        "campaign_summary_run": False,
        "extractor_run": False,
        "seb_conclusion_allowed": False,
    }
    closure_path = attempt_root / "recovery_closure.json"
    write_new(closure_path, json.dumps(closure, ensure_ascii=False, indent=2) + "\n")
    lightweight_path = REPORT_DATA / "igbt_400v_prestrike_recovery.json"
    write_new(lightweight_path, json.dumps(closure, ensure_ascii=False, indent=2) + "\n")
    print(f"closure_status={closure['status']}")
    print(f"closure={closure_path}")
    print(f"lightweight_evidence={lightweight_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--attempt-id")
    prepare_parser.add_argument("--output-root", type=Path)
    next_parser = subparsers.add_parser("prepare-next")
    next_parser.add_argument("--attempt-root", type=Path, required=True)
    next_parser.add_argument("--stage", choices=STAGE_ORDER[1:], required=True)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--attempt-root", type=Path, required=True)
    audit_parser.add_argument("--stage", choices=STAGE_ORDER, required=True)
    audit_parser.add_argument("--run-dir", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--attempt-root", type=Path, required=True)
    close_parser = subparsers.add_parser("close")
    close_parser.add_argument("--attempt-root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare_attempt(args)
    elif args.command == "prepare-next":
        prepare_next(args)
    elif args.command == "audit":
        audit_stage(args)
    elif args.command == "close":
        close_attempt(args)
    else:
        verify_attempt(args)


if __name__ == "__main__":
    main()
