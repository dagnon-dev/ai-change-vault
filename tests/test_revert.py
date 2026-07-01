from pathlib import Path

from aicv.backup import create_backup
from aicv.config import AICVConfig
from aicv.index import index_turn
from aicv.revert import revert_turn


def test_revert_restores_single_file(tmp_path: Path) -> None:
    config = AICVConfig()
    target = tmp_path / "foo.txt"
    target.write_text("before", encoding="utf-8")
    backup = create_backup("before change", root=tmp_path, config=config)
    index_turn(
        "1",
        request="test",
        files=["foo.txt"],
        validation="ok",
        backup_before=backup.path.as_posix(),
        root=tmp_path,
        config=config,
    )

    target.write_text("after", encoding="utf-8")
    result = revert_turn("turn-1", file="foo.txt", root=tmp_path, config=config)

    assert target.read_text(encoding="utf-8") == "before"
    assert result.restored_files == ["foo.txt"]


def test_revert_restores_project_and_removes_new_files(tmp_path: Path) -> None:
    config = AICVConfig()
    (tmp_path / "foo.txt").write_text("before", encoding="utf-8")
    backup = create_backup("before full revert", root=tmp_path, config=config)
    index_turn(
        "1",
        request="test",
        files=["foo.txt"],
        validation="ok",
        backup_before=backup.path.as_posix(),
        root=tmp_path,
        config=config,
    )

    (tmp_path / "foo.txt").write_text("after", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new", encoding="utf-8")
    result = revert_turn("turn-1", root=tmp_path, config=config)

    assert (tmp_path / "foo.txt").read_text(encoding="utf-8") == "before"
    assert not (tmp_path / "new.txt").exists()
    assert "new.txt" in result.removed_paths

