from __future__ import annotations

import shutil
from pathlib import Path

from .backup import infer_backup_for_turn
from .config import AICVConfig, find_project_root, load_config
from .index import load_turns
from .models import RevertResult, TurnDocument
from .session_log import append_session_log
from .utils import ensure_directory, safe_relative_path, should_exclude, turn_matches


def revert_turn(
    turn: str,
    *,
    file: str | None = None,
    state: str = "before",
    root: Path | None = None,
    config: AICVConfig | None = None,
) -> RevertResult:
    project_root = find_project_root(root)
    active_config = config or load_config(project_root)
    document = resolve_turn(project_root, active_config, turn)
    backup_path = resolve_backup_path(project_root, active_config, document, state)

    if file:
        restored = [_restore_file(project_root, backup_path, file)]
        removed: list[str] = []
    else:
        restored, removed = _restore_project(project_root, backup_path, active_config.excludes)

    result = RevertResult(
        turn_id=document.turn_id,
        state=state,
        backup_path=backup_path,
        restored_files=restored,
        removed_paths=removed,
    )
    append_session_log(
        project_root,
        active_config,
        f"revert {document.turn_id}",
        [
            f"state: {state}",
            f"backup: {backup_path.as_posix()}",
            f"file: {file or 'full project'}",
            f"restored files: {len(restored)}",
            f"removed paths: {len(removed)}",
        ],
    )
    return result


def resolve_turn(root: Path, config: AICVConfig, turn: str) -> TurnDocument:
    for document in load_turns(root, config):
        if turn_matches(document.turn_id, turn):
            return document
    msg = f"turn not found: {turn}"
    raise FileNotFoundError(msg)


def resolve_backup_path(root: Path, config: AICVConfig, document: TurnDocument, state: str) -> Path:
    if state not in {"before", "after"}:
        msg = "state must be 'before' or 'after'"
        raise ValueError(msg)
    configured = document.backup_before if state == "before" else document.backup_after
    if configured:
        candidate = Path(configured).expanduser()
        path = candidate if candidate.is_absolute() else root / candidate
    else:
        inferred = infer_backup_for_turn(root, config, document.turn_id)
        if inferred is None:
            msg = f"no {state} backup found for {document.turn_id}"
            raise FileNotFoundError(msg)
        path = inferred
    if not path.exists() or not path.is_dir():
        msg = f"backup path does not exist: {path}"
        raise FileNotFoundError(msg)
    return path


def _restore_file(root: Path, backup_path: Path, file: str) -> str:
    relative = safe_relative_path(file)
    source = backup_path / relative
    target = root / relative
    if not source.exists() or not source.is_file():
        msg = f"file not found in backup: {file}"
        raise FileNotFoundError(msg)
    ensure_directory(target.parent)
    shutil.copy2(source, target)
    return relative.as_posix()


def _restore_project(
    root: Path, backup_path: Path, excludes: list[str]
) -> tuple[list[str], list[str]]:
    restored: list[str] = []
    removed: list[str] = []

    for item in list(root.iterdir()):
        if should_exclude(item, root, excludes):
            continue
        if not (backup_path / item.name).exists():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            removed.append(item.name)

    for item in backup_path.iterdir():
        target = root / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
            restored.extend(
                path.relative_to(root).as_posix() for path in target.rglob("*") if path.is_file()
            )
        else:
            shutil.copy2(item, target)
            restored.append(item.name)

    return sorted(restored), sorted(removed)
