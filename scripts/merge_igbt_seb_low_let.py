#!/usr/bin/env python3
"""Merge low-LET SVisual exports without resampling or hidden interpolation."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACTS = ROOT / "local_runtime" / "lowlet_extract_20260715"
DATA = ROOT / "docs" / "changes" / "2026-07-13-igbt-seb-现有数据复盘" / "let_scan" / "data"
FIELDS = (
    "time_s",
    "collector_inner_voltage_v",
    "collector_total_current_a_um",
    "tmax_k",
)
SERIES = (
    (
        "let0p015_thermal",
        "let0p015_thermal_raw.csv",
        (("let0p015_thermal_0to40", 4e-8), ("let0p015_thermal_40to40p7", None), ("let0p015_thermal_40p7to60", None)),
    ),
    (
        "let0p015_cold300",
        "let0p015_cold300_raw.csv",
        (("let0p015_cold300_0to40", 4e-8), ("let0p015_cold300_40to40p7", None), ("let0p015_cold300_40p7to60", None)),
    ),
    (
        "let0p15_thermal",
        "let0p15_thermal_raw.csv",
        (("let0p15_thermal_0to60", None),),
    ),
    (
        "let0p15_cold300",
        "let0p15_cold300_raw.csv",
        (("let0p15_cold300_0to50", 5e-8), ("let0p15_cold300_50to60", None)),
    ),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_segment(tag: str, inclusive_end: float | None) -> tuple[list[dict[str, str]], dict[str, object]]:
    csv_path = EXTRACTS / f"{tag}.csv"
    metadata_path = EXTRACTS / f"{tag}.json"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if tuple(rows[0]) != FIELDS:
        raise ValueError(f"unexpected columns in {csv_path}")
    if inclusive_end is not None:
        rows = [row for row in rows if float(row["time_s"]) <= inclusive_end]
    if not rows:
        raise ValueError(f"empty selected rows from {csv_path}")
    return rows, {
        "tag": tag,
        "csv_path": csv_path.relative_to(ROOT).as_posix(),
        "csv_sha256": sha256(csv_path),
        "metadata_path": metadata_path.relative_to(ROOT).as_posix(),
        "metadata_sha256": sha256(metadata_path),
        "selected_rows": len(rows),
        "selected_start_s": float(rows[0]["time_s"]),
        "selected_end_s": float(rows[-1]["time_s"]),
        "selection_end_s": inclusive_end,
    }


def merge(tags: tuple[tuple[str, float | None], ...]) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    merged: list[dict[str, str]] = []
    provenance: list[dict[str, object]] = []
    for tag, end in tags:
        rows, source = load_segment(tag, end)
        if merged and float(rows[0]["time_s"]) <= float(merged[-1]["time_s"]):
            raise ValueError(f"overlap or non-increasing segment boundary: {tag}")
        source["previous_end_s"] = float(merged[-1]["time_s"]) if merged else None
        source["boundary_gap_s"] = float(rows[0]["time_s"]) - float(merged[-1]["time_s"]) if merged else None
        merged.extend(rows)
        provenance.append(source)
    if any(float(right["time_s"]) <= float(left["time_s"]) for left, right in zip(merged, merged[1:])):
        raise ValueError("merged time axis is not strictly increasing")
    return merged, provenance


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {"schema": "low_let_svisual_merge/v1", "series": []}
    for series_id, filename, tags in SERIES:
        rows, sources = merge(tags)
        output = DATA / filename
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        manifest["series"].append({
            "series_id": series_id,
            "output_path": output.relative_to(ROOT).as_posix(),
            "output_sha256": sha256(output),
            "sample_count": len(rows),
            "time_start_s": float(rows[0]["time_s"]),
            "time_end_s": float(rows[-1]["time_s"]),
            "source_segments": sources,
            "resampling": "none",
        })
    output = DATA / "low_let_extraction_manifest.json"
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"merged {len(manifest['series'])} low-LET series into {DATA}")


if __name__ == "__main__":
    main()