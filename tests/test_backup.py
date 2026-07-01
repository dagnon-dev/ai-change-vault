from pathlib import Path

from aicv.backup import create_backup
from aicv.config import AICVConfig


def test_backup_creates_snapshot_and_excludes_defaults(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("x", encoding="utf-8")

    result = create_backup("before navbar", root=tmp_path, config=AICVConfig())

    assert result.backup_id.startswith("turn-001-")
    assert (result.path / "src" / "app.py").exists()
    assert not (result.path / ".git").exists()
    assert not (result.path / "node_modules").exists()
    assert result.files_copied == 1

