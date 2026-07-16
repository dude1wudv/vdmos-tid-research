#!/usr/bin/env python3
"""Validate private IGBT-SEB run archives and append them through one writer."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

MANIFEST_SCHEMA = "igbt_seb_run_manifest/v1"
EXECUTION_MODES = {
    "PARALLEL_EXPLORATORY",
    "SERIAL_CONFIRMATORY",
    "DIAGNOSTIC_CLOSURE",
}
LIFECYCLES = {"SUCCEEDED", "FAILED", "TIMED_OUT"}
REGISTRY_HEADER = [
    "run_id", "execution_mode", "worker_id", "case_id", "attempt_id",
    "parent_run_id", "lifecycle", "started_at", "ended_at",
    "staging_manifest_sha256", "merge_status", "merged_at", "merged_by",
]
LEDGERS = {
    "codex_events.csv": ("event_id", "E"),
    "tuning_steps.csv": ("tuning_id", "T"),
    "artifact_manifest.csv": ("artifact_id", "ART"),
    "case_summary.csv": (None, None),
    "run_provenance.csv": (None, None),
}
REQUIRED_FRAGMENT_HEADERS = {
    "codex_events.csv": [
        "start_time", "end_time", "phase", "case_id", "event_type", "tool",
        "action_summary", "reason_summary", "expected_result", "observed_result",
        "exit_code", "duration_s", "evidence_path", "human_intervention", "decision_scope",
    ],
    "tuning_steps.csv": [
        "case_id", "parent_run_id", "parameter", "old_value", "new_value",
        "allowed_by_plan", "trigger_evidence", "hypothesis", "expected_effect",
        "actual_effect", "status_before", "status_after", "accepted",
    ],
    "artifact_manifest.csv": [
        "case_id", "attempt_id", "kind", "local_path", "remote_path", "sha256",
        "size_bytes", "generated_at", "publicable", "source_command_id",
    ],
    "case_summary.csv": [
        "case_id", "attempt_id", "parent_run_id", "phase", "target_vce_v",
        "actual_vce_v", "let_mev_cm2_mg", "let_pc_um", "y_um", "length_um",
        "wt_um", "s_s", "time_end_s", "mesh_variant", "tmax_k", "t1680_s",
        "t2500_s", "peak_ic_a_um", "peak_power_w_um", "status", "run_dir",
        "deck_sha256", "mesh_sha256", "plt_file", "log_file", "tdr_file", "notes",
    ],
    "run_provenance.csv": [
        "run_id", "case_id", "attempt_id", "device_family", "t_init_k", "t_steady_k",
        "target_vce_v", "actual_vce_v", "parent_restart_main_sha256",
        "parent_restart_circuit_sha256", "exact_2p1ns_tdr", "exact_2p1ns_tdr_sha256",
        "field_audit_sha256", "extraction_sha256", "screenshot_manifest_sha256",
        "allocation_mode", "cpu_core", "sdevice_threads", "lease_acquired",
        "lease_released", "affinity_verification", "exit_code", "wall_time_seconds",
    ],
}
OPTIONAL_FRAGMENT_NAMES = {"run_provenance.csv"}


class MergeError(RuntimeError):
    """A staging archive is incomplete or unsafe to merge."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise MergeError(f"CSV has no header: {path}")
        rows = list(reader)
    return list(reader.fieldnames), rows


def require_na_values(row: dict[str, str | None], path: Path) -> None:
    for name, value in row.items():
        if value is None or value == "":
            raise MergeError(f"Blank value violates NA rule in {path}: {name}")


