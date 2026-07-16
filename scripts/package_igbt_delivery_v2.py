#!/usr/bin/env python3
"""Create the compact IGBT delivery v2 package without running TCAD.

The script copies only small, auditable inputs/results, paper material, and the
already-built 20260714 continuation GZP. It never invokes SDevice/SDE/SVisual.
"""
from __future__ import annotations

import argparse
import base64
import csv
import gzip
import hashlib
import io
import json
import re
import shutil
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

REPO = Path(__file__).resolve().parents[1]
FORMAL = REPO / "docs" / "changes" / "2026-07-14-igbt-mosfet-seb-paper-simulation"
PAPER = REPO / "docs" / "changes" / "2026-07-15-ai-assisted-tcad-paper-materials"
LOW_LET = REPO / "docs" / "changes" / "2026-07-13-igbt-seb-现有数据复盘" / "let_scan"
CAMPAIGN = REPO / "local_runtime" / "tcad_projects" / "igbt_mosfet_seb_paper_20260714"
GZP_EVIDENCE = CAMPAIGN / "delivery_v2_gzp_20260715"
GZP = GZP_EVIDENCE / "IGBT_SEB_20260714_Final_Continuation.gzp"
GZP_VERIFICATION = GZP_EVIDENCE / "gzp_verification.json"
GZP_OPEN_PROBE = GZP_EVIDENCE / "workbench_open_probe.json"
BV_FIRST_ROUND = REPO / "local_runtime" / "igbt_bv_first_round_run"
REDESIGN_LOCAL = REPO / "local_runtime" / "tcad_projects" / "igbt_mosfet_650v_seb_20260715"
REDESIGN_DOCS = REPO / "docs" / "changes" / "2026-07-15-igbt-mosfet-650v-redesign"
REDESIGN_PLAN = Path(r"C:\Users\sun\.cursor\plans\igbt_650_v_重设计：单一_550_v_参考案例计划_9b07dafd.plan.md")
MANUAL_COMPARISON_FIGURE = REPO / "local_runtime" / "delivery_additions" / "IGBTvsMOSFET.png"

