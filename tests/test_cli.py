from pathlib import Path

from typer.testing import CliRunner

from aicv.cli import app

runner = CliRunner()


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "AI Change Vault" in result.output
    assert "version" in result.output
    assert "0.2.0" in result.output


def test_cli_embeddings_status() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["embeddings", "status"])

        assert result.exit_code == 0
        assert "Embedding Status" in result.output
        assert "embedding_provider" in result.output
        assert "status: disabled" in result.output


def test_cli_embeddings_status_reports_unavailable_provider(monkeypatch) -> None:
    with runner.isolated_filesystem():
        Path(".aicv.config.yaml").write_text(
            "embedding_provider: sentence-transformers\n",
            encoding="utf-8",
        )

        def fail_create_provider(_config):  # type: ignore[no-untyped-def]
            raise RuntimeError("model download failed")

        monkeypatch.setattr(
            "aicv.cli.create_embedding_provider",
            fail_create_provider,
        )

        result = runner.invoke(app, ["embeddings", "status"])

        assert result.exit_code == 0
        assert "status: unavailable (model download failed)" in result.output


def test_cli_embeddings_rebuild_reports_unavailable_provider(monkeypatch) -> None:
    with runner.isolated_filesystem():
        Path(".aicv.config.yaml").write_text(
            "embedding_provider: sentence-transformers\n",
            encoding="utf-8",
        )

        def fail_create_provider(_config):  # type: ignore[no-untyped-def]
            raise RuntimeError("model download failed")

        monkeypatch.setattr(
            "aicv.cli.create_embedding_provider",
            fail_create_provider,
        )

        result = runner.invoke(app, ["embeddings", "rebuild"])

        assert result.exit_code == 0
        assert "embeddings: unavailable (model download failed)" in result.output


def test_cli_init_and_doctor() -> None:
    with runner.isolated_filesystem():
        init_result = runner.invoke(app, ["init"])
        assert init_result.exit_code == 0

        root = Path.cwd()
        assert (root / ".aicv.config.yaml").exists()
        assert (root / "AI_SESSION_LOG.md").exists()
        assert (root / "scripts" / "AI_INSTRUCTIONS.md").exists()

        doctor_result = runner.invoke(app, ["doctor"])
        assert doctor_result.exit_code == 0
        assert "status: ready" in doctor_result.output


def test_cli_backup_index_search_and_revert_file() -> None:
    with runner.isolated_filesystem():
        root = Path.cwd()
        target = root / "foo.txt"
        target.write_text("before", encoding="utf-8")

        backup_result = runner.invoke(app, ["backup", "--message", "before change"])
        assert backup_result.exit_code == 0
        backup_dir = next((root / ".aicv" / "backups").iterdir())

        index_result = runner.invoke(
            app,
            [
                "index",
                "--turn",
                "1",
                "--request",
                "test navbar",
                "--files",
                "foo.txt",
                "--validation",
                "ok",
                "--backup-before",
                backup_dir.as_posix(),
            ],
        )
        assert index_result.exit_code == 0

        search_result = runner.invoke(app, ["search", "navbar"])
        assert search_result.exit_code == 0
        assert "turn-1" in search_result.output
        assert "Search Results" in search_result.output
        assert "Revert" in search_result.output

        list_result = runner.invoke(app, ["list"])
        assert list_result.exit_code == 0
        assert "Indexed Turns" in list_result.output
        assert "Backups" in list_result.output
        assert "turn-1" in list_result.output
        assert backup_dir.name in list_result.output

        json_list_result = runner.invoke(app, ["list", "--json"])
        assert json_list_result.exit_code == 0
        assert '"turn_id": "turn-1"' in json_list_result.output
        assert '"backup_id":' in json_list_result.output

        target.write_text("after", encoding="utf-8")
        revert_result = runner.invoke(
            app, ["revert", "--turn", "turn-1", "--file", "foo.txt", "--yes"]
        )

        assert revert_result.exit_code == 0
        assert target.read_text(encoding="utf-8") == "before"
