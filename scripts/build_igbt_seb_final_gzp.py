#!/usr/bin/env python3
"""Build and verify the 2026-07-14 IGBT continuation Workbench package.

Run this script on the Sentaurus W-2024.09 VM.  It uses only the uploaded
20260714 frozen inputs, the matching campaign run artifacts, and the installed
Workbench metadata scaffold.
"""

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SENTAURUS = Path("/usr/synopsys/sentaurus/W-2024.09")
SWBPACK = SENTAURUS / "bin/swbpack"
SWBUNPACK = SENTAURUS / "bin/swbunpack"
SVISUAL = SENTAURUS / "bin/svisual"
TEMPLATE = SENTAURUS / "tcad/W-2024.09/Applications_Library/Power/IGBT"
PROJECT_NAME = "IGBT_SEB_20260714_Final_Continuation"
REFERENCE_DC = "IGBT_T298_V550_L15__dc_restart_attempt04__20260715T055202345Z__7c92e3af"
REFERENCE_TR = "IGBT_T298_V550_L15__transient_reference_attempt01__20260715T064159391Z__27ebb6c0"
MAIN_RUNS = [
    ("IGBT_T243_V550_L15", "IGBT_T243_V550_L15__dc_restart_attempt01__20260715T055528829Z__ab401cf2", "IGBT_T243_V550_L15__transient_main_attempt01__20260715T073055448Z__ce237df1"),
    ("IGBT_T298_V550_L15", REFERENCE_DC, REFERENCE_TR),
    ("IGBT_T323_V550_L15", "IGBT_T323_V550_L15__dc_restart_attempt01__20260715T055528981Z__1784234f", "IGBT_T323_V550_L15__transient_main_attempt01__20260715T073055446Z__1743d2d6"),
    ("IGBT_T343_V550_L15", "IGBT_T343_V550_L15__dc_restart_attempt01__20260715T061031255Z__54f3755e", "IGBT_T343_V550_L15__transient_main_attempt01__20260715T073056172Z__3fc3458d"),
    ("IGBT_T298_V500_L15", "IGBT_T298_V500_L15__dc_restart_attempt01__20260715T061031460Z__709b2f1b", "IGBT_T298_V500_L15__transient_main_attempt01__20260715T073057018Z__e24123f9"),
    ("IGBT_T298_V525_L15", "IGBT_T298_V525_L15__dc_restart_attempt02__20260715T062437991Z__21563ff8", "IGBT_T298_V525_L15__transient_main_attempt01__20260715T075808233Z__eed4a67f"),
    ("IGBT_T298_V575_L15", "IGBT_T298_V575_L15__dc_restart_attempt02__20260715T062438172Z__52a7d779", "IGBT_T298_V575_L15__transient_main_attempt01__20260715T075808358Z__476c3ce1"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy(source, target):
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {"relative_path": target.name, "size_bytes": target.stat().st_size, "sha256": sha256(target)}


def run(command, *, cwd=None):
    result = subprocess.run(command, cwd=cwd, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}")
    return result


def sanitize_json_value(value):
    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        normalized = normalized.replace("E:/VDMOS_TID_Research/", "<repository_root>/")
        normalized = normalized.replace(
            "/home/tcad/codex_runs/igbt_mosfet_seb_paper_20260714/",
            "<campaign_fact_source>/",
        )
        return normalized
    return value


def write_sanitized_json(source, target):
    data = json.loads(source.read_text(encoding="utf-8"))
    target.write_text(json.dumps(sanitize_json_value(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def artifact(manifest, leaf):
    matches = [row for row in manifest["artifacts"] if Path(row["relative_path"]).name == leaf]
    if len(matches) != 1:
        raise RuntimeError(f"expected one artifact {leaf}, found {len(matches)}")
    return matches[0]


def input_record(manifest, leaf):
    matches = [row for row in manifest["inputs"] if Path(row["relative_path"]).name == leaf]
    if len(matches) != 1:
        raise RuntimeError(f"expected one input {leaf}, found {len(matches)}")
    return matches[0]


def write_tree(path: Path) -> None:
    path.write_text(
        "# Copyright (C) 1994-2024 Synopsys Inc.\n"
        "# 20260714 IGBT continuation project; fixed 298.15 K / 550 V reference path.\n\n"
        "# --- simulation flow\n"
        "IGBT_Structure sde \"\" {}\n"
        "ThermalRestart sdevice \"\" {}\n"
        "HeavyIon sdevice \"\" {}\n"
        "View_2ns svisual \"\" {}\n"
        "Extract_Results svisual \"\" {}\n"
        "# --- variables\n"
        "# --- scenarios and parameter specs\n"
        "# --- simulation tree\n"
        "0 1 0 {} {default} 0\n"
        "1 2 1 {} {default} 0\n"
        "2 3 2 {} {default} 0\n"
        "3 4 3 {} {default} 0\n"
        "4 5 3 {} {default} 0\n",
        encoding="utf-8",
    )


def adapt_sde(text: str) -> str:
    return (
        text.replace('"igbt_baseline_bnd.tdr"', '"@tdrboundary/o@"')
        .replace('"igbt_baseline_msh.cmd"', '"@commands/o@"')
        .replace("snmesh -offset igbt_baseline_msh", "snmesh -offset n@node@_msh")
    )


def adapt_dc(text: str) -> str:
    replacements = {
        'Grid = "igbt_baseline_msh.tdr"': 'Grid = "@tdr@"',
        'Plot = "IGBT_T298_V550_L15_dc"': 'Plot = "n@node@"',
        'Current = "IGBT_T298_V550_L15_dc.plt"': 'Current = "n@node@_des.plt"',
        'Output = "IGBT_T298_V550_L15_dc.log"': 'Output = "n@node@_des.log"',
        'Save(FilePrefix="IGBT_T298_V550_L15_restart")': 'Save(FilePrefix="n@node@_restart")',
        'Plot(FilePrefix="IGBT_T298_V550_L15_dc_pre"': 'Plot(FilePrefix="n@node@_pre"',
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"DC adaptation anchor missing: {old}")
        text = text.replace(old, new)
    return text


def adapt_transient(text: str) -> str:
    replacements = {
        'Grid = "igbt_baseline_msh.tdr"': 'Grid = "n1_msh.tdr"',
        'Plot = "IGBT_T298_V550_L15_tr"': 'Plot = "n@node@"',
        'Current = "IGBT_T298_V550_L15_tr.plt"': 'Current = "n@node@_des.plt"',
        'Output = "IGBT_T298_V550_L15_tr.log"': 'Output = "n@node@_des.log"',
        'Load(FilePrefix="IGBT_T298_V550_L15_restart")': 'Load(FilePrefix="n2_restart")',
        'IGBT_T298_V550_L15_tr_': 'n@node@_',
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"transient adaptation anchor missing: {old}")
        text = text.replace(old, new)
    return text


def make_project(output_root, upload, campaign):
    project = output_root / "project" / PROJECT_NAME
    project.mkdir(parents=True)
    for name in (".project", ".database", ".organization", "gcomments.dat", "gtooldb.tcl"):
        copy(TEMPLATE / name, project / name)
    write_tree(project / "gtree.dat")
    (project / "gvars.dat").touch()
    (project / "gadvscens.dat").touch()

    runtime_inputs = upload / "runtime_inputs"
    source_sde = runtime_inputs / "sde/igbt_baseline_sde.cmd"
    source_dc = runtime_inputs / "cases/IGBT_T298_V550_L15/IGBT_T298_V550_L15_dc.cmd"
    source_tr = runtime_inputs / "cases/IGBT_T298_V550_L15/IGBT_T298_V550_L15_transient.cmd"
    (project / "IGBT_Structure_dvs.cmd").write_text(adapt_sde(source_sde.read_text(encoding="utf-8")), encoding="utf-8")
    (project / "ThermalRestart_des.cmd").write_text(adapt_dc(source_dc.read_text(encoding="utf-8")), encoding="utf-8")
    (project / "HeavyIon_des.cmd").write_text(adapt_transient(source_tr.read_text(encoding="utf-8")), encoding="utf-8")
    (project / "IGBT_Structure_dvs.prf").write_text("set WB_tool(sde,parallel,activate) 1\n", encoding="utf-8")
    for name in ("ThermalRestart_des.prf", "HeavyIon_des.prf"):
        (project / name).write_text("set WB_tool(sdevice,input,parameter,common) 1\nset WB_tool(sdevice,parallel,activate) 1\n", encoding="utf-8")
    for name in ("View_2ns_vis.prf", "Extract_Results_vis.prf"):
        (project / name).write_text("set WB_tool(svisual,exec_mode) batch\nset WB_tool(svisual,parallel,activate) 1\n", encoding="utf-8")
    (project / "View_2ns_vis.tcl").write_text(
        "#setdep @previous@\n"
        "load_file n3_des.tdr -name Final2ns\n"
        "create_plot -name IGBT_2ns_Field -dataset Final2ns\n"
        "select_plots IGBT_2ns_Field\n"
        "set_field_prop -plot IGBT_2ns_Field -geom Final2ns LatticeTemperature -show -show_bands -levels 30\n"
        "puts \"IGBT_20260714_VIEW_OK input=n3_des.tdr field=LatticeTemperature\"\n",
        encoding="utf-8",
    )
    (project / "Extract_Results_vis.tcl").write_text(
        "#setdep @previous@\n"
        "load_file n3_des.plt -name FinalCurve\n"
        "set vars [list_variables -dataset FinalCurve]\n"
        "puts \"IGBT_20260714_EXTRACT_OK input=n3_des.plt variables=$vars\"\n",
        encoding="utf-8",
    )

    manifests = upload / "run_manifests"
    dc_manifest = json.loads((manifests / f"{REFERENCE_DC}.json").read_text(encoding="utf-8"))
    tr_manifest = json.loads((manifests / f"{REFERENCE_TR}.json").read_text(encoding="utf-8"))
    if dc_manifest["lifecycle"] != "SUCCEEDED" or tr_manifest["lifecycle"] != "SUCCEEDED":
        raise RuntimeError("reference run did not succeed")
    reference_sources = [
        (campaign / "mesh_attempt_20260714T133954/igbt_baseline_msh.tdr", project / "n1_msh.tdr", input_record(dc_manifest, "igbt_baseline_msh.tdr")),
        (campaign / REFERENCE_DC / "inputs/IGBT_T298_V550_L15_restart_des.sav", project / "n2_restart_des.sav", artifact(dc_manifest, "IGBT_T298_V550_L15_restart_des.sav")),
        (campaign / REFERENCE_DC / "inputs/IGBT_T298_V550_L15_restart_circuit_des.sav", project / "n2_restart_circuit_des.sav", artifact(dc_manifest, "IGBT_T298_V550_L15_restart_circuit_des.sav")),
        (campaign / REFERENCE_TR / "inputs/IGBT_T298_V550_L15_tr_at2p1ns_des.tdr", project / "n3_des.tdr", artifact(tr_manifest, "IGBT_T298_V550_L15_tr_at2p1ns_des.tdr")),
        (campaign / REFERENCE_TR / "inputs/IGBT_T298_V550_L15_tr_transient_IGBT_T298_V550_L15_tr.plt", project / "n3_des.plt", artifact(tr_manifest, "IGBT_T298_V550_L15_tr_transient_IGBT_T298_V550_L15_tr.plt")),
    ]
    copied_reference = []
    for source, target, expected in reference_sources:
        record = copy(source, target)
        if record["sha256"] != expected["sha256"] or record["size_bytes"] != expected["size_bytes"]:
            raise RuntimeError(f"reference artifact mismatch: {source.name}")
        copied_reference.append({"role": target.name, **record})
    copy(runtime_inputs / "sdevice.par", project / "sdevice.par")

    metadata = project / "delivery_metadata"
    metadata.mkdir()
    rows = []
    for case_id, dc_run, tr_run in MAIN_RUNS:
        dc = json.loads((manifests / f"{dc_run}.json").read_text(encoding="utf-8"))
        tr = json.loads((manifests / f"{tr_run}.json").read_text(encoding="utf-8"))
        exact = artifact(tr, tr["exact_2p1ns_tdr"])
        curve = next(row for row in tr["artifacts"] if str(row["relative_path"]).endswith(".plt"))
        rows.append({
            "case_id": case_id,
            "dc_run_id": dc_run,
            "transient_run_id": tr_run,
            "dc_status": dc["lifecycle"],
            "transient_status": tr["lifecycle"],
            "mesh_sha256": input_record(dc, "igbt_baseline_msh.tdr")["sha256"],
            "restart_sha256": artifact(dc, f"{case_id}_restart_des.sav")["sha256"],
            "exact_2p1ns_tdr_sha256": exact["sha256"],
            "transient_plt_sha256": curve["sha256"],
        })
    with (metadata / "igbt_main_run_index.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (metadata / "igbt_main_run_index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for source_name in ("case_acceptance.csv", "mesh_track_refined_comparison.csv"):
        copy(upload / "formal_data" / source_name, metadata / source_name)
    write_sanitized_json(
        upload / "formal_data" / "mesh_track_refined_comparison.json",
        metadata / "mesh_track_refined_comparison.json",
    )
    for case_id, _, _ in MAIN_RUNS:
        for suffix in ("_2ns.json", "_2ns_fields.csv", "_dc_gate.json"):
            source = upload / "extracts" / f"{case_id}{suffix}"
            if source.is_file():
                target = metadata / source.name
                if source.suffix == ".json":
                    write_sanitized_json(source, target)
                else:
                    copy(source, target)

    manifest = {
        "schema": "igbt_seb_20260714_final_continuation/v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "project": PROJECT_NAME,
        "sentaurus_release": "W-2024.09",
        "physical_baseline": "451.15 um historical IGBT model",
        "main_case_count": 7,
        "reference_case": "IGBT_T298_V550_L15",
        "reference_dc_run_id": REFERENCE_DC,
        "reference_transient_run_id": REFERENCE_TR,
        "nodes": ["IGBT_Structure", "ThermalRestart", "HeavyIon", "View_2ns", "Extract_Results"],
        "reference_assets": copied_reference,
        "claim_boundary": "四温度和所列偏压案例跑通；298.15 K/550 V baseline 与一次 track-refined 局部网格门通过",
        "not_claimed": ["strict global temperature convergence", "strict global mesh convergence", "SEB threshold", "commercial 650 V proof"],
        "redesign_650v_status": "PENDING",
        "low_let_status": "diagnostic_only/MESH_SENSITIVE",
        "mosfet_role": "appendix only",
    }
    (metadata / "package_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (project / "README_PROJECT.md").write_text(
        "# IGBT SEB 20260714 可继续仿真工程\n\n"
        "主线节点：`IGBT_Structure → ThermalRestart → HeavyIon → {View_2ns, Extract_Results}`。"
        "包内保留 298.15 K/550 V 已验证网格、热稳态 restart 和 2.1 ns 参考输出；修改结构后必须串行重建网格和 restart。\n\n"
        "结论边界：四温度和所列偏压案例跑通；298.15 K/550 V baseline 与一次 track-refined 局部网格门通过。"
        "这不是严格全局温度/网格收敛、SEB 阈值或商用 650 V 证明；650 V 重设计仍为 PENDING。\n",
        encoding="utf-8",
    )
    package = output_root / f"{PROJECT_NAME}.gzp"
    run([str(SWBPACK), "-Z", "-C", str(project.parent), str(package), project.name])
    return project, package, manifest


def verify(output_root, project, package, manifest):
    magic = package.read_bytes()[:4].hex()
    if magic != "1f8b0800":
        raise RuntimeError(f"unexpected gzip magic: {magic}")
    listing = run([str(SWBUNPACK), "-t", str(package)]).stdout
    required = [f"{PROJECT_NAME}/gtree.dat", f"{PROJECT_NAME}/HeavyIon_des.cmd", f"{PROJECT_NAME}/n2_restart_des.sav", f"{PROJECT_NAME}/n3_des.tdr"]
    missing = [name for name in required if name not in listing]
    if missing:
        raise RuntimeError(f"package index missing: {missing}")
    unpack_root = output_root / "unpack_validation"
    unpack_root.mkdir()
    run([str(SWBUNPACK), "-d", str(unpack_root), str(package)])
    unpacked = unpack_root / PROJECT_NAME
    for name in required:
        relative = Path(name).relative_to(PROJECT_NAME)
        if not (unpacked / relative).is_file():
            raise RuntimeError(f"unpacked file missing: {relative}")
    view = run([str(SVISUAL), "-bx", "-script", "View_2ns_vis.tcl"], cwd=unpacked)
    extract = run([str(SVISUAL), "-bx", "-script", "Extract_Results_vis.tcl"], cwd=unpacked)
    checks = {
        "schema": "igbt_seb_gzp_verification/v1",
        "package": package.name,
        "package_size_bytes": package.stat().st_size,
        "package_sha256": sha256(package),
        "magic_hex": magic,
        "swbpack": "PASS",
        "internal_index": "PASS",
        "swbunpack_fresh_directory": "PASS",
        "svisual_view_probe": "PASS" if "IGBT_20260714_VIEW_OK" in view.stdout else "FAIL",
        "svisual_extract_probe": "PASS" if "IGBT_20260714_EXTRACT_OK" in extract.stdout else "FAIL",
        "project_root": project.name,
        "unpacked_project_root": unpacked.name,
        "main_case_count": manifest["main_case_count"],
    }
    if "FAIL" in checks.values():
        raise RuntimeError("SVisual probe failed")
    (output_root / "package_index.txt").write_text(listing, encoding="utf-8")
    (output_root / "view_probe.log").write_text(view.stdout, encoding="utf-8")
    (output_root / "extract_probe.log").write_text(extract.stdout, encoding="utf-8")
    (output_root / "gzp_verification.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--uploaded-input-root", type=Path, required=True)
    parser.add_argument("--campaign-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists() and any(args.output_root.iterdir()):
        raise SystemExit(f"refusing non-empty output root: {args.output_root}")
    args.output_root.mkdir(parents=True, exist_ok=True)
    project, package, manifest = make_project(args.output_root, args.uploaded_input_root, args.campaign_root)
    checks = verify(args.output_root, project, package, manifest)
    print("GZP_COMPLETE=" + json.dumps(checks, ensure_ascii=False))


if __name__ == "__main__":
    main()