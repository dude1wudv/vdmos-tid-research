#!/usr/bin/env python3
"""Generate the locked LET/initial-state transient input matrix."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "local_runtime/igbt_seb_thermal_runs/A01_v2500_let15_y3p5_thermal__R1_thermo_coupled_to60__20260713T064449946Z__1d9cd23a/inputs/r1_thermo_coupled_to60.cmd"
OUT = ROOT / "local_runtime/igbt_seb_let_scan_inputs/transient_matrix"

CASES = (
    ("A01_v2500_let0p015_y3p5_thermal", 0.015, "0.0001555", "thermal-steady", "r1_bias2500"),
    ("A01_v2500_let0p015_y3p5_cold300", 0.015, "0.0001555", "cold300", "bias2500_cold300"),
    ("A01_v2500_let0p15_y3p5_thermal", 0.15, "0.001555", "thermal-steady", "r1_bias2500"),
    ("A01_v2500_let0p15_y3p5_cold300", 0.15, "0.001555", "cold300", "bias2500_cold300"),
    ("A01_v2500_let1p5_y3p5_thermal", 1.5, "0.01555", "thermal-steady", "r1_bias2500"),
    ("A01_v2500_let1p5_y3p5_cold300", 1.5, "0.01555", "cold300", "bias2500_cold300"),
    ("A01_v2500_let150_y3p5_thermal", 150.0, "1.555", "thermal-steady", "r1_bias2500"),
    ("A01_v2500_let150_y3p5_cold300", 150.0, "1.555", "cold300", "bias2500_cold300"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output_deck(source: str, case_id: str, let_f: str, restart: str) -> str:
    text = source.replace("LET_f=0.1555", f"LET_f={let_f}")
    text = text.replace('Load(FilePrefix="r1_bias2500")', f'Load(FilePrefix="{restart}")')
    text = text.replace('Plot = "r1_coupled"', f'Plot = "{case_id}"')
    text = text.replace('Current = "r1_coupled.plt"', f'Current = "{case_id}.plt"')
    text = text.replace('Output = "r1_coupled.log"', f'Output = "{case_id}.log"')
    text = text.replace('NewCurrentPrefix="transient_"', f'NewCurrentPrefix="{case_id}_transient_"')
    for name in ("field_pre", "strike", "checkpoint_0p4ns", "field_0p4ns", "checkpoint_10ns", "field_10ns", "checkpoint_40ns", "field_40ns", "checkpoint_50ns", "field_50ns", "checkpoint_60ns", "field_60ns"):
        text = text.replace(f'FilePrefix="{name}"', f'FilePrefix="{case_id}_{name}"')
    return text


def normalized(text: str) -> str:
    for _, _, let_f, _, _ in CASES:
        text = text.replace(f"LET_f={let_f}", "LET_f=LET_F")
    for case_id, _, _, _, restart in CASES:
        text = text.replace(case_id, "OUTPUT_PREFIX")
        text = text.replace(restart, "RESTART_PREFIX")
    return text


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = SOURCE.read_text(encoding="utf-8")
    audit = []
    for case_id, let, let_f, initial, restart in CASES:
        deck = output_deck(source, case_id, let_f, restart)
        deck_path = OUT / f"{case_id}.cmd"
        metadata_path = OUT / f"{case_id}.json"
        deck_path.write_text(deck, encoding="utf-8")
        metadata = {
            "case_id": case_id,
            "let_mev_cm2_mg": let,
            "let_pc_um": float(let_f),
            "initial_state": initial,
            "restart_prefix": restart,
            "target_vce_v": 2500,
            "y_um": 3.5,
            "time_end_s": 6e-8,
            "threads": 1,
            "timeout_seconds": 7200,
            "control": "Locked R1 mesh, sdevice.par, physical models, and transient timesteps; only LET_f, case output prefixes, restart prefix, and case identity vary.",
        }
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        audit.append({"case_id": case_id, "let_f_pc_um": let_f, "initial_state": initial, "restart_prefix": restart, "deck_sha256": sha256(deck_path), "normalized_control_sha256": hashlib.sha256(normalized(deck).encode()).hexdigest()})
    (OUT / "input_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(f"generated {len(audit)} locked transient decks in {OUT}")


if __name__ == "__main__":
    main()