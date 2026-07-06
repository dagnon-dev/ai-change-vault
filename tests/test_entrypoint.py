import runpy
import subprocess
import sys
from pathlib import Path

from aicv.entrypoint import main


def test_entrypoint_version(capsys) -> None:  # type: ignore[no-untyped-def]
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert "AI Change Vault" in captured.out
    assert "0.2.0" in captured.out


def test_entrypoint_help(capsys) -> None:  # type: ignore[no-untyped-def]
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert "AI Change Vault" in captured.out
    assert "embeddings rebuild" in captured.out


def test_main_module_direct_execution() -> None:
    result = subprocess.run(
        [sys.executable, "aicv/__main__.py", "--version"],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "AI Change Vault" in result.stdout
    assert "0.2.0" in result.stdout


def test_main_module_in_process(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(sys, "argv", ["aicv/__main__.py", "--version"])

    try:
        runpy.run_path(
            Path(__file__).resolve().parent.parent / "aicv" / "__main__.py",
            run_name="__main__",
        )
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert "AI Change Vault" in captured.out
