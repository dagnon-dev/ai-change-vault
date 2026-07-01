from __future__ import annotations

from pathlib import Path

from .config import AICVConfig, find_project_root, load_config
from .embeddings import (
    EmbeddingRecord,
    cosine_similarity,
    create_embedding_provider,
    load_embedding_records,
)
from .index import load_turns
from .models import SearchResult, TurnDocument
from .utils import tokenize, turn_matches


def search_turns(
    query: str | None = None,
    *,
    turn: str | None = None,
    file: str | None = None,
    root: Path | None = None,
    config: AICVConfig | None = None,
) -> list[SearchResult]:
    project_root = find_project_root(root)
    active_config = config or load_config(project_root)
    documents = load_turns(project_root, active_config)
    query_terms = tokenize(query or "")
    query_vector, embedding_records = _load_embedding_context(
        project_root, active_config, query
    )
    results: list[SearchResult] = []

    for document in documents:
        if turn and not turn_matches(document.turn_id, turn):
            continue
        if file and not _matches_file(document, file):
            continue

        score, matched = _score(document, query_terms)
        semantic_score = _semantic_score(document.turn_id, query_vector, embedding_records)
        score = _combine_scores(score, semantic_score, active_config)
        if query_terms and score == 0:
            continue
        if not query_terms and not turn and not file:
            continue
        if semantic_score and not matched:
            matched = ["semantic"]
        results.append(SearchResult(turn=document, score=score or 1, matched_terms=matched))

    return sorted(results, key=lambda result: (-result.score, result.turn.timestamp))


def _matches_file(document: TurnDocument, file_query: str) -> bool:
    needle = file_query.lower()
    return any(
        needle in changed.lower() or needle in Path(changed).name.lower()
        for changed in document.files_changed
    )


def _score(document: TurnDocument, query_terms: list[str]) -> tuple[int, list[str]]:
    if not query_terms:
        return 0, []

    weighted_fields = [
        (document.request, 4),
        (document.description, 2),
        (document.files_changed, 4),
        (document.validation, 1),
        (document.status, 1),
    ]
    score = 0
    matched: set[str] = set()
    for field, weight in weighted_fields:
        field_tokens = set(tokenize(field))
        for term in query_terms:
            if term in field_tokens or any(term in token for token in field_tokens):
                score += weight
                matched.add(term)
    return score, sorted(matched)


def _load_embedding_context(
    root: Path,
    config: AICVConfig,
    query: str | None,
) -> tuple[list[float] | None, list[EmbeddingRecord]]:
    if not query:
        return None, {}

    try:
        provider = create_embedding_provider(config)
        if provider is None:
            return None, {}
        records = load_embedding_records(root, config, provider.provider_name, provider.model_name)
        if not records:
            return None, {}
        query_vector = provider.embed([query])[0]
        return query_vector, records
    except Exception:
        return None, {}


def _semantic_score(
    turn_id: str,
    query_vector: list[float] | None,
    embedding_records: list[EmbeddingRecord],
) -> int:
    if query_vector is None:
        return 0
    vectors = [
        record.vector for record in embedding_records if record.turn_id == turn_id
    ]
    if not vectors:
        return 0
    similarity = max(cosine_similarity(query_vector, vector) for vector in vectors)
    if similarity <= 0:
        return 0
    return round(similarity * 100)


def _combine_scores(keyword_score: int, semantic_score: int, config: AICVConfig) -> int:
    if semantic_score == 0:
        return min(100, keyword_score * 10 or keyword_score)

    keyword_component = min(100, keyword_score * 10)
    weight_total = config.keyword_weight + config.embedding_weight
    if weight_total <= 0:
        return max(1, keyword_component)
    keyword_weight = config.keyword_weight / weight_total
    embedding_weight = config.embedding_weight / weight_total
    total = (keyword_component * keyword_weight) + (semantic_score * embedding_weight)
    return max(1, round(total))
