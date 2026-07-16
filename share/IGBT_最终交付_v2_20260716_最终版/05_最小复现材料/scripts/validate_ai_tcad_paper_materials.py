"""Validate the small public AI-TCAD paper material package."""
from __future__ import annotations

import csv
import json
import re
import sys
import xml.etree.ElementTree as element_tree
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "docs" / "changes" / "2026-07-15-ai-assisted-tcad-paper-materials"
REQUIRED_DIRS = {
    "manuscript", "evidence-map", "dataset-codebook", "data-public", "figures",
    "tables", "environment", "private-restricted-index",
}
REQUIRED_FILES = {
    "README.md",
    "验证记录.md",
    "manuscript/中文论文初稿.md",
    "manuscript/AI使用披露.md",
    "evidence-map/证据链与主张审计.md",
    "dataset-codebook/数据字典.md",
    "environment/执行环境与资源边界.md",
    "private-restricted-index/受限材料索引.md",
    "figures/图件规格.md",
    "tables/T04_主张对抗审计.md",
}
REQUIRED_CSV = {
    "claims.csv", "stage-evidence.csv", "artifact-links.csv", "lineage.csv",
    "failure-taxonomy.csv", "figure-table-map.csv",
}
EXPECTED_HEADERS = {
    "claims.csv": {"claim_id", "stage_id", "status"},
    "stage-evidence.csv": {"stage_id", "denominator", "numerator"},
    "artifact-links.csv": {"event_id", "attempt_id", "run_id", "artifact_id", "sha256", "claim_id"},
    "lineage.csv": {"stage_id", "event_id", "attempt_id", "run_id", "artifact_id", "sha256", "claim_id"},
    "failure-taxonomy.csv": {"failure_id", "canonical_event_or_attempt"},
    "figure-table-map.csv": {"figure_or_table_id", "data_source"},
}
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")
# Deliberately match only concrete private path values.  Prose examples and
# regex source such as ``[A-Za-z]:[\\\\/]`` are allowed in boundary docs.
PRIVATE_PATH_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_<])(?:"
    r"[A-Z]:[\\/](?:Users|home|Program Files|Windows|Temp|秘密|private)[^\r\n`<>\"']*"
    r"|/home/(?:tcad|[A-Za-z0-9_.-]+)(?:/[^\r\n`<>\"']*)?"
    r"|" + r"/" + r"usr/synopsys/[^\r\n`<>\"']*"
    r")"
)
CREDENTIAL_BLOCK_RE = re.compile(r"-----BEGIN\s+(?:(?:RSA|EC|OPENSSH|DSA)\s+)?PRIVATE KEY-----")


def fail(message: str) -> None:
    raise ValueError(message)


def validate_required_files() -> int:
    missing = sorted(relative for relative in REQUIRED_FILES if not (ROOT / relative).is_file())
    if missing:
        fail(f"missing required material files: {missing}")
    disclosure = (ROOT / "manuscript" / "AI使用披露.md").read_text(encoding="utf-8")
    for phrase in ("研究者", "人工基线", "token", "不声称", "最终责任"):
        if phrase not in disclosure:
            fail(f"AI disclosure missing required boundary phrase: {phrase}")
    return len(REQUIRED_FILES)


def validate_csvs() -> int:
    count = 0
    for name in sorted(REQUIRED_CSV):
        path = ROOT / "data-public" / name
        if not path.is_file():
            fail(f"missing CSV: {path}")
        try:
            raw = path.read_bytes()
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            fail(f"non-UTF-8 CSV: {path}: {error}")
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            headers = set(reader.fieldnames or [])
            if not rows:
                fail(f"empty CSV: {path}")
            if None in headers or not EXPECTED_HEADERS[name].issubset(headers):
                fail(f"invalid CSV header: {path}: {sorted(headers)}")
            if any(PRIVATE_PATH_RE.search(value) for row in rows for value in row.values() if value):
                fail(f"private absolute path in CSV: {path}")
        count += 1
    return count