def read_fragment(path: Path, required: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    header, rows = read_csv(path)
    if header != required:
        raise MergeError(f"Unexpected fragment header: {path}")
    for row in rows:
        require_na_values(row, path)
    return header, rows


def verify_file_records(root: Path, records: Any, label: str) -> None:
    if not isinstance(records, list):
        raise MergeError(f"Manifest {label} must be a list")
    for record in records:
        if not isinstance(record, dict):
            raise MergeError(f"Manifest {label} record is invalid")
        relative = record.get("relative_path")
        expected_sha = record.get("sha256")
        expected_size = record.get("size_bytes")
        if not isinstance(relative, str) or not isinstance(expected_sha, str):
            raise MergeError(f"Manifest {label} record lacks path or SHA")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise MergeError(f"Manifest {label} SHA format invalid: {relative}")
        if not isinstance(expected_size, int) or expected_size < 0:
            raise MergeError(f"Manifest {label} size invalid: {relative}")
        path = (root / relative).resolve()
        if root.resolve() not in path.parents or not path.is_file():
            raise MergeError(f"Manifest {label} file missing or escapes archive: {relative}")
        if path.stat().st_size != expected_size or sha256_file(path) != expected_sha:
            raise MergeError(f"Manifest {label} checksum mismatch: {relative}")


def manifest_path_for(directory: Path) -> Path:
    path = directory / "run_manifest.json"
    if not path.is_file():
        raise MergeError(f"run_manifest.json missing: {directory}")
    return path


def validate_archive(directory: Path) -> dict[str, Any]:
    directory = directory.resolve()
    manifest_path = manifest_path_for(directory)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MergeError(f"Unreadable manifest {manifest_path}: {error}") from error
    required = {
        "schema_version", "run_id", "execution_mode", "worker_id", "case_id",
        "attempt_id", "parent_run_id", "lifecycle", "started_at", "ended_at",
        "inputs", "artifacts",
    }
    missing = required.difference(manifest) if isinstance(manifest, dict) else required
    if missing:
        raise MergeError(f"Manifest missing keys: {', '.join(sorted(missing))}")
    run_id = manifest["run_id"]
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id):
        raise MergeError("Manifest run_id is not portable")
    if manifest["schema_version"] != MANIFEST_SCHEMA:
        raise MergeError("Unsupported manifest schema")
    if manifest["execution_mode"] not in EXECUTION_MODES:
        raise MergeError("Unsupported execution_mode")
    if manifest["lifecycle"] not in LIFECYCLES:
        raise MergeError("Manifest lifecycle must be a closure state")
    for key in ("worker_id", "case_id", "attempt_id", "parent_run_id", "started_at", "ended_at"):
        if not isinstance(manifest[key], str) or not manifest[key]:
            raise MergeError(f"Manifest {key} is blank")
    verify_file_records(directory, manifest["inputs"], "inputs")
    verify_file_records(directory, manifest["artifacts"], "artifacts")

    fragments = directory / "fragments"
    if not fragments.is_dir():
        raise MergeError("fragments directory missing")
    fragment_rows: dict[str, list[dict[str, str]]] = {}
    for name, required_header in REQUIRED_FRAGMENT_HEADERS.items():
        fragment_path = fragments / name
        if name in OPTIONAL_FRAGMENT_NAMES and not fragment_path.is_file():
            fragment_rows[name] = []
            continue
        _, rows = read_fragment(fragment_path, required_header)
        fragment_rows[name] = rows
    closure = fragment_rows["codex_events.csv"]
    if len(closure) != 1 or closure[0]["event_type"] != "run_closure":
        raise MergeError("Exactly one run_closure event is required")
    if closure[0]["case_id"] != manifest["case_id"]:
        raise MergeError("Closure event case_id does not match manifest")
    summaries = fragment_rows["case_summary.csv"]
    if len(summaries) != 1:
        raise MergeError("Exactly one case summary row is required")
    summary = summaries[0]
    if (summary["case_id"], summary["attempt_id"]) != (manifest["case_id"], manifest["attempt_id"]):
        raise MergeError("Case summary identity does not match manifest")
    if summary["status"] != manifest["lifecycle"]:
        raise MergeError("Case summary status does not match manifest lifecycle")
    provenance = fragment_rows["run_provenance.csv"]
    if provenance:
        if len(provenance) != 1:
            raise MergeError("At most one run provenance row is allowed")
        if (
            provenance[0]["run_id"], provenance[0]["case_id"], provenance[0]["attempt_id"]
        ) != (manifest["run_id"], manifest["case_id"], manifest["attempt_id"]):
            raise MergeError("Run provenance identity does not match manifest")
        if provenance[0]["sdevice_threads"] != str(manifest.get("sdevice_threads", "NA")):
            raise MergeError("Run provenance thread count does not match manifest")
    return {
        "directory": directory,
        "manifest": manifest,
        "manifest_sha256": sha256_file(manifest_path),
        "rows": fragment_rows,
    }


def validate_archives(paths: Iterable[Path]) -> list[dict[str, Any]]:
    archives = [validate_archive(path) for path in paths]
    run_ids = [archive["manifest"]["run_id"] for archive in archives]
    if len(set(run_ids)) != len(run_ids):
        raise MergeError("Duplicate run_id in supplied archives")
    case_attempts = [
        (archive["manifest"]["case_id"], archive["manifest"]["attempt_id"])
        for archive in archives
    ]
    if len(set(case_attempts)) != len(case_attempts):
        raise MergeError("Duplicate case_id/attempt_id in supplied archives")
    return archives


