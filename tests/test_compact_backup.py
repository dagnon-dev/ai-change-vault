import json
import shutil
from pathlib import Path

from aicv.backup import (
    build_compact_backup,
    create_backup,
    list_backups,
    prune_backups,
)
from aicv.config import AICVConfig
from aicv.index import index_turn
from aicv.revert import revert_turn


def test_compact_backup_keeps_only_changed_files_and_reverts(tmp_path: Path) -> None:
    config = AICVConfig(backup_retention=10)
    src = tmp_path / "src"
    src.mkdir()
    (src / "edit.txt").write_text("before edit\n", encoding="utf-8")
    (src / "delete.txt").write_text("remove me\n", encoding="utf-8")
    (src / "rename_old.txt").write_text("rename me\n", encoding="utf-8")
    (src / "keep.txt").write_text("keep me\n", encoding="utf-8")

    before = create_backup("before change", root=tmp_path, config=config)

    (src / "edit.txt").write_text("after edit\n", encoding="utf-8")
    (src / "delete.txt").unlink()
    (src / "new.txt").write_text("new file\n", encoding="utf-8")
    (src / "rename_old.txt").rename(src / "rename_new.txt")

    after = create_backup("after change", root=tmp_path, config=config)

    compact_path = build_compact_backup(
        tmp_path,
        config,
        "turn-1",
        backup_before=before.path.as_posix(),
        backup_after=after.path.as_posix(),
    )
    assert compact_path is not None

    shutil.rmtree(before.path)
    shutil.rmtree(after.path)

    manifest = json.loads((compact_path / "manifest.json").read_text(encoding="utf-8"))
    statuses = {entry["status"] for entry in manifest["entries"]}

    document = index_turn(
        "1",
        request="Compact backup flow",
        files=[
            "src/edit.txt",
            "src/delete.txt",
            "src/new.txt",
            "src/rename_old.txt",
            "src/rename_new.txt",
        ],
        validation="ok",
        backup_before=compact_path.as_posix(),
        root=tmp_path,
        config=config,
    )

    assert document.backup_before == compact_path.as_posix()
    assert document.backup_after is None
    assert compact_path.exists()
    assert not before.path.exists()
    assert not after.path.exists()
    assert statuses == {"added", "deleted", "modified", "renamed"}

    (src / "edit.txt").write_text("corrupted\n", encoding="utf-8")
    (src / "keep.txt").write_text("keep me changed\n", encoding="utf-8")

    result = revert_turn("turn-1", root=tmp_path, config=config)

    assert (src / "edit.txt").read_text(encoding="utf-8") == "before edit\n"
    assert (src / "delete.txt").read_text(encoding="utf-8") == "remove me\n"
    assert (src / "rename_old.txt").read_text(encoding="utf-8") == "rename me\n"
    assert not (src / "new.txt").exists()
    assert not (src / "rename_new.txt").exists()
    assert (src / "keep.txt").read_text(encoding="utf-8") == "keep me changed\n"
    assert "src/new.txt" in result.removed_paths
    assert "src/rename_new.txt" in result.removed_paths


def test_backup_retention_limits_stored_backups(tmp_path: Path) -> None:
    config = AICVConfig(backup_retention=2)
    (tmp_path / "file.txt").write_text("content\n", encoding="utf-8")

    first = create_backup("first", root=tmp_path, config=config)
    second = create_backup("second", root=tmp_path, config=config)
    third = create_backup("third", root=tmp_path, config=config)

    prune_backups(tmp_path, config)

    backups = list_backups(tmp_path, config)

    assert len(backups) == 2
    assert all(backup.exists() for backup in backups)
    assert not first.path.exists()
    assert second.path.exists()
    assert third.path.exists()