def validate_json() -> int:
    count = 0
    manifest_path = ROOT / "data-public" / "public-materials.json"
    schema_path = ROOT / "dataset-codebook" / "public-materials.schema.json"
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    with schema_path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    if manifest.get("privacy") != {"credentials_included": False, "absolute_private_paths_included": False}:
        fail("public manifest privacy flags are not fail-closed")
    if schema.get("title") != "AI-assisted TCAD public material manifest":
        fail("unexpected public material schema")
    for dataset in manifest.get("datasets", []):
        relative = dataset.get("path", "")
        destination = (ROOT / relative).resolve()
        if not destination.is_file() or ROOT not in destination.parents:
            fail(f"manifest dataset missing/outside package: {relative}")
        if PRIVATE_PATH_RE.search(relative):
            fail(f"private path in public manifest: {relative}")
    count += 2
    return count


def validate_svgs() -> int:
    paths = sorted((ROOT / "figures").glob("F*.svg"))
    if len(paths) != 5:
        fail(f"expected five new SVG figures, found {len(paths)}")
    for path in paths:
        root = element_tree.parse(path).getroot()
        if not root.tag.endswith("svg"):
            fail(f"not SVG XML: {path}")
    return len(paths)


def validate_markdown_links_and_privacy() -> tuple[int, int]:
    links = 0
    scanned = 0
    text_suffixes = {".md", ".csv", ".json", ".txt", ".svg"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            fail(f"non-UTF-8 text file {path.relative_to(ROOT)}: {error}")
        scanned += 1
        if PRIVATE_PATH_RE.search(text) or CREDENTIAL_BLOCK_RE.search(text):
            fail(f"absolute private path or credential block in {path.relative_to(ROOT)}")
        if path.suffix.lower() != ".md":
            continue
        for target in LINK_RE.findall(text):
            if "://" in target or target.startswith("mailto:"):
                continue
            destination = (path.parent / target).resolve()
            if not destination.exists() or ROOT not in destination.parents and destination != ROOT:
                fail(f"broken/outside relative link in {path.relative_to(ROOT)}: {target}")
            links += 1
    return scanned, links


def validate_relations() -> None:
    claims_path = ROOT / "data-public" / "claims.csv"
    stages_path = ROOT / "data-public" / "stage-evidence.csv"
    with claims_path.open("r", encoding="utf-8", newline="") as handle:
        claims = list(csv.DictReader(handle))
    with stages_path.open("r", encoding="utf-8", newline="") as handle:
        stages = list(csv.DictReader(handle))
    claim_ids = {row["claim_id"] for row in claims}
    stage_ids = {row["stage_id"] for row in stages}
    for row in claims:
        if row["stage_id"] not in stage_ids:
            fail(f"claim references missing stage: {row['claim_id']} -> {row['stage_id']}")
    for name in ("artifact-links.csv", "lineage.csv"):
        with (ROOT / "data-public" / name).open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if row.get("claim_id") not in claim_ids:
                fail(f"{name} references missing claim: {row.get('claim_id')}")
    for row in claims:
        if not re.fullmatch(r"C\d+", row["claim_id"]):
            fail(f"invalid claim id: {row['claim_id']}")


def main() -> int:
    missing = REQUIRED_DIRS - {path.name for path in ROOT.iterdir() if path.is_dir()}
    if missing:
        fail(f"missing directories: {sorted(missing)}")
    required_file_count = validate_required_files()
    csv_count = validate_csvs()
    json_count = validate_json()
    validate_relations()
    svg_count = validate_svgs()
    markdown_count, link_count = validate_markdown_links_and_privacy()
    print(f"PASS: {required_file_count} required files, {csv_count} CSV, {json_count} JSON, {svg_count} SVG, {markdown_count} UTF-8 text files, {link_count} relative links")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, csv.Error, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)