from __future__ import annotations

import re
from pathlib import Path

from .config import AICVConfig, find_project_root, load_config
from .models import BackupResult
from .session_log import append_session_log
from .utils import copy_tree_filtered, ensure_directory, slugify, utc_now

BACKUP_RE = re.compile(r"^turn-(\d+)-")


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
    return result


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
