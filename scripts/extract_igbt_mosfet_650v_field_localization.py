#!/usr/bin/env python3
"""Extract Emax from six verified-mesh field TDRs and freeze safe strike tracks."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "local_runtime" / "tcad_projects" / "igbt_mosfet_650v_seb_20260715"
RUNS = RUNTIME / "runs"
LOCAL_EXTRACTIONS = RUNTIME / "field_extractions"
DATA = ROOT / "docs" / "changes" / "2026-07-15-igbt-mosfet-650v-redesign" / "data"
FIGURES = DATA.parent / "figures"
REPORT = DATA.parent / "电场与入射轨迹定位报告.md"
SVISUAL_SCRIPT = ROOT / "scripts" / "extract_igbt_mosfet_650v_field_tdr.py"
VM = "tcad@192.168.137.131"
SVISUAL = "/usr/synopsys/sentaurus/W-2024.09/bin/svisual"
ATTEMPT = "checkpoint_b_field_localization_v1"
FLOAT = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?")
CASES = [(family, bias) for family in ("IGBT", "MOSFET") for bias in (325, 400, 500)]
DSL = {
    "IGBT": ROOT / "projects" / "igbt_mosfet_650v_seb_20260715" / "devices" / "igbt_650v.json",
    "MOSFET": ROOT / "projects" / "igbt_mosfet_650v_seb_20260715" / "devices" / "mosfet_650v_sj.json",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def value(spec: dict, name: str) -> float:
    item = spec["parameters"][name]
    selected = item["final_value"] if item["final_value"] is not None else item.get("candidate_value")
    return float(item["seed_value"] if selected is None else selected)


def successful_run(case_id: str) -> tuple[Path, dict]:
    matches = sorted(RUNS.glob(f"{case_id}__{ATTEMPT}__*/run_manifest.json"))
    succeeded = []
    for path in matches:
        manifest = read_json(path)
        scheduling = manifest.get("scheduling_evidence", {})
        if (
            manifest.get("lifecycle") == "SUCCEEDED"
            and str(manifest.get("exit_code")) == "0"
            and manifest.get("sdevice_threads") == 1
            and scheduling.get("allocation_mode") == "AUTO_LEASE"
            and scheduling.get("lease_acquired") is True
            and scheduling.get("lease_released") is True
            and scheduling.get("affinity_verification") == "VERIFIED"
        ):
            succeeded.append((path.parent, manifest))
    if len(succeeded) != 1:
        raise ValueError(f"{case_id}: expected exactly one successful leased field run, found {len(succeeded)}")
    return succeeded[0]


def run_svisual(run_dir: Path, manifest: dict, family: str, bias: int) -> dict:
    case_id = manifest["case_id"]
    tdr_leaf = f"{case_id.lower()}_pre_des.tdr"
    local_tdr = run_dir / "artifacts" / tdr_leaf
    if not local_tdr.is_file():
        raise FileNotFoundError(f"{case_id}: required field TDR is missing: {tdr_leaf}")
    mesh_hash = next(item["sha256"] for item in manifest["inputs"] if item["relative_path"].endswith("_msh.tdr"))
    spec = read_json(DSL[family])
    track_start_x = 3.13 + value(spec, "gate_oxide_thickness") + 0.01
    track_end_x = value(spec, "drift_thickness") - 0.01
    remote_dir = manifest["remote_run_dir"] + "/inputs"
    remote_script = remote_dir + "/extract_field_tdr.py"
    remote_output = remote_dir + f"/{case_id.lower()}_field_v2.json"
    remote_stdout = remote_dir + f"/{case_id.lower()}_svisual.stdout.log"
    remote_stderr = remote_dir + f"/{case_id.lower()}_svisual.stderr.log"
    subprocess.run(["scp", str(SVISUAL_SCRIPT), f"{VM}:{remote_script}"], check=True)
    environment = {
        "SOURCE_TDR": remote_dir + "/" + tdr_leaf,
        "CASE_ID": case_id,
        "DEVICE_FAMILY": family,
        "BIAS_V": str(bias),
        "MESH_SHA256": mesh_hash,
        "TRACK_START_X": f"{track_start_x:.9g}",
        "TRACK_END_X": f"{track_end_x:.9g}",
        "TRACK_Y_MODE": "IMPACT_MAX_Y",
        "STRICT_MARGIN": "0.01",
        "OUTPUT_JSON": remote_output,
    }
    command = "cd " + shlex.quote(remote_dir) + " && " + " ".join(
        f"{name}={shlex.quote(text)}" for name, text in environment.items()
    )
    command += f" {shlex.quote(SVISUAL)} -b -python {shlex.quote(remote_script)} > {shlex.quote(remote_stdout)} 2> {shlex.quote(remote_stderr)}"
    subprocess.run(["ssh", VM, command], check=True)
    LOCAL_EXTRACTIONS.mkdir(parents=True, exist_ok=True)
    local_output = LOCAL_EXTRACTIONS / f"{case_id.lower()}_field_v2.json"
    subprocess.run(["scp", f"{VM}:{remote_output}", str(local_output)], check=True)
    extracted = read_json(local_output)
    if (
        extracted.get("schema_version") != "650v_field_localization_tdr_extraction/v2"
        or extracted.get("status") != "VERIFIED"
        or extracted.get("source_tdr_sha256") != sha256(local_tdr)
        or not isinstance(extracted.get("track_path_electric_field_max"), dict)
        or not isinstance(extracted.get("track_path_impact_ionization_max"), dict)
    ):
        raise ValueError(f"{case_id}: SVisual extraction/TDR/active-path closure failed")
    return {
        "run_dir": run_dir,
        "manifest": manifest,
        "local_tdr": local_tdr,
        "local_extraction": local_output,
        "extracted": extracted,
        "mesh_sha256": mesh_hash,
    }


def svg_plot(rows: list[dict], tracks: dict[str, dict]) -> str:
    colors = {325: "#2c7fb8", 400: "#fdae61", 500: "#d7191c"}
    width, height = 1000, 420
    panels = {"IGBT": (60, 55, 410, 300), "MOSFET": (530, 55, 410, 300)}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="white"/>']
    for family, (left, top, pw, ph) in panels.items():
        xmax = tracks[family]["silicon_bounds_um"]["x_max"]
        parts += [f'<rect x="{left}" y="{top}" width="{pw}" height="{ph}" fill="#f7f7f7" stroke="#333"/>', f'<text x="{left + pw/2}" y="30" text-anchor="middle" font-family="sans-serif" font-size="18">{family} high-impact markers and frozen track</text>']
        track = tracks[family]
        x1 = left + pw * track["start_um"][0] / xmax
        x2 = left + pw * track["end_um"][0] / xmax
        y = top + ph * (1 - track["start_um"][1] / 6.0)
        parts.append(f'<line x1="{x1:.2f}" y1="{y:.2f}" x2="{x2:.2f}" y2="{y:.2f}" stroke="#6a3d9a" stroke-width="3"/>')
        for row in [item for item in rows if item["device_family"] == family]:
            x = left + pw * row["impact_max_x_um"] / xmax
            py = top + ph * (1 - row["impact_max_y_um"] / 6.0)
            color = colors[int(row["bias_v"])]
            parts += [f'<circle cx="{x:.2f}" cy="{py:.2f}" r="6" fill="{color}"/>', f'<text x="{x + 8:.2f}" y="{py - 6:.2f}" font-family="sans-serif" font-size="12">{int(row["bias_v"])} V</text>']
        parts += [f'<text x="{left + pw/2}" y="{top + ph + 35}" text-anchor="middle" font-family="sans-serif" font-size="13">x: device depth (um)</text>', f'<text x="{left - 38}" y="{top + ph/2}" transform="rotate(-90 {left - 38} {top + ph/2})" text-anchor="middle" font-family="sans-serif" font-size="13">y: lateral coordinate (um)</text>']
    parts.append('<text x="500" y="408" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#6a3d9a">Purple: frozen direction=(1,0) strict-interior Silicon track; dots: ImpactIonization maxima</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def final_bias_from_plt(path: Path, high_terminal: str) -> float:
    text = path.read_text(encoding="utf-8-sig")
    dataset_match = re.search(r"datasets\s*=\s*\[(.*?)\]\s*functions\s*=", text, re.DOTALL)
    data_match = re.search(r"\bData\s*\{(.*)\}\s*$", text, re.DOTALL)
    if dataset_match is None or data_match is None:
        raise ValueError(f"unsupported field PLT: {path}")
    datasets = re.findall(r'"([^"]+)"', dataset_match.group(1))
    values = [float(token) for token in FLOAT.findall(data_match.group(1))]
    if not datasets or len(values) % len(datasets):
        raise ValueError(f"field PLT cardinality mismatch: {path}")
    voltage_name = f"{high_terminal} InnerVoltage"
    if voltage_name not in datasets:
        raise ValueError(f"missing {voltage_name}: {path}")
    index = datasets.index(voltage_name)
    return values[-len(datasets) + index]


def distance_to_segment(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    fraction = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + fraction * dx), py - (y1 + fraction * dy))


def boundary_audit(spec: dict, family: str, point: tuple[float, float]) -> dict:
    x, y = point
    drift = value(spec, "drift_thickness")
    oxide_thickness = value(spec, "gate_oxide_thickness")
    oxide_tip_x = 3.13 + oxide_thickness
    lower_tip_y = 2.1 - oxide_thickness
    upper_tip_y = 2.7 + oxide_thickness
    oxide_distance = distance_to_segment(point, (oxide_tip_x, lower_tip_y), (oxide_tip_x, upper_tip_y))
    record = {
        "point_um": [x, y],
        "distance_to_si_oxide_tip_segment_um": oxide_distance,
        "distance_to_back_silicon_boundary_um": drift - x,
        "distance_to_nearest_lateral_silicon_boundary_um": min(y, 6.0 - y),
    }
    if family == "IGBT":
        body_depth = value(spec, "body_implant_depth")
        body_start = value(spec, "body_implant_y_start")
        body_end = value(spec, "body_implant_y_end")
        record.update({
            "junction_reference": "nominal P-body/drift ValueAtDepth segment from the frozen DSL; not a proprietary-junction reconstruction",
            "junction_reference_segment_um": [[body_depth, body_start], [body_depth, body_end]],
            "distance_to_junction_reference_um": distance_to_segment(point, (body_depth, body_start), (body_depth, body_end)),
        })
    else:
        termination_x = drift - value(spec, "p_pillar_drain_setback")
        pillar_start = value(spec, "pillar_pitch") / 2.0
        pillar_end = pillar_start + value(spec, "p_pillar_width")
        record.update({
            "junction_reference": "SJ P-pillar termination segment from the frozen DSL; nearest named P/N-junction termination",
            "junction_reference_segment_um": [[termination_x, pillar_start], [termination_x, pillar_end]],
            "distance_to_junction_reference_um": distance_to_segment(point, (termination_x, pillar_start), (termination_x, pillar_end)),
        })
    return record


def main() -> None:
    rows = []
    run_records = []
    extracted_by_family: dict[str, list[dict]] = {"IGBT": [], "MOSFET": []}
    for family, bias in CASES:
        case_id = f"{family}650_FIELD_V{bias}"
        run_dir, manifest = successful_run(case_id)
        evidence = run_svisual(run_dir, manifest, family, bias)
        extracted = evidence["extracted"]
        global_emax = extracted["electric_field_max"]
        impact_max = extracted["impact_ionization_max"]
        track_emax = extracted["track_path_electric_field_max"]
        track_impact_max = extracted["track_path_impact_ionization_max"]
        spec = read_json(DSL[family])
        drift = value(spec, "drift_thickness")
        global_x, global_y = map(float, global_emax["position_um"])
        impact_x, impact_y = map(float, impact_max["position_um"])
        track_x, track_y = map(float, track_emax["position_um"])
        for label, x, y in (
            ("global Emax", global_x, global_y),
            ("impact-ionization maximum", impact_x, impact_y),
            ("active-path Emax", track_x, track_y),
        ):
            if not (0.0 <= x <= drift and 0.0 <= y <= 6.0):
                raise ValueError(f"{case_id}: {label} is outside the documented Silicon bounds")
        high_terminal = "Collector" if family == "IGBT" else "Drain"
        plt_path = run_dir / "artifacts" / f"{case_id.lower()}.plt"
        actual_bias = final_bias_from_plt(plt_path, high_terminal)
        if not math.isclose(actual_bias, float(bias), rel_tol=0.0, abs_tol=1e-6):
            raise ValueError(f"{case_id}: actual high-terminal bias {actual_bias} V does not match {bias} V")
        boundary = boundary_audit(spec, family, (impact_x, impact_y))
        input_records = {Path(item["relative_path"]).name: item for item in manifest["inputs"]}
        deck_record = next(item for name, item in input_records.items() if name.endswith(".cmd"))
        metadata_record = next(item for name, item in input_records.items() if name.endswith(".json"))
        row = {
            "device_family": family,
            "bias_v": bias,
            "actual_bias_v": actual_bias,
            "mesh_sha256": evidence["mesh_sha256"],
            "run_id": manifest["run_id"],
            "cpu_core": manifest["cpu_core"],
            "global_emax_v_per_cm": float(global_emax["value"]),
            "global_emax_x_um": global_x,
            "global_emax_y_um": global_y,
            "impact_ionization_max_cm3_s": float(impact_max["value"]),
            "impact_max_x_um": impact_x,
            "impact_max_y_um": impact_y,
            "track_y_um": float(extracted["track_selection"]["track_y_um"]),
            "track_path_emax_v_per_cm": float(track_emax["value"]),
            "track_path_emax_x_um": track_x,
            "track_path_impact_max_cm3_s": float(track_impact_max["value"]),
            "distance_to_si_oxide_um": boundary["distance_to_si_oxide_tip_segment_um"],
            "distance_to_junction_reference_um": boundary["distance_to_junction_reference_um"],
            "distance_to_back_si_boundary_um": boundary["distance_to_back_silicon_boundary_um"],
            "distance_to_lateral_si_boundary_um": boundary["distance_to_nearest_lateral_silicon_boundary_um"],
            "source_tdr_sha256": extracted["source_tdr_sha256"],
            "source_tdr_size_bytes": extracted["source_tdr_size_bytes"],
            "deck_sha256": deck_record["sha256"],
            "metadata_sha256": metadata_record["sha256"],
            "source_plt_sha256": sha256(plt_path),
        }
        rows.append(row)
        extracted_by_family[family].append(row)
        run_records.append({
            "case_id": case_id,
            "bias_v": bias,
            "actual_bias_v": actual_bias,
            "run_id": manifest["run_id"],
            "run_manifest": relative(run_dir / "run_manifest.json"),
            "run_manifest_sha256": sha256(run_dir / "run_manifest.json"),
            "deck_sha256": deck_record["sha256"],
            "metadata_sha256": metadata_record["sha256"],
            "mesh_sha256": evidence["mesh_sha256"],
            "source_plt": relative(plt_path),
            "source_plt_sha256": sha256(plt_path),
            "field_tdr": relative(evidence["local_tdr"]),
            "field_tdr_sha256": sha256(evidence["local_tdr"]),
            "field_extraction": relative(evidence["local_extraction"]),
            "field_extraction_sha256": sha256(evidence["local_extraction"]),
            "scheduling_evidence": manifest["scheduling_evidence"],
        })

    tracks = {}
    sensitive_regions = {
        "IGBT": "trench oxide tip / P-body-to-drift high-impact-ionization region",
        "MOSFET": "drain-side high-impact-ionization region adjacent to the SJ P-pillar termination",
    }
    for family, family_rows in extracted_by_family.items():
        spec = read_json(DSL[family])
        representative = next(row for row in family_rows if row["bias_v"] == 500)
        representative_run = next(record for record in run_records if record["case_id"] == f"{family}650_FIELD_V500")
        oxide_tip_x = 3.13 + value(spec, "gate_oxide_thickness")
        start_x = round(oxide_tip_x + 0.01, 6)
        end_x = round(value(spec, "drift_thickness") - 0.01, 6)
        track_y = round(representative["track_y_um"], 12)
        if not (start_x < end_x and 0.0 < track_y < 6.0):
            raise ValueError(f"{family}: safe Silicon track construction failed")
        boundary = boundary_audit(
            spec,
            family,
            (representative["impact_max_x_um"], representative["impact_max_y_um"]),
        )
        tracks[family] = {
            "status": "VERIFIED_FROZEN_NOT_SEED",
            "selection_rule": "500 V impact-ionization maximum defines the sensitive lateral coordinate; boundary maxima are retained as context but are not used as the track selector; the path starts 0.01 um beyond the oxide tip and ends 0.01 um before the back Silicon boundary",
            "seed_track_reused": False,
            "sensitive_region": sensitive_regions[family],
            "mesh_sha256": representative["mesh_sha256"],
            "representative_bias_v": 500,
            "representative_run_id": representative["run_id"],
            "representative_deck_sha256": representative["deck_sha256"],
            "representative_run_manifest_sha256": representative_run["run_manifest_sha256"],
            "representative_field_tdr_sha256": representative_run["field_tdr_sha256"],
            "representative_field_extraction_sha256": representative_run["field_extraction_sha256"],
            "global_emax_boundary_context": {
                "value_v_per_cm": representative["global_emax_v_per_cm"],
                "position_um": [representative["global_emax_x_um"], representative["global_emax_y_um"]],
                "interpretation": "retained boundary/contact maximum; not used to freeze the HeavyIon path",
            },
            "sensitive_marker": {
                "field": "ImpactIonization",
                "value_cm3_s": representative["impact_ionization_max_cm3_s"],
                "position_um": [representative["impact_max_x_um"], representative["impact_max_y_um"]],
            },
            "track_path_emax": {
                "value_v_per_cm": representative["track_path_emax_v_per_cm"],
                "position_um": [representative["track_path_emax_x_um"], track_y],
            },
            "start_um": [start_x, track_y],
            "direction": [1.0, 0.0],
            "length_um": round(end_x - start_x, 6),
            "end_um": [end_x, track_y],
            "oxide_tip_x_um": oxide_tip_x,
            "silicon_bounds_um": {"x_min": 0.0, "x_max": value(spec, "drift_thickness"), "y_min": 0.0, "y_max": 6.0},
            "strict_interior_margin_um": 0.01,
            "boundary_distances_from_sensitive_marker": boundary,
            "all_bias_sensitive_markers": [
                {
                    "bias_v": row["bias_v"],
                    "impact_ionization_max_cm3_s": row["impact_ionization_max_cm3_s"],
                    "position_um": [row["impact_max_x_um"], row["impact_max_y_um"]],
                    "track_path_emax_v_per_cm": row["track_path_emax_v_per_cm"],
                }
                for row in family_rows
            ],
        }

    DATA.mkdir(parents=True, exist_ok=True)
    json_path = DATA / "field_track_localization_v2.json"
    csv_path = DATA / "field_track_localization_v2.csv"
    figure_path = FIGURES / "field_track_localization_v2.svg"
    output = {
        "schema_version": "650v_field_track_localization/v2",
        "status": "VERIFIED_TRACKS_FROZEN_HEAVYION_NOT_AUTHORIZED",
        "coordinate_system": {"x": "device depth from top surface", "y": "lateral cell coordinate", "unit": "um"},
        "field_unit": "V/cm (Sentaurus native electric-field magnitude)",
        "impact_ionization_unit": "cm^-3 s^-1 (Sentaurus native field)",
        "selection_policy": "retain global Silicon Emax as boundary context; freeze the non-seed path from the 500 V ImpactIonization sensitive marker and audit the strict-interior path Emax",
        "runs": run_records,
        "field_rows": rows,
        "tracks": tracks,
        "all_tracks_frozen": all(track["status"] == "VERIFIED_FROZEN_NOT_SEED" for track in tracks.values()),
        "heavy_ion_authorized": False,
    }
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    FIGURES.mkdir(parents=True, exist_ok=True)
    figure_path.write_text(svg_plot(rows, tracks), encoding="utf-8")
    report_lines = [
        "# 650 V IGBT / MOSFET 关断电场与入射轨迹定位",
        "",
        "状态：`VERIFIED_TRACKS_FROZEN_HEAVYION_NOT_AUTHORIZED`。六份已有 325/400/500 V TDR 被复用，没有重复 SDevice 仿真；v1 边界最大值记录保留，v2 轻量证据见 `data/field_track_localization_v2.json/csv`。此证据本身仍不授权 HeavyIon。",
        "",
        "全域 Silicon `Emax` 位于 x=0 接触/顶表面边界且随偏压不变，因此只保留为边界背景，不用于选轨。敏感区由 `ImpactIonization` 最大值定位，冻结轨迹上的 `Emax` 另行用严格硅内 cutline 复核。",
        "",
        "| 器件 | 偏压/实际偏压 (V) | 全域 Emax (V/cm) @ (x,y) um | ImpactIonization max @ (x,y) um | 轨迹 Emax (V/cm) | run ID | core |",
        "|---|---:|---|---|---:|---|---:|",
    ]
    for row in rows:
        report_lines.append(
            f"| {row['device_family']} | {row['bias_v']} / {row['actual_bias_v']:.6f} | "
            f"{row['global_emax_v_per_cm']:.6e} @ ({row['global_emax_x_um']:.6f}, {row['global_emax_y_um']:.6f}) | "
            f"{row['impact_ionization_max_cm3_s']:.6e} @ ({row['impact_max_x_um']:.6f}, {row['impact_max_y_um']:.6f}) | "
            f"{row['track_path_emax_v_per_cm']:.6e} | `{row['run_id']}` | {row['cpu_core']} |"
        )
    report_lines += ["", "## 冻结轨迹", ""]
    for family, track in tracks.items():
        distances = track["boundary_distances_from_sensitive_marker"]
        report_lines.append(
            f"- {family}: `{track['sensitive_region']}`；500 V ImpactIonization marker=({track['sensitive_marker']['position_um'][0]:.6f}, {track['sensitive_marker']['position_um'][1]:.6f}) um。"
        )
        report_lines.append(
            f"  - StartPoint=({track['start_um'][0]:.6f}, {track['start_um'][1]:.6f}), Direction=(1, 0), Length={track['length_um']:.6f} um，终点=({track['end_um'][0]:.6f}, {track['end_um'][1]:.6f})；`seed_track_reused=false`。"
        )
        report_lines.append(
            f"  - 敏感标记到 Si/Oxide tip segment、命名结参考、背面 Si 边界、最近横向 Si 边界的距离分别为 {distances['distance_to_si_oxide_tip_segment_um']:.6f} / {distances['distance_to_junction_reference_um']:.6f} / {distances['distance_to_back_silicon_boundary_um']:.6f} / {distances['distance_to_nearest_lateral_silicon_boundary_um']:.6f} um。"
        )
    report_lines += [
        "",
        "轨迹由 500 V ImpactIonization 敏感标记的 y 坐标确定；若标记落在横向边界，按预先记录的 0.01 um 严格硅内裕量夹紧。深度方向从氧化层尖端之后 0.01 um 开始，在背面边界之前 0.01 um 结束。它们不是 DSL 中的 seed track，也没有在本阶段运行 HeavyIon。",
        "",
        f"![Emax 与冻结轨迹](figures/{figure_path.name})",
    ]
    REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"field_localization=VERIFIED evidence={json_path} report={REPORT}")


if __name__ == "__main__":
    main()