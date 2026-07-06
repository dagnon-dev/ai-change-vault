from __future__ import annotations

import re
import shutil
from collections import defaultdict
from pathlib import Path

from .config import AICVConfig, find_project_root, load_config
from .models import BackupResult, CompactBackupEntry, CompactBackupManifest
from .session_log import append_session_log
from .utils import copy_tree_filtered, ensure_directory, file_hash, slugify, utc_now

BACKUP_RE = re.compile(r"^turn-(\d+)-")
COMPACT_BACKUP_MANIFEST = "manifest.json"


def create_backup(
    message: str,
    *,
    root: Path | None = None,
    config: AICVConfig | None = None,
) -> BackupResult:
    project_root = find_project_root(root)
    active_config = config or load_config(project_root)
    backup_root = active_config.backup_path(project_root)
    ensure_directory(backup_root)

    turn_number = next_turn_number(backup_root)
    timestamp = utc_now()
    backup_id = f"turn-{turn_number:03d}-{timestamp:%Y%m%d-%H%M%S}-{slugify(message)}"
    destination = backup_root / backup_id
    ensure_directory(destination)
    files_copied = copy_tree_filtered(project_root, destination, active_config.excludes)

    result = BackupResult(
        turn_number=turn_number,
        backup_id=backup_id,
        message=message,
        path=destination,
        timestamp=timestamp,
        files_copied=files_copied,
    )
    append_session_log(
        project_root,
        active_config,
        "backup",
        [
            f"message: {message}",
            f"backup: {destination.as_posix()}",
            f"files copied: {files_copied}",
        ],
    )
    prune_backups(project_root, active_config)
    return result


def build_compact_backup(
    root: Path,
    config: AICVConfig,
    turn_id: str,
    *,
    backup_before: str | None = None,
    backup_after: str | None = None,
) -> Path | None:
    if not backup_before or not backup_after:
        return None

    before_root = _resolve_backup_root(root, backup_before)
    after_root = _resolve_backup_root(root, backup_after)
    if before_root is None or after_root is None:
        return None

    backup_root = config.backup_path(root)
    ensure_directory(backup_root)
    timestamp = utc_now()
    compact_id = f"{turn_id}-{timestamp:%Y%m%d-%H%M%S}-compact"
    destination = backup_root / compact_id
    ensure_directory(destination)

    before_files = _snapshot_files(before_root)
    after_files = _snapshot_files(after_root)
    manifest = _diff_snapshots(
        turn_id=turn_id,
        before_root=before_root,
        after_root=after_root,
        before_files=before_files,
        after_files=after_files,
        created_at=timestamp,
    )

    if not manifest.entries:
        manifest.entries = []

    _copy_compact_payloads(destination, before_root, after_root, manifest.entries)
    manifest_path = destination / COMPACT_BACKUP_MANIFEST
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    prune_backups(root, config)
    return destination


def next_turn_number(backup_root: Path) -> int:
    highest = 0
    if backup_root.exists():
        for item in backup_root.iterdir():
            if not item.is_dir():
                continue
            match = BACKUP_RE.match(item.name)
            if match:
                highest = max(highest, int(match.group(1)))
    return highest + 1


def infer_backup_for_turn(root: Path, config: AICVConfig, turn_id: str) -> Path | None:
    from .utils import turn_number

    number = turn_number(turn_id)
    if number is None:
        return None
    prefix = f"turn-{number:03d}-"
    backup_root = config.backup_path(root)
    if not backup_root.exists():
        return None
    matches = sorted(
        path for path in backup_root.iterdir() if path.is_dir() and path.name.startswith(prefix)
    )
    return matches[-1] if matches else None


def list_backups(root: Path, config: AICVConfig) -> list[Path]:
    backup_root = config.backup_path(root)
    if not backup_root.exists():
        return []
    return sorted(path for path in backup_root.iterdir() if path.is_dir())


