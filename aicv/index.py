from __future__ import annotations

import json
from pathlib import Path

from .backup import infer_backup_for_turn
from .config import AICVConfig, find_project_root, load_config
from .embeddings import create_embedding_provider, upsert_turn_embeddings
from .models import TurnDocument
from .session_log import append_session_log
from .utils import ensure_directory, split_values, tokenize


def index_turn(
    turn: str,
    *,
    request: str,
    files: list[str] | None = None,
    validation: str | None = None,
    description: str | None = None,
    backup_before: str | None = None,
    backup_after: str | None = None,
    status: str = "indexed",
    root: Path | None = None,
    config: AICVConfig | None = None,
) -> TurnDocument:
    project_root = find_project_root(root)
    active_config = config or load_config(project_root)
    files_changed = split_values(files)

    document = TurnDocument(
        turn_id=turn,
        request=request,
        description=description,
        files_changed=files_changed,
        backup_before=backup_before,
        backup_after=backup_after,
        validation=validation,
        status=status,
    )

    if document.backup_before is None:
        inferred = infer_backup_for_turn(project_root, active_config, document.turn_id)
        if inferred is not None:
            document.backup_before = inferred.as_posix()

    turns_dir = active_config.rag_path(project_root) / "turns"
    ensure_directory(turns_dir)
    turn_path = turns_dir / f"{document.turn_id}.json"
    turn_path.write_text(document.model_dump_json(indent=2), encoding="utf-8")

    rebuild_index(project_root, active_config)
    embedding_note = _refresh_embedding(project_root, active_config, document)
    append_session_log(
        project_root,
        active_config,
        f"index {document.turn_id}",
        [
            f"request: {request}",
            f"files: {', '.join(files_changed) if files_changed else 'none'}",
            f"validation: {validation or 'not provided'}",
            f"status: {status}",
            embedding_note,
        ],
    )
    return document


def rebuild_index(root: Path, config: AICVConfig) -> dict[str, list[str]]:
    inverted: dict[str, set[str]] = {}
    for document in load_turns(root, config):
        fields = [
            document.request,
            document.description,
            document.files_changed,
            document.validation,
            document.status,
        ]
        for token in tokenize(*fields):
            inverted.setdefault(token, set()).add(document.turn_id)

    serializable = {term: sorted(turns) for term, turns in sorted(inverted.items())}
    rag_root = config.rag_path(root)
    ensure_directory(rag_root)
    (rag_root / "index.json").write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    return serializable


def load_turns(root: Path, config: AICVConfig) -> list[TurnDocument]:
    turns_dir = config.rag_path(root) / "turns"
    if not turns_dir.exists():
        return []
    documents: list[TurnDocument] = []
    for path in sorted(turns_dir.glob("*.json")):
        documents.append(TurnDocument.model_validate_json(path.read_text(encoding="utf-8")))
    return documents


def _refresh_embedding(root: Path, config: AICVConfig, document: TurnDocument) -> str:
    try:
        provider = create_embedding_provider(config)
        if provider is None:
            return f"embeddings: disabled ({config.embedding_provider})"
        records = upsert_turn_embeddings(root, config, document, provider=provider)
        if records is None:
            return "embeddings: skipped"
        diff_count = sum(1 for record in records if record.kind == "diff")
        snippet_count = sum(1 for record in records if record.kind == "snippet")
        return (
            f"embeddings: indexed {len(records)} record(s) with "
            f"{provider.provider_name}/{provider.model_name} "
            f"({diff_count} diffs, {snippet_count} snippets)"
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        return f"embeddings: unavailable ({exc})"
