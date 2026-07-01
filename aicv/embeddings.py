from __future__ import annotations

import difflib
import hashlib
import json
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib import error, request

from .config import AICVConfig, resolve_project_path
from .models import EmbeddingRecord, EmbeddingStore, TurnDocument
from .utils import ensure_directory, safe_relative_path, slugify, utc_now


@runtime_checkable
class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(slots=True)
class EmbeddingPayload:
    kind: str
    chunk_id: str | None
    source_path: str | None
    title: str | None
    text: str
    line_start: int | None = None
    line_end: int | None = None


def build_embedding_text(document: TurnDocument) -> str:
    lines = [
        f"Turn: {document.turn_id}",
        f"Request: {document.request}",
    ]
    if document.description:
        lines.append(f"Description: {document.description}")
    if document.files_changed:
        lines.append("Files changed:")
        lines.extend(f"- {path}" for path in document.files_changed)
    if document.validation:
        lines.append(f"Validation: {document.validation}")
    lines.append(f"Status: {document.status}")
    return "\n".join(lines)


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def embedding_store_path(root: Path, config: AICVConfig) -> Path:
    return resolve_project_path(root, config.embedding_store)


def load_embedding_store(root: Path, config: AICVConfig) -> EmbeddingStore:
    path = embedding_store_path(root, config)
    if not path.exists():
        return EmbeddingStore()
    return EmbeddingStore.model_validate_json(path.read_text(encoding="utf-8"))


def save_embedding_store(root: Path, config: AICVConfig, store: EmbeddingStore) -> Path:
    path = embedding_store_path(root, config)
    ensure_directory(path.parent)
    path.write_text(store.model_dump_json(indent=2), encoding="utf-8")
    return path


def build_turn_embedding_payloads(root: Path, document: TurnDocument) -> list[EmbeddingPayload]:
    payloads = [
        EmbeddingPayload(
            kind="turn",
            chunk_id=None,
            source_path=None,
            title=f"Turn summary: {document.turn_id}",
            text=build_embedding_text(document),
        )
    ]

    payloads.extend(_build_file_payloads(root, document))
    return payloads


def upsert_turn_embeddings(
    root: Path,
    config: AICVConfig,
    document: TurnDocument,
    *,
    provider: EmbeddingProvider | None = None,
) -> list[EmbeddingRecord] | None:
    active_provider = provider or create_embedding_provider(config)
    if active_provider is None:
        return None

    payloads = build_turn_embedding_payloads(root, document)
    if not payloads:
        return []

    vectors = _embed_payloads(active_provider, payloads, config.embedding_batch_size)
    records = [
        EmbeddingRecord(
            turn_id=document.turn_id,
            kind=payload.kind,  # type: ignore[arg-type]
            chunk_id=payload.chunk_id,
            provider=active_provider.provider_name,
            model=active_provider.model_name,
            source_path=payload.source_path,
            title=payload.title,
            line_start=payload.line_start,
            line_end=payload.line_end,
            text=payload.text,
            vector=vector,
            text_hash=text_hash(payload.text),
            updated_at=utc_now(),
        )
        for payload, vector in zip(payloads, vectors, strict=True)
    ]

    store = load_embedding_store(root, config)
    store.records = [existing for existing in store.records if existing.turn_id != document.turn_id]
    store.records.extend(records)
    save_embedding_store(root, config, store)
    return records


def upsert_turn_embedding(
    root: Path,
    config: AICVConfig,
    document: TurnDocument,
    *,
    provider: EmbeddingProvider | None = None,
) -> EmbeddingRecord | None:
    records = upsert_turn_embeddings(root, config, document, provider=provider)
    if not records:
        return None
    for record in records:
        if record.kind == "turn":
            return record
    return records[0]


def load_embedding_records(
    root: Path,
    config: AICVConfig,
    provider_name: str,
    model_name: str,
) -> list[EmbeddingRecord]:
    store = load_embedding_store(root, config)
    return [
        record
        for record in store.records
        if record.provider == provider_name and record.model == model_name
    ]


