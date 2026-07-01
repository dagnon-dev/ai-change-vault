from __future__ import annotations

import sys
from textwrap import dedent

from . import __version__
from .console import render_key_value_table


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)

    if not args or args[0] in {"-h", "--help", "help"}:
        _print_help()
        raise SystemExit(0)

    if args[0] in {"-V", "--version"}:
        print(
            render_key_value_table(
                "AI Change Vault",
                [
                    ("version", __version__),
                    ("command", "aicv"),
                    ("mode", "local-first"),
                ],
            )
        )
        raise SystemExit(0)

    try:
        from .cli import app
    except ModuleNotFoundError as exc:
        _print_missing_dependency_error(exc)
        raise SystemExit(1) from exc

    app()


def _print_help() -> None:
    print(
        dedent(
            f"""
            AI Change Vault ({__version__})

            Usage:
              aicv --version
              aicv --help
              aicv backup --message "before change"
              aicv index --turn 1 --request "..." --files "path/to/file"
              aicv search "keyword"
              aicv revert --turn turn-1
              aicv config
              aicv embeddings status
              aicv embeddings rebuild

            Commands:
              backup       Create a local snapshot
              index        Store a turn document and update search indexes
              search       Search indexed turns
              revert       Restore a turn or file
              list         List stored turns and backups
              config       Print the resolved configuration
              embeddings   Inspect or rebuild semantic vectors

            For the full CLI help, install the runtime dependencies and run:
              pip install -e .
              aicv --help
            """
        ).strip()
    )


def _print_missing_dependency_error(exc: ModuleNotFoundError) -> None:
    missing = exc.name or "a required dependency"
    print(
        "AI Change Vault is installed, but runtime dependencies are missing.\n"
        f"Missing module: {missing}\n\n"
        "Install the package dependencies inside your virtualenv:\n"
        '  python -m pip install typer pydantic pydantic-settings PyYAML\n'
        "or reinstall the project with editable mode:\n"
        '  python -m pip install -e .\n',
        file=sys.stderr,
    )
