from __future__ import annotations

import shutil
from pathlib import Path

from .backup import infer_backup_for_turn
from .config import AICVConfig, find_project_root, load_config
from .index import load_turns
from .models import CompactBackupEntry, CompactBackupManifest, RevertResult, TurnDocument
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
        restored = [_restore_file(project_root, backup_path, file, state)]
        removed: list[str] = []
    else:
        restored, removed = _restore_project(
            project_root, backup_path, active_config.excludes, state
        )

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


def _restore_file(root: Path, backup_path: Path, file: str, state: str) -> str:
    manifest = _load_compact_manifest(backup_path)
    if manifest is None:
        relative = safe_relative_path(file)
        source = backup_path / relative
        target = root / relative
        if not source.exists() or not source.is_file():
            msg = f"file not found in backup: {file}"
            raise FileNotFoundError(msg)
        ensure_directory(target.parent)
        shutil.copy2(source, target)
        return relative.as_posix()

    entry = _match_manifest_entry(manifest, file)
    if entry is None:
        msg = f"file not found in backup: {file}"
        raise FileNotFoundError(msg)

    if entry.status == "deleted":
        if state != "before":
            msg = f"file not available in after-state backup: {file}"
            raise FileNotFoundError(msg)
        source_path = backup_path / "before" / entry.before_path
        target_path = root / entry.before_path
        ensure_directory(target_path.parent)
        shutil.copy2(source_path, target_path)
        return entry.before_path
    if entry.status == "added":
        if state != "after":
            msg = f"file not available in before-state backup: {file}"
            raise FileNotFoundError(msg)
        source_path = backup_path / "after" / entry.after_path
        target_path = root / entry.after_path
        ensure_directory(target_path.parent)
        shutil.copy2(source_path, target_path)
        return entry.after_path
    if entry.status == "renamed":
        if state == "before" or file == entry.before_path:
            source_path = backup_path / "before" / entry.before_path
            target_path = root / entry.before_path
            ensure_directory(target_path.parent)
            shutil.copy2(source_path, target_path)
            return entry.before_path
        source_path = backup_path / "after" / entry.after_path
        target_path = root / entry.after_path
        ensure_directory(target_path.parent)
        shutil.copy2(source_path, target_path)
        return entry.after_path

    side = "before" if state == "before" else "after"
    source_relative = entry.before_path if state == "before" else entry.after_path
    source_path = _compact_source_path(backup_path, side, source_relative or entry.path)
    target_path = root / (source_relative or entry.path)
    ensure_directory(target_path.parent)
    shutil.copy2(source_path, target_path)
    return target_path.relative_to(root).as_posix()


def _restore_project(
    root: Path, backup_path: Path, excludes: list[str], state: str
) -> tuple[list[str], list[str]]:
    manifest = _load_compact_manifest(backup_path)
    if manifest is not None:
        return _restore_compact_project(root, backup_path, manifest, state)

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


def _load_compact_manifest(backup_path: Path) -> CompactBackupManifest | None:
    manifest_path = backup_path / "manifest.json"
    if not manifest_path.exists():
        return None
    return CompactBackupManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def _match_manifest_entry(
    manifest: CompactBackupManifest, file: str
) -> CompactBackupEntry | None:
    relative = safe_relative_path(file).as_posix()
    for entry in manifest.entries:
        if entry.status in {"modified", "deleted"} and entry.before_path == relative:
            return entry
        if entry.status == "added" and entry.after_path == relative:
            return entry
        if entry.status == "renamed" and (
            entry.before_path == relative or entry.after_path == relative
        ):
            return entry
    return None


def _compact_source_path(backup_path: Path, side: str, relative: str) -> Path:
    source = backup_path / side / safe_relative_path(relative)
    if not source.exists() or not source.is_file():
        msg = f"file not found in backup: {relative}"
        raise FileNotFoundError(msg)
    return source


def _restore_compact_project(
    root: Path,
    backup_path: Path,
    manifest: CompactBackupManifest,
    state: str,
) -> tuple[list[str], list[str]]:
    restored: list[str] = []
    removed: list[str] = []

    for entry in manifest.entries:
        if state == "before":
            if entry.status == "added":
                _remove_target(root, entry.after_path, removed)
                continue
            if entry.status == "deleted":
                restored.append(
                    _copy_compact_side(root, backup_path, "before", entry.before_path)
                )
                continue
            if entry.status == "renamed":
                _remove_target(root, entry.after_path, removed)
                restored.append(
                    _copy_compact_side(root, backup_path, "before", entry.before_path)
                )
                continue
            restored.append(_copy_compact_side(root, backup_path, "before", entry.before_path))
            continue

        if entry.status == "deleted":
            _remove_target(root, entry.before_path, removed)
            continue
        if entry.status == "added":
            restored.append(_copy_compact_side(root, backup_path, "after", entry.after_path))
            continue
        if entry.status == "renamed":
            _remove_target(root, entry.before_path, removed)
            restored.append(_copy_compact_side(root, backup_path, "after", entry.after_path))
            continue
        restored.append(_copy_compact_side(root, backup_path, "after", entry.after_path))

    return sorted(restored), sorted(removed)


def _copy_compact_side(root: Path, backup_path: Path, side: str, relative: str) -> str:
    source = _compact_source_path(backup_path, side, relative)
    target = root / safe_relative_path(relative)
    ensure_directory(target.parent)
    shutil.copy2(source, target)
    return target.relative_to(root).as_posix()


def _remove_target(root: Path, relative: str | None, removed: list[str]) -> None:
    if not relative:
        return
    target = root / safe_relative_path(relative)
    if not target.exists():
        return
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    removed.append(target.relative_to(root).as_posix())
