from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from .backup import create_backup, list_backups
from .config import (
    default_project_config,
    find_project_root,
    load_config,
    project_has_config,
    render_project_config,
    resolve_config_path,
)
from .console import Table, render_key_value_table, render_table
from .embeddings import create_embedding_provider, load_embedding_store, upsert_turn_embedding
from .index import index_turn, load_turns
from .revert import revert_turn
from .search import search_turns
from .utils import ensure_directory, split_values

app = typer.Typer(
    name="aicv",
    help="AI Change Vault: local snapshots, turn index and reversions for AI-assisted coding.",
    no_args_is_help=True,
)
embeddings_app = typer.Typer(help="Manage semantic embeddings.")
app.add_typer(embeddings_app, name="embeddings")


def _try_create_embedding_provider(config):
    try:
        return create_embedding_provider(config), None
    except Exception as exc:  # pragma: no cover - defensive fallback
        return None, exc


def version_callback(value: bool) -> None:
    if value:
        typer.echo(
            render_key_value_table(
                "AI Change Vault",
                [
                    ("version", __version__),
                    ("command", "aicv"),
                    ("mode", "local-first"),
                ],
            )
        )
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    _ = version


@app.command()
def backup(
    message_arg: Annotated[str | None, typer.Argument(help="Backup message.")] = None,
    message: Annotated[str | None, typer.Option("--message", "-m", help="Backup message.")] = None,
) -> None:
    """Create a full local project snapshot."""

    final_message = message or message_arg
    if not final_message:
        raise typer.BadParameter("message is required")

    result = create_backup(final_message)
    typer.echo(
        render_key_value_table(
            "Backup Created",
            [
                ("path", result.path),
                ("turn", f"turn-{result.turn_number:03d}"),
                ("files_copied", result.files_copied),
            ],
        )
    )


@app.command("index")
def index_command(
    turn: Annotated[str, typer.Option("--turn", help="Turn id or number.")],
    request: Annotated[str, typer.Option("--request", help="Original user request.")],
    files: Annotated[
        list[str] | None,
        typer.Option("--files", "--file", help="Changed file path. Repeat or comma-separate."),
    ] = None,
    validation: Annotated[
        str | None, typer.Option("--validation", help="Validation result.")
    ] = None,
    description: Annotated[
        str | None, typer.Option("--description", help="Optional description.")
    ] = None,
    backup_before: Annotated[
        str | None, typer.Option("--backup-before", help="Before backup path.")
    ] = None,
    backup_after: Annotated[
        str | None, typer.Option("--backup-after", help="After backup path.")
    ] = None,
    status: Annotated[str, typer.Option("--status", help="Turn status.")] = "indexed",
) -> None:
    """Index a turn document and update the local inverted index."""

    document = index_turn(
        turn,
        request=request,
        files=split_values(files),
        validation=validation,
        description=description,
        backup_before=backup_before,
        backup_after=backup_after,
        status=status,
    )
    typer.echo(render_key_value_table("Turn Indexed", [("turn_id", document.turn_id)]))


@app.command()
def search(
    query: Annotated[str | None, typer.Argument(help="Keyword query.")] = None,
    turn: Annotated[str | None, typer.Option("--turn", help="Filter by turn id.")] = None,
    file: Annotated[str | None, typer.Option("--file", help="Filter by changed file.")] = None,
) -> None:
    """Search indexed turns by text, turn id or file."""

    results = search_turns(query, turn=turn, file=file)
    if not results:
        typer.echo("No matching turns found.")
        return

    rows = []
    for result in results:
        document = result.turn
        rows.append(
            (
                document.turn_id,
                f"{result.score}",
                document.request,
                ", ".join(document.files_changed) if document.files_changed else "—",
                document.validation or "not provided",
                f"aicv revert --turn {document.turn_id}",
            )
        )
    typer.echo(
        render_table(
            Table(
                title="Search Results",
                headers=("Turn", "Score", "Request", "Files", "Validation", "Revert"),
                rows=rows,
            )
        )
    )


