from pathlib import Path

from aicv.config import find_project_root, load_config


def test_load_config_merges_yaml_and_env(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / ".aicv.config.yaml").write_text(
        "backup_dir: vault/backups\n"
        "rag_dir: vault/rag\n"
        "auto_index: true\n"
        "excludes:\n"
        "  - .git/\n"
        "  - tmp/\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AICV_RAG_DIR", "env/rag")
    monkeypatch.setenv("AICV_EXCLUDES", ".git/,cache/")
    monkeypatch.setenv("AICV_EMBEDDING_PROVIDER", "none")
    monkeypatch.setenv("AICV_EMBEDDING_WEIGHT", "0.7")

    config = load_config(tmp_path)

    assert config.backup_dir == "vault/backups"
    assert config.rag_dir == "env/rag"
    assert config.auto_index is True
    assert config.excludes == [".git/", "cache/"]
    assert config.embedding_provider == "none"
    assert config.embedding_weight == 0.7
    assert config.backup_path(tmp_path) == tmp_path / "vault" / "backups"
    assert config.rag_path(tmp_path) == tmp_path / "env" / "rag"


def test_find_project_root_uses_nearest_aicv_yaml(tmp_path: Path) -> None:
    nested = tmp_path / "app" / "src"
    nested.mkdir(parents=True)
    (tmp_path / "app" / ".aicv.config.yaml").write_text(
        "backup_dir: .aicv/backups\n", encoding="utf-8"
    )

    assert find_project_root(nested) == tmp_path / "app"