PRIVATE_TEXT = (
    (str(REPO), "<REPOSITORY_ROOT>"),
    (str(REPO).replace("\\", "/"), "<REPOSITORY_ROOT>"),
    ("/home/tcad/", "<REMOTE_PRIVATE_ROOT>/"),
    ("/home/tcad\\", "<REMOTE_PRIVATE_ROOT>/"),
    ("tcad@192.168.137.131", "<AUTHORIZED_VM>"),
    ("/usr/synopsys/sentaurus/W-2024.09", "<SENTAURUS_ROOT>"),
    ("/usr/synopsys/", "<SENTAURUS_ROOT>/"),
    ("C:/Users/sun/", "<HOST_USER_ROOT>/"),
    ("C:\\Users\\sun\\", "<HOST_USER_ROOT>\\"),
)
FORBIDDEN_SUFFIXES = {".tdr", ".plt", ".sav", ".pdf", ".log", ".stdout", ".stderr", ".bak"}
TEXT_SUFFIXES = {".md", ".csv", ".json", ".txt", ".py", ".ps1", ".sh", ".cmd", ".par", ".tcl"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sanitize(text: str) -> str:
    for old, new in PRIVATE_TEXT:
        text = text.replace(old, new)
    # Source-code string literals contain escaped Windows separators.
    text = text.replace("C:\\\\Users\\\\sun\\\\", "<HOST_USER_ROOT>\\\\")
    return text


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(sanitize(text))


def copy_file(source: Path, target: Path, *, text: bool = False, replacements: dict[str, str] | None = None) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    if text:
        content = source.read_text(encoding="utf-8")
        for old, new in (replacements or {}).items():
            content = content.replace(old, new)
        write_text(target, content)
    else:
        shutil.copy2(source, target)


def copy_tree_small(
    source_root: Path,
    target_root: Path,
    suffixes: set[str],
    *,
    replacements: dict[str, str] | None = None,
    predicate: Callable[[Path], bool] | None = None,
) -> None:
    for source in sorted(source_root.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in suffixes:
            continue
        if predicate is not None and not predicate(source):
            continue
        relative = source.relative_to(source_root)
        copy_file(source, target_root / relative, text=source.suffix.lower() in TEXT_SUFFIXES, replacements=replacements)


def copy_csv_filtered(source: Path, target: Path, predicate: Callable[[dict[str, str]], bool]) -> None:
    """Copy a UTF-8 CSV while making the formal/appendix boundary explicit."""
    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [row for row in reader if predicate(row)]
        fields = list(reader.fieldnames or [])
    if not fields:
        raise ValueError(f"CSV has no header: {source}")
    if not rows:
        raise ValueError(f"CSV filter produced no rows: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def copy_mesh_json_filtered(source: Path, target: Path, device_family: str) -> None:
    """Publish only one device family from the mixed mesh-gate JSON."""
    payload = read_json(source)
    if not isinstance(payload, dict):
        raise ValueError(f"mesh comparison is not an object: {source}")
    devices = payload.get("devices", {})
    rows = payload.get("rows", [])
    if not isinstance(devices, dict) or not isinstance(rows, list):
        raise ValueError(f"mesh comparison schema invalid: {source}")
    filtered = dict(payload)
    filtered["devices"] = {device_family: devices[device_family]} if device_family in devices else {}
    filtered["rows"] = [row for row in rows if isinstance(row, dict) and row.get("device_family") == device_family]
    if not filtered["rows"]:
        raise ValueError(f"mesh comparison has no {device_family} rows: {source}")
    filtered["scope"] = f"{device_family} only; MOSFET remains a comparison appendix" if device_family == "IGBT" else "MOSFET comparison appendix only"
    write_json(target, filtered)


def copy_metadata_filtered(source: Path, target: Path, device_family: str) -> None:
    """Publish metadata with only the requested device's input/render records."""
    payload = read_json(source)
    if not isinstance(payload, dict):
        raise ValueError(f"SVisual metadata is not an object: {source}")
    filtered = dict(payload)
    for key in ("field_used", "inputs"):
        value = filtered.get(key)
        if isinstance(value, dict):
            filtered[key] = {device_family: value[device_family]} if device_family in value else {}
    published = filtered.get("published_pngs")
    if isinstance(published, dict):
        filtered["published_pngs"] = {
            device_family: published[device_family]
        } if device_family in published else {}
    filtered["scope"] = f"{device_family} formal fact source; MOSFET remains a comparison appendix" if device_family == "IGBT" else "MOSFET comparison appendix only"
    write_json(target, filtered)


def copy_campaign_manifest_filtered(source: Path, target: Path) -> None:
    """Keep only IGBT main and IGBT validation cases in section 01/05."""
    payload = read_json(source)
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError(f"campaign manifest schema invalid: {source}")
    filtered = dict(payload)
    filtered["cases"] = [
        case for case in payload["cases"]
        if isinstance(case, dict) and str(case.get("device_family")) == "IGBT"
    ]
    filtered["main_case_count"] = sum(case.get("run_class") == "paper_main" for case in filtered["cases"])
    filtered["validation_case_count"] = sum(case.get("run_class") == "validation_only" for case in filtered["cases"])
    filtered["scope"] = "IGBT continuation inputs only; MOSFET comparison lives in section 03"
    write_json(target, filtered)


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sanitized_json_copy(source: Path, target: Path) -> None:
    write_json(target, read_json(source))


def inspect_gzp(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {
            "relative_path": f"01_IGBT可继续仿真工程/{path.name}",
            "exists": False,
            "verification_level": "BLOCKED_MISSING",
        }
    recorded = read_json(GZP_VERIFICATION)
    open_probe = read_json(GZP_OPEN_PROBE)
    result: dict[str, object] = {
        "relative_path": f"01_IGBT可继续仿真工程/{path.name}",
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "magic_hex": path.read_bytes()[:4].hex(),
        "format": "gzip" if path.read_bytes()[:2] == b"\x1f\x8b" else "unknown",
        "copied_into_delivery": True,
    }
    if not isinstance(recorded, dict) or not isinstance(open_probe, dict):
        raise ValueError("GZP verification metadata is invalid")
    if result["size_bytes"] != recorded.get("package_size_bytes") or result["sha256"] != recorded.get("package_sha256"):
        raise ValueError("recovered GZP does not match the frozen verification record")
    with gzip.open(path, "rb") as stream:
        decompressed = stream.read()
    result["gzip_read_to_eof"] = "PASS"
    with tarfile.open(fileobj=io.BytesIO(decompressed), mode="r:") as archive:
        members = archive.getmembers()
        decoded_names: list[str] = []
        for member in members:
            name = member.name
            if name.startswith("#B64#"):
                name = base64.b64decode(name[5:]).decode("utf-8")
            decoded_names.append(name)
            if member.isreg():
                payload = archive.extractfile(member)
                if payload is not None:
                    payload.read()
        project_root = str(recorded.get("project_root"))
        required = {
            f"{project_root}/.project",
            f"{project_root}/gtree.dat",
            f"{project_root}/ThermalRestart_des.cmd",
            f"{project_root}/HeavyIon_des.cmd",
            f"{project_root}/delivery_metadata/package_manifest.json",
        }
        missing = sorted(required - set(decoded_names))
        if missing:
            raise ValueError(f"final IGBT GZP identity files missing: {missing}")
        result.update({
            "tar_open": "PASS",
            "member_count": len(members),
            "regular_member_count": sum(member.isreg() for member in members),
            "project_root": project_root,
            "required_identity_files": {name: True for name in sorted(required)},
            "internal_identity": "IGBT_SEB_20260714_Final_Continuation / 7-case IGBT continuation Workbench project",
            "unpack_structure": recorded.get("swbunpack_fresh_directory"),
        })
    result["verification_level"] = "PACK_UNPACK_WORKBENCH_OPEN_SVISUAL_VIEW_EXTRACT"
    result["opened_in_workbench"] = open_probe.get("status")
    result["svisual_view_probe"] = recorded.get("svisual_view_probe")
    result["svisual_extract_probe"] = recorded.get("svisual_extract_probe")
    result["continued_run"] = "NOT_RERUN_AFTER_PACKAGING"
    result["relation_to_formal_20260714"] = "Bound to the 20260714 formal IGBT fact source by the embedded 7-case run index and package manifest."
    return result


def copy_formal(package: Path) -> None:
    formal = package / "02_正式结果"
    data = formal / "data"
    figures = formal / "figures"
    report_replacements = {
        "../2026-07-15-igbt-mosfet-650v-redesign/正式仿真结果报告.md": "../00_交付说明/650V重设计边界.md",
    }
    copy_file(FORMAL / "正式仿真结果报告.md", formal / "正式仿真结果报告.md", text=True, replacements=report_replacements)
    # The formal fact source is exactly seven IGBT cases.  Keep the single
    # MOSFET row and mixed plots in the comparison appendix instead of letting
    # a mixed source table silently redefine the main denominator.
    copy_csv_filtered(
        FORMAL / "data" / "case_acceptance.csv",
        data / "case_acceptance.csv",
        lambda row: row.get("case_id", "").startswith("IGBT_"),
    )
    copy_csv_filtered(
        FORMAL / "data" / "dc_thermal_restart_summary.csv",
        data / "dc_thermal_restart_summary.csv",
        lambda row: row.get("device_family") == "IGBT",
    )
    copy_csv_filtered(
        FORMAL / "data" / "campaign_2ns_comparison.csv",
        data / "campaign_2ns_comparison.csv",
        lambda row: row.get("device_family") == "IGBT",
    )
    copy_csv_filtered(
        FORMAL / "data" / "campaign_2ns_numerical_comparison_figure_data.csv",
        data / "campaign_2ns_numerical_comparison_figure_data.csv",
        lambda row: row.get("series") == "IGBT",
    )
    copy_csv_filtered(
        FORMAL / "data" / "mesh_track_refined_comparison.csv",
        data / "mesh_track_refined_comparison.csv",
        lambda row: row.get("device_family") == "IGBT",
    )
    copy_mesh_json_filtered(
        FORMAL / "data" / "mesh_track_refined_comparison.json",
        data / "mesh_track_refined_comparison.json",
        "IGBT",
    )
    copy_metadata_filtered(
        FORMAL / "data" / "lattice_temperature_post2ns_svisual_metadata.json",
        data / "lattice_temperature_post2ns_svisual_metadata.json",
        "IGBT",
    )
    copy_file(
        FORMAL / "figures" / "igbt_lattice_temperature_post2ns_svisual.png",
        figures / "igbt_lattice_temperature_post2ns_svisual.png",
    )
    write_text(
        formal / "README_正式结果.md",
        """# 2026-07-14 正式 IGBT 结果

正式事实源是 7 个 IGBT 唯一案例：四温度线 4 案与 298.15 K 下 500/525/550/575 V 偏压线 4 案共享 T298/V550，因此唯一案数为 7。每个 IGBT 案的热稳态/DC restart 与精确 2.1 ns sidecar 均 PASS（7/7）。

MOSFET 只有 1 个结构匹配派生对照，已移至 `03_MOSFET对照附录/`；它不计入 IGBT 正式事实源，也不代表商用 SJ MOSFET。

交付口径：四温度/多偏压案例跑通，且 298.15 K/550 V 下 baseline 与一次 track-refined 网格的 Tmax、端量、Emax、热点距离通过预设门。这里的通过不是严格全局收敛、普适阈值或商用 650 V 证明。

- [正式结果报告](正式仿真结果报告.md)
- [7 案验收表](data/case_acceptance.csv)
- [2.1 ns IGBT 数值比较](data/campaign_2ns_comparison.csv)
- [局部 track-refined IGBT 网格门](data/mesh_track_refined_comparison.csv)
- [IGBT SVisual 晶格温度图](figures/igbt_lattice_temperature_post2ns_svisual.png)
""",
    )


def copy_mosfet_appendix(package: Path) -> None:
    appendix = package / "03_MOSFET对照附录"
    data = appendix / "data"
    figures = appendix / "figures"
    source_csv = FORMAL / "data" / "campaign_2ns_comparison.csv"
    copy_csv_filtered(
        source_csv,
        data / "MOSFET_T298_V550_L15_2ns.csv",
        lambda row: row.get("device_family") == "MOSFET",
    )
    copy_csv_filtered(
        FORMAL / "data" / "campaign_2ns_numerical_comparison_figure_data.csv",
        data / "MOSFET_2ns_figure_data.csv",
        lambda row: row.get("series") == "MOSFET",
    )
    copy_csv_filtered(
        FORMAL / "data" / "mesh_track_refined_comparison.csv",
        data / "MOSFET_track_refined_mesh_gate.csv",
        lambda row: row.get("device_family") == "MOSFET",
    )
    copy_mesh_json_filtered(
        FORMAL / "data" / "mesh_track_refined_comparison.json",
        data / "MOSFET_track_refined_mesh_gate.json",
        "MOSFET",
    )
    copy_metadata_filtered(
        FORMAL / "data" / "lattice_temperature_post2ns_svisual_metadata.json",
        data / "MOSFET_lattice_temperature_post2ns_svisual_metadata.json",
        "MOSFET",
    )
    # These mixed plots are explicitly comparison-only and therefore belong in
    # the appendix, never in the formal IGBT result directory.
    for name in (
        "campaign_2ns_numerical_comparison.png",
        "campaign_2ns_numerical_comparison.svg",
        "mosfet_lattice_temperature_post2ns_svisual.png",
        "lattice_temperature_post2ns_svisual_comparison.png",
    ):
        copy_file(FORMAL / "figures" / name, figures / name)
    write_text(
        appendix / "README_MOSFET对照附录.md",
        """# MOSFET 对照附录\n\nMOSFET 是与 IGBT 冻结历史模型匹配的派生对照，不是商用 SJ MOSFET 证明，也不改变 IGBT 主交付口径。它不计入 7 个 IGBT 正式事实源。\n\n- [2.1 ns MOSFET 数值行](data/MOSFET_T298_V550_L15_2ns.csv)\n- [MOSFET 图数据](data/MOSFET_2ns_figure_data.csv)\n- [track-refined 网格门](data/MOSFET_track_refined_mesh_gate.csv)\n- [track-refined 网格 JSON](data/MOSFET_track_refined_mesh_gate.json)\n- [SVisual 晶格温度图](figures/mosfet_lattice_temperature_post2ns_svisual.png)\n- [IGBT/MOSFET 数值比较图](figures/campaign_2ns_numerical_comparison.png)\n- [IGBT/MOSFET 空间场对照](figures/lattice_temperature_post2ns_svisual_comparison.png)\n\n热点距离来自 sidecar 数值计算，不从图像估计。不得外推为所有 MOSFET 热点更近/更远氧化层，也不得外推为 TID 永久损伤。\n""",
    )


def copy_low_let(package: Path) -> None:
    appendix = package / "04_低LET诊断附录"
    copy_file(LOW_LET / "LET扫描诊断报告.md", appendix / "低LET诊断报告.md", text=True)
    copy_tree_small(LOW_LET / "data", appendix / "data", {".csv", ".json"})
    copy_tree_small(LOW_LET / "figures", appendix / "figures", {".png", ".svg"})
    write_text(
        appendix / "README_低LET边界.md",
        """# 低 LET 诊断附录\n\n本目录仅收录既有低 LET 数据复盘。其状态固定为 `diagnostic_only/MESH_SENSITIVE`，不构成 SEB 阈值、热因果、普适机制或 NO_SEB 结论。\n\n- [诊断报告](低LET诊断报告.md)\n- [提取与验证数据](data/)\n- [图件](figures/)\n""",
    )


def copy_minimal_reproduction(package: Path) -> None:
    minimum = package / "05_最小复现材料"
    script_dir = minimum / "scripts"
    input_dir = minimum / "formal_inputs"
    copy_file(
        REPO / "scripts" / "run_igbt_seb_case.ps1",
        script_dir / "run_igbt_seb_case_脱敏.ps1",
        text=True,
        replacements={
            "'/home/tcad/codex_runs'": "'<REMOTE_RUN_ROOT>'",
            "'tcad@192.168.137.131'": "'<AUTHORIZED_VM>'",
            "'/usr/synopsys/sentaurus/W-2024.09'": "'<SENTAURUS_ROOT>'",
        },
    )
    copy_file(REPO / "scripts" / "sdevice_core_lease.sh", script_dir / "sdevice_core_lease.sh", text=True)
    copy_file(REPO / "scripts" / "summarize_igbt_mosfet_seb_campaign.py", script_dir / "summarize_igbt_mosfet_seb_campaign.py", text=True)
    copy_file(REPO / "scripts" / "validate_ai_tcad_paper_materials.py", script_dir / "validate_ai_tcad_paper_materials.py", text=True)
    copy_file(REPO / "scripts" / "verify_delivery_v2.py", script_dir / "verify_delivery_v2.py", text=True)
    copy_file(REPO / "config" / "sentaurus-core-policy.json", script_dir / "sentaurus-core-policy.json", text=True, replacements={"/home/tcad/.cache/": "<REMOTE_PRIVATE_ROOT>/.cache/"})
    for name in (
        "campaign_manifest.json",
        "case_matrix.csv",
        "frozen_input_hashes.json",
        "frozen_input_manifest.json",
        "plot_2ns_spec.json",
        "sdevice_parameter_snapshot.json",
        "source_and_derivation_audit.json",
        "sdevice.par",
    ):
        source = CAMPAIGN / "inputs" / name
        if name == "campaign_manifest.json":
            copy_campaign_manifest_filtered(source, input_dir / name)
        elif name == "case_matrix.csv":
            copy_csv_filtered(
                source,
                input_dir / name,
                lambda row: row.get("device_family") == "IGBT",
            )
        elif source.suffix.lower() == ".json":
            sanitized_json_copy(source, input_dir / name)
        else:
            copy_file(source, input_dir / name, text=True)
    copy_tree_small(
        CAMPAIGN / "inputs" / "sde",
        input_dir / "sde",
        {".cmd"},
        predicate=lambda path: path.name.startswith("igbt_"),
    )
    copy_tree_small(
        CAMPAIGN / "inputs" / "cases",
        input_dir / "cases",
        {".cmd", ".json"},
        predicate=lambda path: path.parent.name.startswith("IGBT_") or path.parent.name.startswith("VAL_IGBT_"),
    )
    write_text(
        minimum / "README_最小复现材料.md",
        """# 最小复现材料\n\n本目录只提供 7 个 IGBT 主案的小型输入、只读汇总脚本和自动核心租约包装器；不含 MOSFET 主输入、重复的 GZP、TDR/PLT/SAV、完整日志、许可证或凭据。最终 GZP 位于 `../01_IGBT可继续仿真工程/`。\n\n## 已验证的只读复算\n\n```powershell\npython scripts\\summarize_igbt_mosfet_seb_campaign.py\npython scripts\\validate_ai_tcad_paper_materials.py\n```\n\n仓库侧 `package_igbt_delivery_v2.py` 复制已验证的最终 GZP 和小型脱敏材料，不构建 GZP、不调用 SDevice。随包提供的 `scripts/verify_delivery_v2.py` 执行 ZIP CRC、解压后二次哈希、清单、相对链接与包内 GZP 结构核验。\n\n## 获授权 VM 上的继续运行\n\n1. 先按 `../01_IGBT可继续仿真工程/README_可继续仿真工程.md` 解包并核对 GZP 身份；\n2. 将 `scripts/run_igbt_seb_case_脱敏.ps1` 复制到仓库 `scripts/`，并通过参数显式提供授权的 `-VmUserHost`、`-RemoteRunRoot`、`-SentaurusRoot`、`-LocalRunRoot`；\n3. 用 `-Threads 1` 和 `-CorePolicyPath` 启动新的独立 attempt；网格、DC restart、瞬态必须串行。\n\n本材料不授权分发 Synopsys 软件或受限产物。MOSFET 仅在 03 附录提供；低 LET 仅 diagnostic_only/MESH_SENSITIVE；650 V redesign 仍 PENDING。\n""",
    )


def copy_bv_first_round(package: Path) -> None:
    """Publish the first-round BV temperature matrix as bounded evidence."""
    target = package / "02_正式结果" / "BV首轮温度矩阵"
    copy_tree_small(
        BV_FIRST_ROUND,
        target,
        {".cmd", ".csv", ".json", ".png", ".py", ".sh", ".par", ".txt"},
        predicate=lambda path: path.name != "mesh_export.grd",
    )
    write_text(
        target / "README_BV首轮温度矩阵.md",
        """# IGBT 首轮 BV 温度矩阵

本目录收录 `igbt_bv_first_round_run` 的首轮四温度 BV 运行材料、端量 CSV/JSON、图件和输入脚本。

证据用途限定为：首轮 IGBT BV 温度矩阵与局部温度/场分布检查。它不是严格全局温度收敛证明，也不替代 2026-07-14 正式 IGBT 主案的四温度/多偏压结果，不用于 SEB 阈值或热机制因果结论。

原始 `.log`、`.stdout` 和大体积网格/求解产物不随包复制；本目录文件均来自同一首轮运行目录，具体 SHA-256 见上级 `资产清单.csv`。
""",
    )


def copy_650v_redesign(package: Path) -> None:
    """Publish small 650 V redesign evidence without promoting its status."""
    target = package / "06_650V重设计状态附录"
    copy_file(REDESIGN_DOCS / "正式仿真结果报告.md", target / "正式仿真结果报告.md", text=True)
    copy_file(REDESIGN_DOCS / "电场与入射轨迹定位报告.md", target / "电场与入射轨迹定位报告.md", text=True)
    copy_file(REDESIGN_PLAN, target / "计划_单一550V参考案例.md", text=True)
    copy_tree_small(REDESIGN_DOCS / "data", target / "data", {".csv", ".json"})
    copy_tree_small(REDESIGN_DOCS / "figures", target / "figures", {".png", ".svg"})

    # Keep only compact manifests, inputs, extraction results, and comparison
    # evidence. Raw run logs/TDR/PLT/SAV and credentials stay in local_runtime.
    for relative, suffixes in (
        ("field_extractions", {".json"}),
        ("field_localization_inputs", {".cmd", ".json"}),
        ("static_run_sets", {".json"}),
        ("mesh_generation", {".json"}),
        ("post_static_inputs", {".cmd", ".json", ".par"}),
        ("comparison_only_igbt550_mosfet500_20260716", {".csv", ".json"}),
        ("recovery", {".csv", ".json", ".cmd", ".par"}),
        ("generated", {".cmd", ".json", ".scm"}),
        ("calibration_inputs", {".cmd", ".json", ".par"}),
    ):
        source = REDESIGN_LOCAL / relative
        if source.is_dir():
            copy_tree_small(source, target / "local_materials" / relative, suffixes)

    for source in sorted(REDESIGN_LOCAL.glob("*.json")):
        if source.name.startswith(("igbt_attempt", "mosfet_attempt")) or source.name in {"seed_tree_manifest.json"}:
            copy_file(source, target / "local_materials" / source.name, text=True)
    copy_file(REDESIGN_LOCAL / "static_field_audit.py", target / "local_materials" / "static_field_audit.py", text=True)
    write_text(
        target / "README_650V状态边界.md",
        """# 650 V 重设计状态附录

本附录收录计划文件、正式状态报告、轻量 CSV/JSON、图件和局部输入，**不是**正式 IGBT 主交付结果，也不进入 GZP。

截至当前证据，状态必须保留为：

- `FAILED_NUMERICAL_ONLY`：IGBT 400 V pre-strike recovery 仍未形成正式 HeavyIon 数值闭合；
- `CANCELLED_BY_SCOPE_CHANGE`：当前 650 V IGBT 的新 550 V 单案例未启动，计划文件中的 `pending` 状态原样保留；
- `COMPARISON_ONLY`：历史 IGBT 550 V 与当前 MOSFET 500 V 的并列材料仅作非共同工况对照。

因此本目录不得被解释为完成的 650 V 商用器件证明、SEB 阈值、安全边界、温度全局收敛或器件排名。原始运行日志、TDR/PLT/SAV 和凭据仍仅保留在仓库 `local_runtime`，不随分享包分发。

- [正式状态报告](正式仿真结果报告.md)
- [电场与入射轨迹报告](电场与入射轨迹定位报告.md)
- [单一 550 V 计划](计划_单一550V参考案例.md)
- [轻量数据](data/)
- [轻量本地材料](local_materials/)
""",
    )


def copy_manual_comparison_figure(package: Path) -> None:
    """Keep the manually added MOSFET comparison figure reproducible."""
    target = package / "03_MOSFET对照附录" / "figures" / "IGBTvsMOSFET.png"
    source = MANUAL_COMPARISON_FIGURE
    if not source.is_file():
        source = REPO / "share" / "IGBT_最终交付_v2_20260716_最终版" / "03_MOSFET对照附录" / "figures" / "IGBTvsMOSFET.png"
    copy_file(source, target)


def copy_paper_materials(package: Path) -> None:
    target = package / "02_正式结果" / "论文材料"
    # The paper package is already small and contains no raw binary solver artifacts.
    copy_tree_small(PAPER, target, {".md", ".csv", ".json", ".svg"})


def write_delivery_docs(package: Path, gzp_info: dict[str, object]) -> None:
    info = package / "00_交付说明"
    info.mkdir(parents=True, exist_ok=True)
    write_json(info / "GZP验证记录.json", gzp_info)
    write_text(
        info / "GZP验证记录.md",
        f"""# 最终 IGBT GZP 验证记录\n\n- 包内文件：`../01_IGBT可继续仿真工程/IGBT_SEB_20260714_Final_Continuation.gzp`。\n- SHA-256：`{gzp_info.get('sha256', 'NA')}`\n- 大小：`{gzp_info.get('size_bytes', 'NA')} bytes`\n- 内部身份：`{gzp_info.get('internal_identity', '未识别')}`。\n- 验证等级：`{gzp_info.get('verification_level', 'NA')}`。\n- 直接证据：gzip EOF 与 tar 结构 PASS；全新目录 `swbunpack` = {gzp_info.get('unpack_structure', 'NA')}；Workbench W-2024.09 可编辑打开 = {gzp_info.get('opened_in_workbench', 'NA')}；SVisual 查看 = {gzp_info.get('svisual_view_probe', 'NA')}；SVisual 提取 = {gzp_info.get('svisual_extract_probe', 'NA')}。\n- 打包后 SDevice 重跑：`{gzp_info.get('continued_run', 'NA')}`。\n\n**关系声明：**该工程通过内嵌 7 案 run index、package manifest 和冻结产物哈希绑定 20260714 IGBT 正式事实源。它包含结构、热 restart、HeavyIon、查看和提取节点，可作为后续获授权仿真的起点；本次交付收口没有额外启动 SDevice，因此不把“可继续”写成打包后已重跑。\n""",
    )
    write_text(
        info / "650V重设计边界.md",
        """# 650 V redesign 边界\n\n截至当前证据，650 V redesign 状态为 `FAILED_NUMERICAL_ONLY / CANCELLED_BY_SCOPE_CHANGE / PENDING`：本包仅收录状态材料、轻量证据和计划，不把它并入正式 IGBT 数值结论或 GZP。当前 550 V 新案例未启动；历史 451.15 µm 数据不能替代当前 650 V 模型结果。\n\n详见仓库 `docs/changes/2026-07-15-igbt-mosfet-650v-redesign/正式仿真结果报告.md`。\n""",
    )
    write_text(
        info / "来源版本与边界.md",
        """# 来源版本与边界\n\n## 正式结果\n\n- [2026-07-14 正式结果](../02_正式结果/正式仿真结果报告.md)\n- [正式结果 README](../02_正式结果/README_正式结果.md)\n- [AI-assisted TCAD 论文材料](../02_正式结果/论文材料/README.md)\n\n## 附录边界\n\n- [MOSFET 对照附录](../03_MOSFET对照附录/README_MOSFET对照附录.md)\n- [低 LET 诊断附录](../04_低LET诊断附录/README_低LET边界.md)\n- 650 V redesign：PENDING，见本目录 `650V重设计边界.md`。\n\n## 工程来源\n\n- 包内 `IGBT_SEB_20260714_Final_Continuation.gzp`：由内嵌 7 案 run index、package manifest 和冻结哈希绑定 20260714 正式结果；已通过 pack/unpack、Workbench 打开和 SVisual 探针。\n- 正式事实源：仓库 `docs/changes/2026-07-14-igbt-mosfet-seb-paper-simulation` 与 `local_runtime/tcad_projects/igbt_mosfet_seb_paper_20260714`。\n- 软件：Sentaurus W-2024.09；许可证、原始 PDF、私有运行产物不随包分发。\n""",
    )
    write_text(
        info / "00_交付说明.md",
        """# IGBT 最终交付 v2\n\n本包以 7 个 IGBT 正式主案为主，MOSFET 仅作 1 个结构匹配对照附录。\n\n## 一句话结论\n\n四温度/多偏压案例跑通：4 个温度点与 4 个偏压点共享 298.15 K/550 V，形成 7 个唯一 IGBT 主案；且 298.15 K/550 V 下 baseline 与一次 track-refined 网格的 Tmax/端量/Emax/热点距离通过预设门。不得将其扩写为严格全局收敛、普适阈值或商用 650 V 证明。\n\n## 目录\n\n- [01 IGBT 可继续仿真工程](../01_IGBT可继续仿真工程/README_可继续仿真工程.md)\n- [02 正式结果与论文材料](../02_正式结果/README_正式结果.md)\n- [03 MOSFET 对照附录](../03_MOSFET对照附录/README_MOSFET对照附录.md)\n- [04 低 LET 诊断附录](../04_低LET诊断附录/README_低LET边界.md)\n- [05 最小复现材料](../05_最小复现材料/README_最小复现材料.md)\n- [06 650 V 重设计状态附录](../06_650V重设计状态附录/README_650V状态边界.md)\n- [最终 IGBT GZP 验证](GZP验证记录.md)\n- [来源与边界](来源版本与边界.md)\n- [来源清单](来源清单.csv)\n- [资产清单](资产清单.csv)\n\n包内包含一个已验证且绑定 20260714 正式事实源的 IGBT continuation GZP；不重复打包其他 GZP。\n""",
    )
    write_source_manifest(package)


def write_source_manifest(package: Path) -> None:
    """Write a concise source inventory without exposing private locations."""
    target = package / "00_交付说明" / "来源清单.csv"
    rows = [
        {
            "source_id": "S01",
            "source_path": "docs/changes/2026-07-14-igbt-mosfet-seb-paper-simulation",
            "source_type": "formal fact source",
            "used_in": "02_正式结果 (7 IGBT cases)",
            "status": "included as filtered public evidence",
            "boundary": "fixed historical 2D model; not global convergence or 650 V proof",
        },
        {
            "source_id": "S02",
            "source_path": "local_runtime/tcad_projects/igbt_mosfet_seb_paper_20260714/inputs",
            "source_type": "continuation inputs",
            "used_in": "01_IGBT可继续仿真工程; 05_最小复现材料",
            "status": "included after IGBT-only filtering and path redaction",
            "boundary": "no raw TDR/PLT/SAV or private run directory",
        },
        {
            "source_id": "S03",
            "source_path": "docs/changes/2026-07-15-ai-assisted-tcad-paper-materials",
            "source_type": "AI-assisted TCAD paper materials",
            "used_in": "02_正式结果/论文材料",
            "status": "included as public small materials",
            "boundary": "researcher-constrained bounded autonomy; no AI-vs-human claim",
        },
        {
            "source_id": "S04",
            "source_path": "docs/changes/2026-07-13-igbt-seb-现有数据复盘/let_scan",
            "source_type": "low-LET diagnostic evidence",
            "used_in": "04_低LET诊断附录",
            "status": "included as diagnostic appendix",
            "boundary": "diagnostic_only/MESH_SENSITIVE; no threshold or causality",
        },
        {
            "source_id": "S05",
            "source_path": "scripts + config",
            "source_type": "reproduction tooling",
            "used_in": "05_最小复现材料/scripts",
            "status": "included after sensitive-path redaction",
            "boundary": "verifier is read-only; no SDevice invoked by packaging",
        },
        {
            "source_id": "S06",
            "source_path": "local_runtime/.../delivery_v2_gzp_20260715/IGBT_SEB_20260714_Final_Continuation.gzp",
            "source_type": "verified 20260714 continuation Workbench package",
            "used_in": "01_IGBT可继续仿真工程",
            "status": "included; SHA matched frozen verification record",
            "boundary": "pack/unpack/Workbench-open/SVisual probes PASS; no post-package SDevice rerun",
        },
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def copy_igbt_continuation(package: Path) -> None:
    target = package / "01_IGBT可继续仿真工程"
    copy_file(GZP, target / GZP.name)
    input_target = target / "inputs"
    for name in (
        "campaign_manifest.json",
        "case_matrix.csv",
        "frozen_input_hashes.json",
        "frozen_input_manifest.json",
        "plot_2ns_spec.json",
        "sdevice_parameter_snapshot.json",
        "source_and_derivation_audit.json",
        "sdevice.par",
    ):
        source = CAMPAIGN / "inputs" / name
        if name == "campaign_manifest.json":
            copy_campaign_manifest_filtered(source, input_target / name)
        elif name == "case_matrix.csv":
            copy_csv_filtered(
                source,
                input_target / name,
                lambda row: row.get("device_family") == "IGBT",
            )
        elif source.suffix.lower() == ".json":
            sanitized_json_copy(source, input_target / name)
        else:
            copy_file(source, input_target / name, text=True)
    copy_tree_small(
        CAMPAIGN / "inputs" / "sde",
        input_target / "sde",
        {".cmd"},
        predicate=lambda path: path.name.startswith("igbt_"),
    )
    copy_tree_small(
        CAMPAIGN / "inputs" / "cases",
        input_target / "cases",
        {".cmd", ".json"},
        predicate=lambda path: path.parent.name.startswith("IGBT_") or path.parent.name.startswith("VAL_IGBT_"),
    )
    write_text(
        target / "README_可继续仿真工程.md",
        """# IGBT 可继续仿真工程\n\n本目录包含已生成并验证的 `IGBT_SEB_20260714_Final_Continuation.gzp`，以及 2026-07-14 7 个正式 IGBT 主案和 1 个 IGBT track-refined validation 的脱敏输入层。该 GZP 已通过 `swbpack`、全新目录 `swbunpack`、Workbench W-2024.09 可编辑打开、SVisual 查看和提取探针；打包后未重新执行 SDevice。\n\n- [输入说明](inputs/case_matrix.csv)\n- [GZP 验证记录](../00_交付说明/GZP验证记录.md)\n- [正式结果](../02_正式结果/正式仿真结果报告.md)\n- [最小复现说明](../05_最小复现材料/README_最小复现材料.md)\n\n## 打开与继续仿真\n\n1. 在合法授权的 Sentaurus W-2024.09 环境执行 `swbunpack -d <新目录> IGBT_SEB_20260714_Final_Continuation.gzp`；\n2. 用 Workbench 打开解包后的 `IGBT_SEB_20260714_Final_Continuation` 工程；\n3. 先核对内嵌 `delivery_metadata/package_manifest.json`、7 案 run index 和输入哈希；\n4. 后续新运行必须使用新 attempt ID，按网格 → DC restart → transient 串行，SDevice 一线程并经自动核心租约；\n5. 不把低 LET diagnostic_only 数据、MOSFET 对照或 650 V PENDING redesign 混入正式 IGBT 矩阵。\n\n“可继续仿真”表示工程已可解包、可编辑打开并带有结构、热 restart、HeavyIon 与 SVisual 节点及冻结参考产物；本次交付收口未额外重跑 SDevice。\n""",
    )


def kind_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md"}:
        return "documentation"
    if suffix in {".csv", ".json"}:
        return "structured_data"
    if suffix in {".png", ".svg"}:
        return "figure"
    if suffix in {".cmd", ".par", ".ps1", ".sh", ".py", ".tcl"}:
        return "reproduction_input_or_script"
    if suffix == ".gzp":
        return "verified_workbench_package"
    if suffix == ".txt":
        return "manifest_or_record"
    return "other"


def boundary_for(path: Path) -> str:
    text = path.as_posix()
    if text.startswith("00_交付说明"):
        return "delivery metadata and explicit claim boundary"
    if text.startswith("03_MOSFET"):
        return "derived comparison appendix only"
    if text.startswith("04_低LET"):
        return "diagnostic_only/MESH_SENSITIVE; no threshold or causality"
    if text.startswith("02_正式结果/BV首轮温度矩阵"):
        return "first-round BV temperature matrix/local evidence only; not strict global convergence"
    if text.startswith("02_正式结果/论文材料"):
        return "researcher-constrained AI-assisted/headless SSH case study"
    if text.startswith("01_IGBT"):
        return "verified continuation GZP and sanitized input layer; no post-package SDevice rerun"
    if text.startswith("02_正式结果/BV首轮温度矩阵"):
        return "local_runtime/igbt_bv_first_round_run"
    return "see package README"


def source_for(path: Path) -> str:
    text = path.as_posix()
    if text.startswith("02_正式结果/BV首轮温度矩阵"):
        return "local_runtime/igbt_bv_first_round_run"
    if text.startswith("02_正式结果"):
        return "docs/changes/2026-07-14-igbt-mosfet-seb-paper-simulation"
    if text.startswith("04_低LET"):
        return "docs/changes/2026-07-13-igbt-seb-现有数据复盘/let_scan"
    if text.endswith("IGBT_SEB_20260714_Final_Continuation.gzp"):
        return "verified 20260714 continuation package"
    if text.startswith("01_IGBT"):
        return "local_runtime/tcad_projects/igbt_mosfet_seb_paper_20260714/inputs"
    if text.startswith("05_最小复现"):
        return "scripts + config + formal input source"
    if text.startswith("06_650V重设计状态附录"):
        return "docs/changes/2026-07-15-igbt-mosfet-650v-redesign + local_runtime/tcad_projects/igbt_mosfet_650v_seb_20260715 + approved plan"
    return "delivery metadata"


def write_asset_manifest(package: Path) -> None:
    rows: list[dict[str, object]] = []
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path.name in {"资产清单.csv", "SHA256SUMS.txt"}:
            continue
        relative = path.relative_to(package).as_posix()
        rows.append(
            {
                "relative_path": relative,
                "kind": kind_for(path),
                "status": "included",
                "source": source_for(path),
                "size": path.stat().st_size,
                "sha": sha256(path),
                "purpose": "final delivery evidence or reproducible input",
                "boundary": boundary_for(path),
            }
        )
    manifest = package / "00_交付说明" / "资产清单.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["relative_path", "kind", "status", "source", "size", "sha", "purpose", "boundary"])
        writer.writeheader()
        writer.writerows(rows)
    sums: list[str] = []
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            sums.append(f"{sha256(path)}  {path.relative_to(package).as_posix()}")
    write_text(package / "00_交付说明" / "SHA256SUMS.txt", "\n".join(sums) + "\n")


def write_archive(package: Path, archive_path: Path) -> tuple[str, int]:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(package.parent).as_posix())
    return sha256(archive_path), archive_path.stat().st_size


def write_external_summary(package: Path, archive_path: Path, archive_sha: str, archive_size: int, gzp_info: dict[str, object]) -> None:
    summary = {
        "schema": "igbt_final_delivery_summary/v2",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "share_directory": package.relative_to(REPO).as_posix(),
        "zip_relative_path": archive_path.relative_to(REPO).as_posix(),
        "zip_sha256": archive_sha,
        "zip_size_bytes": archive_size,
        "gzp_relative_path": gzp_info.get("relative_path"),
        "gzp_sha256": gzp_info.get("sha256", "NA"),
        "gzp_verification_level": gzp_info.get("verification_level", "MISSING"),
        "gzp_open_evidence": gzp_info.get("opened_in_workbench"),
        "gzp_continuation_evidence": gzp_info.get("continued_run"),
        "formal_fact_source": [
            "docs/changes/2026-07-14-igbt-mosfet-seb-paper-simulation",
            "local_runtime/tcad_projects/igbt_mosfet_seb_paper_20260714",
        ],
        "formal_igbt_case_count": 7,
        "formal_igbt_thermal_and_2p1ns_status": "7/7 PASS",
        "mosfet_appendix_case_count": 1,
        "main_scope": "7 IGBT four-temperature/multi-bias short-transient cases with one local track-refined gate",
        "mosfet_scope": "comparison appendix only",
        "low_let_scope": "diagnostic_only/MESH_SENSITIVE appendix",
        "bv_first_round_scope": "first-round IGBT BV temperature matrix and local evidence only; not strict global convergence",
        "redesign_650v_scope": "PENDING / FAILED_NUMERICAL_ONLY / CANCELLED_BY_SCOPE_CHANGE status appendix; no new 550 V SDevice result",
        "new_sdevice_started_by_packager": False,
        "gzp_rebuilt_by_packager": False,
    }
    write_json(REPO / "share" / f"{package.name}.delivery_summary.json", summary)
    write_text(REPO / "share" / f"{package.name}.zip.sha256", f"{archive_sha}  {archive_path.name}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="", help="unique directory/archive stem under share/ (defaults to current UTC time)")
    parser.add_argument("--output-root", type=Path, default=REPO / "share")
    args = parser.parse_args()
    name = args.name or f"IGBT_最终交付_v2_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}"
    output_root = args.output_root.resolve()
    package = output_root / name
    archive_path = output_root / f"{name}.zip"
    if package.exists() or archive_path.exists():
        raise SystemExit(f"refusing to overwrite existing delivery: {package} or {archive_path}")
    package.mkdir(parents=True)
    gzp_info = inspect_gzp(GZP)
    copy_igbt_continuation(package)
    copy_formal(package)
    copy_bv_first_round(package)
    copy_mosfet_appendix(package)
    copy_manual_comparison_figure(package)
    copy_low_let(package)
    copy_minimal_reproduction(package)
    copy_paper_materials(package)
    copy_650v_redesign(package)
    write_delivery_docs(package, gzp_info)
    write_asset_manifest(package)
    archive_sha, archive_size = write_archive(package, archive_path)
    write_external_summary(package, archive_path, archive_sha, archive_size, gzp_info)
    # The external summary and sidecar are intentionally outside the archive;
    # regenerate the archive only if callers explicitly request a new package.
    print(json.dumps({
        "share_directory": package.relative_to(REPO).as_posix(),
        "zip_relative_path": archive_path.relative_to(REPO).as_posix(),
        "zip_sha256": archive_sha,
        "zip_size_bytes": archive_size,
        "gzp": gzp_info,
        "note": "external delivery_summary and ZIP SHA written after archive creation",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())