def read_existing(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    return read_csv(path)


def next_identifier(rows: list[dict[str, str]], column: str, prefix: str) -> int:
    values = []
    pattern = re.compile(re.escape(prefix) + r"(\d+)$")
    for row in rows:
        match = pattern.fullmatch(row.get(column, ""))
        if match:
            values.append(int(match.group(1)))
    return max(values, default=0) + 1


def normalized_row(header: list[str], row: dict[str, str]) -> dict[str, str]:
    return {column: row.get(column, "NA") or "NA" for column in header}


def atomic_write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(normalized_row(header, row) for row in rows)
    os.replace(temp_path, path)


@contextmanager
def writer_lock(root: Path):
    lock_path = root / ".igbt_seb_merge.lock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise MergeError(f"Another merge writer holds {lock_path}") from error
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        yield
    finally:
        os.close(fd)
        lock_path.unlink(missing_ok=True)


def ensure_compatible_header(path: Path, expected: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    header, rows = read_existing(path)
    if not header:
        return expected, []
    if header != expected:
        raise MergeError(f"Existing ledger header differs; refusing migration: {path}")
    return header, rows


def apply_archives(archives: list[dict[str, Any]], ledger_root: Path, merged_by: str) -> None:
    ledger_root = ledger_root.resolve()
    registry_path = ledger_root / "run_registry.csv"
    registry_header, registry_rows = ensure_compatible_header(registry_path, REGISTRY_HEADER)
    existing_runs = {row["run_id"] for row in registry_rows}
    incoming_runs = {archive["manifest"]["run_id"] for archive in archives}
    overlap = existing_runs.intersection(incoming_runs)
    if overlap:
        raise MergeError(f"run_id already merged: {', '.join(sorted(overlap))}")

    loaded: dict[str, tuple[list[str], list[dict[str, str]]]] = {}
    for name, (id_column, _) in LEDGERS.items():
        expected = ([id_column] if id_column else []) + REQUIRED_FRAGMENT_HEADERS[name]
        loaded[name] = ensure_compatible_header(ledger_root / name, expected)
    existing_cases = {
        (row["case_id"], row["attempt_id"])
        for row in loaded["case_summary.csv"][1]
    }
    for archive in archives:
        pair = (archive["manifest"]["case_id"], archive["manifest"]["attempt_id"])
        if pair in existing_cases:
            raise MergeError(f"case summary already exists: {pair[0]}/{pair[1]}")
        existing_cases.add(pair)

    timestamp = datetime.now(timezone.utc).isoformat()
    updated = {name: list(rows) for name, (_, rows) in loaded.items()}
    for name, (id_column, prefix) in LEDGERS.items():
        header, _ = loaded[name]
        counter = next_identifier(updated[name], id_column, prefix) if id_column else 0
        for archive in archives:
            for source in archive["rows"].get(name, []):
                row = dict(source)
                if id_column:
                    row[id_column] = f"{prefix}{counter:04d}"
                    counter += 1
                updated[name].append(normalized_row(header, row))
    for archive in archives:
        manifest = archive["manifest"]
        registry_rows.append({
            "run_id": manifest["run_id"], "execution_mode": manifest["execution_mode"],
            "worker_id": manifest["worker_id"], "case_id": manifest["case_id"],
            "attempt_id": manifest["attempt_id"], "parent_run_id": manifest["parent_run_id"],
            "lifecycle": manifest["lifecycle"], "started_at": manifest["started_at"],
            "ended_at": manifest["ended_at"], "staging_manifest_sha256": archive["manifest_sha256"],
            "merge_status": "MERGED", "merged_at": timestamp, "merged_by": merged_by,
        })
    for name, (header, _) in loaded.items():
        atomic_write_csv(ledger_root / name, header, updated[name])
    atomic_write_csv(registry_path, registry_header, registry_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging_dirs", nargs="+", type=Path, help="private run directories")
    parser.add_argument("--ledger-root", type=Path, required=True, help="shared CSV directory")
    parser.add_argument("--apply", action="store_true", help="append validated fragments")
    parser.add_argument("--merged-by", default=os.environ.get("USERNAME", "NA"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        archives = validate_archives(args.staging_dirs)
        if not args.apply:
            print(f"DRY_RUN_OK validated={len(archives)} shared_files_unchanged=true")
            return 0
        with writer_lock(args.ledger_root):
            apply_archives(archives, args.ledger_root, args.merged_by or "NA")
        print(f"APPLY_OK merged={len(archives)} ledger_root={args.ledger_root}")
        return 0
    except MergeError as error:
        print(f"MERGE_REJECTED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())