def prune_backups(root: Path, config: AICVConfig) -> None:
    retention = max(0, config.backup_retention)
    if retention == 0:
        return

    backup_root = config.backup_path(root)
    if not backup_root.exists():
        return

    backups = sorted(
        (path for path in backup_root.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in backups[retention:]:
        shutil.rmtree(path, ignore_errors=True)


def _resolve_backup_root(root: Path, backup_path: str) -> Path | None:
    candidate = Path(backup_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate if candidate.exists() and candidate.is_dir() else None


def _snapshot_files(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for item in root.rglob("*"):
        if item.is_file():
            files[item.relative_to(root).as_posix()] = file_hash(item)
    return files


def _diff_snapshots(
    *,
    turn_id: str,
    before_root: Path,
    after_root: Path,
    before_files: dict[str, str],
    after_files: dict[str, str],
    created_at,
) -> CompactBackupManifest:
    common_paths = sorted(set(before_files) & set(after_files))
    before_only = {path: before_files[path] for path in before_files.keys() - after_files.keys()}
    after_only = {path: after_files[path] for path in after_files.keys() - before_files.keys()}
    entries: list[CompactBackupEntry] = []

    for path in common_paths:
        if before_files[path] == after_files[path]:
            continue
        entries.append(
            CompactBackupEntry(
                path=path,
                status="modified",
                before_path=path,
                after_path=path,
            )
        )

    renamed, before_only, after_only = _pair_renames(before_only, after_only)
    entries.extend(renamed)

    for path in sorted(before_only):
        entries.append(
            CompactBackupEntry(
                path=path,
                status="deleted",
                before_path=path,
            )
        )

    for path in sorted(after_only):
        entries.append(
            CompactBackupEntry(
                path=path,
                status="added",
                after_path=path,
            )
        )

    return CompactBackupManifest(
        turn_id=turn_id,
        created_at=created_at,
        source_before=before_root.as_posix(),
        source_after=after_root.as_posix(),
        entries=entries,
    )


def _pair_renames(
    before_only: dict[str, str],
    after_only: dict[str, str],
) -> tuple[list[CompactBackupEntry], dict[str, str], dict[str, str]]:
    by_hash_before: dict[str, list[str]] = defaultdict(list)
    by_hash_after: dict[str, list[str]] = defaultdict(list)
    for path, digest in before_only.items():
        by_hash_before[digest].append(path)
    for path, digest in after_only.items():
        by_hash_after[digest].append(path)

    renamed: list[CompactBackupEntry] = []
    consumed_before: set[str] = set()
    consumed_after: set[str] = set()

    for digest in sorted(set(by_hash_before) & set(by_hash_after)):
        before_paths = sorted(by_hash_before[digest])
        after_paths = sorted(by_hash_after[digest])
        for before_path, after_path in zip(before_paths, after_paths, strict=False):
            if before_path == after_path:
                continue
            consumed_before.add(before_path)
            consumed_after.add(after_path)
            renamed.append(
                CompactBackupEntry(
                    path=before_path,
                    status="renamed",
                    before_path=before_path,
                    after_path=after_path,
                )
            )

    remaining_before = {
        path: digest for path, digest in before_only.items() if path not in consumed_before
    }
    remaining_after = {
        path: digest for path, digest in after_only.items() if path not in consumed_after
    }
    return renamed, remaining_before, remaining_after


def _copy_compact_payloads(
    destination: Path,
    before_root: Path,
    after_root: Path,
    entries: list[CompactBackupEntry],
) -> None:
    before_dir = destination / "before"
    after_dir = destination / "after"
    for entry in entries:
        if entry.before_path is not None:
            source = before_root / entry.before_path
            target = before_dir / entry.before_path
            ensure_directory(target.parent)
            shutil.copy2(source, target)
        if entry.after_path is not None:
            source = after_root / entry.after_path
            target = after_dir / entry.after_path
            ensure_directory(target.parent)
            shutil.copy2(source, target)
