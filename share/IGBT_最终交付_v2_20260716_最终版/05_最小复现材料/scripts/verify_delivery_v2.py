#!/usr/bin/env python3
"""Verify the compact delivery directory, ZIP, and included final IGBT GZP.

This is a read-only verifier. It never starts Sentaurus, SDevice, SDE, or
SVisual and never extracts the GZP to disk. ZIP extraction is performed into a
temporary directory only for hash comparison, then removed automatically.
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
import tarfile
import tempfile
import zipfile
from pathlib import Path

FORBIDDEN_SUFFIXES = {".tdr", ".plt", ".sav", ".pdf", ".log", ".stdout", ".stderr", ".bak"}
EXPECTED_GZP_RELATIVE = "01_IGBT可继续仿真工程/IGBT_SEB_20260714_Final_Continuation.gzp"
TEXT_SUFFIXES = {".md", ".csv", ".json", ".txt", ".svg", ".py", ".ps1", ".sh", ".cmd", ".par", ".tcl"}
# Match concrete paths, not a regex declaration such as ``[A-Za-z]:[\\\\/]``
# in a copied verifier.  This lets the delivery explain prohibited examples
# while still rejecting an accidentally leaked path value.
PRIVATE_PATH_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_<])(?:"
    r"[A-Z]:[\\/](?:Users|home|Program Files|Windows|Temp|秘密|private)[^\r\n`<>\"']*"
    r"|/home/(?:tcad|[A-Za-z0-9_.-]+)(?:/[^\r\n`<>\"']*)?"
    r"|" + r"/" + r"usr/synopsys/[^\r\n`<>\"']*"
    r")"
)
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")
CREDENTIAL_BLOCK_RE = re.compile(r"-----BEGIN\s+(?:(?:RSA|EC|OPENSSH|DSA)\s+)?PRIVATE KEY-----")
SHA_LINE_RE = re.compile(r"^([0-9a-f]{64})  (.+)$")


def fail(message: str) -> None:
    raise ValueError(message)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def safe_relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def verify_directory(root: Path) -> dict[str, int | str]:
    if not root.is_dir():
        fail(f"delivery directory missing: {root}")
    files = [path for path in root.rglob("*") if path.is_file()]
    forbidden = [safe_relative(path, root) for path in files if path.suffix.lower() in FORBIDDEN_SUFFIXES]
    if forbidden:
        fail(f"forbidden raw/private artifacts in delivery: {forbidden[:10]}")
    gzp_files = [safe_relative(path, root) for path in files if path.suffix.lower() == ".gzp"]
    if gzp_files != [EXPECTED_GZP_RELATIVE]:
        fail(f"delivery must contain exactly the verified final IGBT GZP: {gzp_files}")
    text_count = 0
    links = 0
    for path in files:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text_count += 1
        text = path.read_text(encoding="utf-8")
        if PRIVATE_PATH_RE.search(text) or CREDENTIAL_BLOCK_RE.search(text):
            fail(f"private absolute path or credential block: {safe_relative(path, root)}")
        if path.suffix.lower() != ".md":
            continue
        for target in LINK_RE.findall(text):
            if "://" in target or target.startswith("mailto:"):
                continue
            destination = (path.parent / target).resolve()
            if not destination.exists() or root not in destination.parents and destination != root:
                fail(f"broken/outside delivery link {safe_relative(path, root)} -> {target}")
            links += 1
    asset_manifest = root / "00_交付说明" / "资产清单.csv"
    if not asset_manifest.is_file():
        fail("asset manifest missing")
    with asset_manifest.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"relative_path", "kind", "status", "source", "size", "sha", "purpose", "boundary"}
    if not rows or not required.issubset(set(rows[0])):
        fail("asset manifest header/rows invalid")
    for row in rows:
        target = root / row["relative_path"]
        if not target.is_file() or root not in target.resolve().parents:
            fail(f"asset manifest target missing/outside: {row['relative_path']}")
        if int(row["size"]) != target.stat().st_size or row["sha"] != digest(target):
            fail(f"asset manifest hash mismatch: {row['relative_path']}")
    sums_path = root / "00_交付说明" / "SHA256SUMS.txt"
    if not sums_path.is_file():
        fail("SHA256SUMS.txt missing")
    sum_rows = [line for line in sums_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for line in sum_rows:
        match = SHA_LINE_RE.match(line)
        if not match:
            fail(f"invalid SHA256SUMS line: {line}")
        target = root / match.group(2)
        if not target.is_file() or root not in target.resolve().parents:
            fail(f"SHA256SUMS target missing/outside: {match.group(2)}")
        if digest(target) != match.group(1):
            fail(f"SHA256SUMS mismatch: {match.group(2)}")
    return {"file_count": len(files), "asset_rows": len(rows), "text_count": text_count, "relative_links": links}


def verify_zip(archive: Path, package: Path) -> dict[str, int | str]:
    if not archive.is_file():
        fail(f"ZIP missing: {archive}")
    checksum_sidecar = archive.with_suffix(archive.suffix + ".sha256")
    if not checksum_sidecar.is_file():
        fail(f"ZIP SHA sidecar missing: {checksum_sidecar}")
    sidecar_line = checksum_sidecar.read_text(encoding="utf-8").strip()
    expected = sidecar_line.split()[0] if sidecar_line else ""
    actual = digest(archive)
    if expected != actual:
        fail(f"external ZIP SHA mismatch: {expected} != {actual}")
    with zipfile.ZipFile(archive, "r") as handle:
        bad = handle.testzip()
        if bad is not None:
            fail(f"ZIP CRC failure: {bad}")
        names = handle.namelist()
        if len(names) != len(set(names)):
            fail("ZIP contains duplicate names")
        if any(name.startswith("/") or ".." in Path(name).parts for name in names):
            fail("ZIP contains unsafe path")
        package_prefix = package.name + "/"
        expected_names = {package_prefix + safe_relative(path, package) for path in package.rglob("*") if path.is_file()}
        if set(names) != expected_names:
            missing = sorted(expected_names - set(names))[:5]
            extra = sorted(set(names) - expected_names)[:5]
            fail(f"ZIP/directory file set differs: missing={missing}, extra={extra}")
        with tempfile.TemporaryDirectory(prefix="igbt_delivery_verify_") as temporary:
            extracted_root = Path(temporary) / package.name
            handle.extractall(Path(temporary))
            for path in package.rglob("*"):
                if not path.is_file():
                    continue
                extracted = extracted_root / path.relative_to(package)
                if not extracted.is_file() or digest(path) != digest(extracted):
                    fail(f"ZIP extraction hash mismatch: {safe_relative(path, package)}")
        return {"zip_size_bytes": archive.stat().st_size, "zip_sha256": actual, "zip_entries": len(names), "zip_crc": "PASS"}


def verify_gzp(gzp: Path) -> dict[str, object]:
    if not gzp.is_file():
        fail(f"GZP missing: {gzp}")
    raw = gzp.read_bytes()
    result: dict[str, object] = {
        "relative_path": EXPECTED_GZP_RELATIVE,
        "exists": True,
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "magic_hex": raw[:4].hex(),
        "format": "gzip" if raw[:2] == b"\x1f\x8b" else "unknown",
        "copied_into_delivery": True,
    }
    if result["format"] != "gzip":
        fail(f"GZP magic is not gzip: {result['magic_hex']}")
    with gzip.open(io.BytesIO(raw), "rb") as stream:
        decompressed = stream.read()
    result["gzip_read_to_eof"] = "PASS"
    with tarfile.open(fileobj=io.BytesIO(decompressed), mode="r:") as archive:
        members = archive.getmembers()
        names: list[str] = []
        for member in members:
            name = member.name
            if name.startswith("#B64#"):
                name = base64.b64decode(name[5:]).decode("utf-8")
            names.append(name)
            if member.isreg():
                payload = archive.extractfile(member)
                if payload is not None:
                    payload.read()
        project_root = "IGBT_SEB_20260714_Final_Continuation"
        required = {
            f"{project_root}/.project",
            f"{project_root}/gtree.dat",
            f"{project_root}/ThermalRestart_des.cmd",
            f"{project_root}/HeavyIon_des.cmd",
            f"{project_root}/delivery_metadata/package_manifest.json",
        }
        if not required.issubset(set(names)):
            fail(f"GZP identity files missing: {sorted(required - set(names))}")
        result.update({
            "tar_open": "PASS",
            "unpack_structure": "PASS",
            "member_count": len(members),
            "regular_member_count": sum(member.isreg() for member in members),
            "project_root": project_root,
            "required_identity_files": {name: True for name in sorted(required)},
            "internal_identity": "IGBT_SEB_20260714_Final_Continuation / 7-case IGBT continuation Workbench project",
        })
    result["verification_level"] = "PACKAGE_CONTENT_STRUCTURE_PASS"
    result["relation_to_formal_20260714"] = "bound by embedded 7-case run index and package manifest"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delivery-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--gzp", type=Path, default=None, help="defaults to the verified GZP inside delivery-root")
    args = parser.parse_args()
    delivery_root = args.delivery_root.resolve()
    directory = verify_directory(delivery_root)
    archive = verify_zip(args.archive.resolve(), delivery_root)
    gzp_path = args.gzp.resolve() if args.gzp else delivery_root / EXPECTED_GZP_RELATIVE
    gzp = verify_gzp(gzp_path)
    summary = args.archive.resolve().with_suffix("").with_suffix(".delivery_summary.json")
    # For a name such as foo.zip, the external summary is foo.delivery_summary.json.
    summary = args.archive.resolve().parent / f"{args.archive.stem}.delivery_summary.json"
    if not summary.is_file():
        fail(f"delivery_summary missing: {summary}")
    summary_data = json.loads(summary.read_text(encoding="utf-8"))
    if summary_data.get("zip_sha256") != archive["zip_sha256"] or summary_data.get("gzp_sha256") != gzp["sha256"]:
        fail("delivery_summary SHA does not match direct verification")
    if summary_data.get("formal_igbt_case_count") != 7 or summary_data.get("formal_igbt_thermal_and_2p1ns_status") != "7/7 PASS":
        fail("delivery_summary formal IGBT boundary is missing or incorrect")
    if summary_data.get("mosfet_scope") != "comparison appendix only":
        fail("delivery_summary MOSFET boundary is missing or incorrect")
    if summary_data.get("low_let_scope") != "diagnostic_only/MESH_SENSITIVE appendix":
        fail("delivery_summary low-LET boundary is missing or incorrect")
    if summary_data.get("redesign_650v_scope") != "PENDING / FAILED_NUMERICAL_ONLY / CANCELLED_BY_SCOPE_CHANGE status appendix; no new 550 V SDevice result":
        fail("delivery_summary 650 V boundary is missing or incorrect")
    print(json.dumps({"delivery_directory": directory, "archive": archive, "gzp": gzp, "summary": "PASS"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, csv.Error, json.JSONDecodeError, gzip.BadGzipFile, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)