def compatible_vectors(
    root: Path,
    config: AICVConfig,
    provider_name: str,
    model_name: str,
) -> dict[str, list[float]]:
    vectors: dict[str, list[float]] = {}
    for record in load_embedding_records(root, config, provider_name, model_name):
        if record.kind == "turn":
            vectors[record.turn_id] = record.vector
    return vectors


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def create_embedding_provider(config: AICVConfig) -> EmbeddingProvider | None:
    if config.embedding_provider == "none":
        return None
    if config.embedding_provider == "sentence-transformers":
        return SentenceTransformersEmbeddingProvider(config.embedding_model)
    if config.embedding_provider == "openai":
        return OpenAIEmbeddingProvider(
            model_name=config.embedding_model,
            api_key=config.embedding_api_key or os.getenv("OPENAI_API_KEY"),
        )
    if config.embedding_provider == "ollama":
        return OllamaEmbeddingProvider(
            model_name=config.embedding_model,
            base_url=config.embedding_base_url,
            endpoint=config.embedding_endpoint,
        )
    msg = f"unsupported embedding provider: {config.embedding_provider}"
    raise ValueError(msg)


class SentenceTransformersEmbeddingProvider:
    provider_name = "sentence-transformers"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - optional dependency
            msg = (
                "sentence-transformers is not installed. "
                "Install with `pip install -e \".[embeddings-local]\"`."
            )
            raise RuntimeError(msg) from exc
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        encoded = self._model.encode(list(texts), normalize_embeddings=True)
        return [list(map(float, row)) for row in encoded]


class OpenAIEmbeddingProvider:
    provider_name = "openai"

    def __init__(self, model_name: str, api_key: str | None) -> None:
        self.model_name = model_name
        if not api_key:
            msg = "OPENAI_API_KEY or AICV_EMBEDDING_API_KEY is required for openai embeddings"
            raise RuntimeError(msg)
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            msg = "openai is not installed. Install with `pip install -e \".[embeddings-openai]\"`."
            raise RuntimeError(msg) from exc
        self._client = OpenAI(api_key=api_key)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self.model_name, input=list(texts))
        return [list(map(float, item.embedding)) for item in response.data]


class OllamaEmbeddingProvider:
    provider_name = "ollama"

    def __init__(self, model_name: str, base_url: str, endpoint: str) -> None:
        self.model_name = model_name
        self._url = base_url.rstrip("/") + "/" + endpoint.lstrip("/")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        payload = json.dumps({"model": self.model_name, "input": list(texts)}).encode("utf-8")
        req = request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:  # pragma: no cover - network dependent
            msg = f"failed to fetch embeddings from {self._url}"
            raise RuntimeError(msg) from exc

        embeddings = data.get("embeddings") or data.get("embedding")
        if embeddings is None:
            msg = f"embedding response did not include vectors: {data}"
            raise RuntimeError(msg)
        if embeddings and isinstance(embeddings[0], (int, float)):
            return [list(map(float, embeddings))]
        return [list(map(float, row)) for row in embeddings]


def _build_file_payloads(root: Path, document: TurnDocument) -> list[EmbeddingPayload]:
    payloads: list[EmbeddingPayload] = []
    if not document.files_changed:
        return payloads

    snapshot_root = _resolve_snapshot_root(root, document.backup_before)
    for index, file_path in enumerate(document.files_changed, start=1):
        current_text = _read_optional_text(root / safe_relative_path(file_path))
        before_text = (
            _read_optional_text(snapshot_root / safe_relative_path(file_path))
            if snapshot_root is not None
            else None
        )

        if before_text is None and current_text is None:
            continue

        diff_text = _render_unified_diff(file_path, before_text, current_text)
        if diff_text:
            payloads.append(
                EmbeddingPayload(
                    kind="diff",
                    chunk_id=f"{slugify(file_path)}-diff-{index}",
                    source_path=file_path,
                    title=f"Diff for {file_path}",
                    text=diff_text,
                )
            )

        payloads.extend(
            _render_snippet_payloads(
                file_path=file_path,
                before_text=before_text,
                after_text=current_text,
                chunk_prefix=f"{slugify(file_path)}-snippet-{index}",
            )
        )

        if not diff_text and current_text is not None:
            payloads.append(
                EmbeddingPayload(
                    kind="snippet",
                    chunk_id=f"{slugify(file_path)}-fallback-{index}",
                    source_path=file_path,
                    title=f"Current content for {file_path}",
                    text=_clip_text(current_text, limit=2400),
                )
            )

    return payloads