@app.command("list")
def list_command(
    kind: Annotated[
        str,
        typer.Option("--kind", help="What to list: all, turns or backups."),
    ] = "all",
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    """List everything stored locally by AI Change Vault."""

    if kind not in {"all", "turns", "backups"}:
        raise typer.BadParameter("kind must be one of: all, turns, backups")

    root = find_project_root()
    resolved = load_config(root)
    turns = load_turns(root, resolved) if kind in {"all", "turns"} else []
    backups = list_backups(root, resolved) if kind in {"all", "backups"} else []

    if json_output:
        payload = {
            "project_root": root.as_posix(),
            "turns": [turn.model_dump(mode="json") for turn in turns],
            "backups": [
                {
                    "backup_id": backup.name,
                    "path": backup.as_posix(),
                    "files": _count_files(backup),
                }
                for backup in backups
            ],
        }
        typer.echo(json.dumps(payload, indent=2))
        return

    if kind in {"all", "turns"}:
        typer.echo("Indexed turns")
        if not turns:
            typer.echo("  none")
        else:
            typer.echo(
                render_table(
                    Table(
                        title="Indexed Turns",
                        headers=("Turn", "Request", "Files", "Validation", "Status", "Revert"),
                        rows=[
                            (
                                turn.turn_id,
                                turn.request,
                                ", ".join(turn.files_changed) if turn.files_changed else "—",
                                turn.validation or "not provided",
                                turn.status,
                                f"aicv revert --turn {turn.turn_id}",
                            )
                            for turn in turns
                        ],
                    )
                )
            )

    if kind in {"all", "backups"}:
        if kind == "all":
            typer.echo("")
        typer.echo("Backups")
        if not backups:
            typer.echo("  none")
        else:
            typer.echo(
                render_table(
                    Table(
                        title="Backups",
                        headers=("Backup", "Path", "Files"),
                        rows=[
                            (backup.name, backup.as_posix(), _count_files(backup))
                            for backup in backups
                        ],
                    )
                )
            )


@app.command()
def revert(
    turn: Annotated[str, typer.Option("--turn", help="Turn id to restore.")],
    file: Annotated[str | None, typer.Option("--file", help="Restore only this file.")] = None,
    state: Annotated[
        str, typer.Option("--state", help="Backup state: before or after.")
    ] = "before",
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Restore the project or a single file from a turn backup."""

    target = file or "the full project"
    if not yes:
        typer.confirm(f"Restore {target} from {turn} ({state})?", abort=True)
    result = revert_turn(turn, file=file, state=state)
    typer.echo(
        render_key_value_table(
            "Restore Complete",
            [
                ("restored_files", len(result.restored_files)),
                ("backup_path", result.backup_path),
            ],
        )
    )
    if result.removed_paths:
        typer.echo(
            render_key_value_table(
                "Removed Paths",
                [("count", len(result.removed_paths)), ("paths", ", ".join(result.removed_paths))],
            )
        )


@app.command()
def config() -> None:
    """Print resolved configuration for the current project."""

    root = find_project_root()
    resolved = load_config(root)
    typer.echo(
        render_key_value_table(
            "Resolved Configuration",
            [
                ("project_root", root),
                ("backup_dir", resolved.backup_path(root)),
                ("backup_retention", resolved.backup_retention),
                ("rag_dir", resolved.rag_path(root)),
                ("session_log", resolved.session_log_path(root)),
                ("embedding_provider", resolved.embedding_provider),
                ("embedding_model", resolved.embedding_model),
                ("auto_index", resolved.auto_index),
                ("embedding_weight", resolved.embedding_weight),
                ("keyword_weight", resolved.keyword_weight),
                ("embedding_store", resolved.embedding_store),
            ],
        )
    )


@app.command()
def init(
    path: Annotated[
        Path | None,
        typer.Argument(
            exists=False,
            file_okay=False,
            dir_okay=True,
            writable=False,
            help="Project root to initialize.",
        ),
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing config.")] = False,
) -> None:
    """Create the project-level AICV config and base directories."""

    project_root = (path or Path.cwd()).resolve()
    ensure_directory(project_root)
    ensure_directory(project_root / ".aicv")
    ensure_directory(project_root / ".aicv" / "backups")
    ensure_directory(project_root / ".aicv" / "rag")

    config_path = project_root / ".aicv.config.yaml"
    legacy_path = project_root / ".aicv.yaml"
    if config_path.exists() and not force:
        raise typer.BadParameter(f"{config_path} already exists. Use --force to overwrite it.")
    if legacy_path.exists() and not config_path.exists() and not force:
        typer.echo(f"Found legacy config at {legacy_path}; writing new config alongside it.")

    config_data = default_project_config(project_root.name)
    config_path.write_text(render_project_config(config_data), encoding="utf-8")

    session_log_path = project_root / "AI_SESSION_LOG.md"
    if not session_log_path.exists():
        session_log_path.write_text("# AI Session Log\n\n", encoding="utf-8")

    instructions_path = project_root / "scripts" / "AI_INSTRUCTIONS.md"
    if not instructions_path.exists():
        ensure_directory(instructions_path.parent)
        instructions_path.write_text(
            _default_ai_instructions(project_root.name, config_path.name), encoding="utf-8"
        )

    typer.echo(
        render_key_value_table(
            "AICV Initialized",
            [
                ("project_root", project_root),
                ("config", config_path),
                ("instructions", instructions_path),
                ("next_step", "aicv doctor"),
            ],
        )
    )


@app.command()
def doctor() -> None:
    """Validate that the current project is ready for AI Change Vault."""

    root = find_project_root()
    config_path = resolve_config_path(root)
    issues: list[str] = []

    if not project_has_config(root):
        issues.append(f"missing config file: {root / '.aicv.config.yaml'}")
    elif config_path.name == ".aicv.yaml":
        issues.append("legacy config detected: .aicv.yaml (migrate to .aicv.config.yaml)")

    resolved = load_config(root)
    backup_dir = resolved.backup_path(root)
    rag_dir = resolved.rag_path(root)
    session_log = resolved.session_log_path(root)
    provider = None

    if resolved.embedding_provider != "none":
        try:
            provider = create_embedding_provider(resolved)
        except Exception as exc:
            issues.append(f"embedding provider unavailable: {exc}")

    summary_rows = [
                ("project_root", root),
                ("config_path", config_path),
                ("backup_dir", backup_dir),
                ("backup_retention", resolved.backup_retention),
                ("rag_dir", rag_dir),
                ("session_log", session_log),
                ("embedding_provider", resolved.embedding_provider),
        ("embedding_model", resolved.embedding_model),
        ("auto_index", resolved.auto_index),
        (
            "embedding_status",
            (
                f"active ({provider.provider_name}/{provider.model_name})"
                if provider is not None
                else "disabled"
                if resolved.embedding_provider == "none"
                else "unavailable"
            ),
        ),
    ]

    if not backup_dir.exists():
        issues.append(f"missing backup directory: {backup_dir}")
    if not rag_dir.exists():
        issues.append(f"missing rag directory: {rag_dir}")
    if not session_log.exists():
        issues.append(f"missing session log: {session_log}")

    if issues:
        typer.echo(render_key_value_table("Doctor", summary_rows))
        typer.echo(
            render_table(
                Table(
                    title="Issues",
                    headers=("#", "Problem"),
                    rows=[(index + 1, issue) for index, issue in enumerate(issues)],
                )
            )
        )
        typer.echo("status: needs attention")
        raise typer.Exit(code=1)

    typer.echo(render_key_value_table("Doctor", summary_rows + [("status", "ready")]))
    typer.echo("status: ready")


@embeddings_app.command("status")
def embeddings_status() -> None:
    """Show embedding provider and stored vector statistics."""

    root = find_project_root()
    resolved = load_config(root)
    provider, provider_error = _try_create_embedding_provider(resolved)
    store = load_embedding_store(root, resolved)

    counts = Counter(record.kind for record in store.records)
    typer.echo(
        render_key_value_table(
            "Embedding Status",
            [
                ("project_root", root),
                ("embedding_provider", resolved.embedding_provider),
                ("embedding_model", resolved.embedding_model),
                ("embedding_store", resolved.embedding_store),
                ("vector_records", len(store.records)),
                ("turn_records", counts.get("turn", 0)),
                ("diff_records", counts.get("diff", 0)),
                ("snippet_records", counts.get("snippet", 0)),
            ],
        )
    )
    if provider_error is not None:
        typer.echo(f"status: unavailable ({provider_error})")
        return
    if provider is None:
        typer.echo("status: disabled")
        return
    typer.echo(f"status: active ({provider.provider_name}/{provider.model_name})")


@embeddings_app.command("rebuild")
def embeddings_rebuild() -> None:
    """Rebuild semantic vectors for every indexed turn."""

    root = find_project_root()
    resolved = load_config(root)
    provider, provider_error = _try_create_embedding_provider(resolved)
    if provider_error is not None:
        typer.echo(f"embeddings: unavailable ({provider_error})")
        return
    if provider is None:
        typer.echo("embeddings: disabled")
        return

    turns = load_turns(root, resolved)
    if not turns:
        typer.echo("No turns found to embed.")
        return

    count = 0
    failed: list[str] = []
    for turn in turns:
        try:
            record = upsert_turn_embedding(root, resolved, turn, provider=provider)
        except Exception as exc:  # pragma: no cover - defensive fallback
            failed.append(f"{turn.turn_id}: {exc}")
            continue
        if record is not None:
            count += 1

    typer.echo(
        f"Rebuilt {count} embedding record(s) using "
        f"{provider.provider_name}/{provider.model_name}"
    )
    if failed:
        typer.echo("Skipped turns with embedding errors:")
        for item in failed:
            typer.echo(f"- {item}")


def _count_files(path: Path) -> int:
    return sum(1 for item in path.rglob("*") if item.is_file())


def _default_ai_instructions(project_name: str, config_filename: str) -> str:
    return (
        f"# AI Instructions for {project_name}\n\n"
        "Read this before editing the project.\n\n"
        "1. Look for AICV config in the project root.\n"
        f"2. Use `{config_filename}` as the project policy source.\n"
        "3. Run a backup before making changes.\n"
        "4. Make the requested change.\n"
        "5. Validate the result.\n"
        "6. Run a second backup and index the turn.\n"
        "7. Use `aicv doctor` if the project is missing required files or directories.\n"
    )