def _render_unified_diff(
    file_path: str,
    before_text: str | None,
    after_text: str | None,
) -> str:
    before_lines = [] if before_text is None else before_text.splitlines()
    after_lines = [] if after_text is None else after_text.splitlines()
    diff = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
    )
    if not diff:
        return ""
    return _clip_text("\n".join(diff), limit=4000)


def _render_snippet_payloads(
    *,
    file_path: str,
    before_text: str | None,
    after_text: str | None,
    chunk_prefix: str,
) -> list[EmbeddingPayload]:
    if before_text is None and after_text is None:
        return []

    before_lines = [] if before_text is None else before_text.splitlines()
    after_lines = [] if after_text is None else after_text.splitlines()

    if before_lines == after_lines:
        return []

    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines)
    payloads: list[EmbeddingPayload] = []
    chunk_index = 0
    for opcode, before_start, before_end, after_start, after_end in matcher.get_opcodes():
        if opcode == "equal":
            continue
        chunk_index += 1
        before_snippet = _with_context(before_lines, before_start, before_end)
        after_snippet = _with_context(after_lines, after_start, after_end)
        text = _format_snippet_chunk(
            file_path=file_path,
            opcode=opcode,
            before_start=before_start,
            before_end=before_end,
            after_start=after_start,
            after_end=after_end,
            before_snippet=before_snippet,
            after_snippet=after_snippet,
        )
        payloads.append(
            EmbeddingPayload(
                kind="snippet",
                chunk_id=f"{chunk_prefix}-{chunk_index}",
                source_path=file_path,
                title=f"{file_path} {opcode} {chunk_index}",
                text=text,
                line_start=after_start + 1 if after_lines else before_start + 1,
                line_end=after_end if after_lines else before_end,
            )
        )
    return payloads


def _format_snippet_chunk(
    *,
    file_path: str,
    opcode: str,
    before_start: int,
    before_end: int,
    after_start: int,
    after_end: int,
    before_snippet: list[str],
    after_snippet: list[str],
) -> str:
    sections = [
        f"File: {file_path}",
        f"Change: {opcode}",
        f"Before range: {before_start + 1}-{max(before_end, before_start + 1)}",
        f"After range: {after_start + 1}-{max(after_end, after_start + 1)}",
    ]
    if before_snippet:
        sections.append("Before snippet:")
        sections.extend(before_snippet)
    if after_snippet:
        sections.append("After snippet:")
        sections.extend(after_snippet)
    return _clip_text("\n".join(sections), limit=2600)


def _with_context(lines: list[str], start: int, end: int, context: int = 4) -> list[str]:
    if not lines:
        return []
    lower = max(0, start - context)
    upper = min(len(lines), end + context)
    return [
        f"{index + 1:04d}: {line}"
        for index, line in enumerate(lines[lower:upper], start=lower)
    ]


def _resolve_snapshot_root(root: Path, backup_before: str | None) -> Path | None:
    if not backup_before:
        return None
    candidate = Path(backup_before).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate if candidate.exists() else None


def _read_optional_text(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="ignore")


def _clip_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 20] + "\n... [truncated]"


def _embed_payloads(
    provider: EmbeddingProvider,
    payloads: list[EmbeddingPayload],
    batch_size: int,
) -> list[list[float]]:
    if not payloads:
        return []
    size = max(1, batch_size)
    vectors: list[list[float]] = []
    for start in range(0, len(payloads), size):
        batch = payloads[start : start + size]
        batch_vectors = provider.embed([payload.text for payload in batch])
        if len(batch_vectors) != len(batch):
            msg = "embedding provider returned an unexpected number of vectors"
            raise RuntimeError(msg)
        vectors.extend(batch_vectors)
    return vectors
