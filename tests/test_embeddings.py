from pathlib import Path

from aicv.config import AICVConfig
from aicv.embeddings import (
    build_embedding_text,
    compatible_vectors,
    load_embedding_store,
    upsert_turn_embedding,
)
from aicv.index import index_turn
from aicv.models import TurnDocument
from aicv.search import search_turns


class FakeProvider:
    provider_name = "fake"
    model_name = "test-model"

    def embed(self, texts):  # type: ignore[no-untyped-def]
        return [[1.0, 0.0, 0.0] for _ in texts]


def test_build_embedding_text_includes_core_fields() -> None:
    document = TurnDocument(
        turn_id="turn-004",
        request="Fix navbar",
        description="Align header spacing",
        files_changed=["frontend/src/components/Navbar.tsx"],
        validation="lint ok",
    )

    text = build_embedding_text(document)

    assert "Turn: turn-004" in text
    assert "Request: Fix navbar" in text
    assert "Description: Align header spacing" in text
    assert "frontend/src/components/Navbar.tsx" in text
    assert "Validation: lint ok" in text


def test_upsert_turn_embedding_persists_store(tmp_path: Path) -> None:
    config = AICVConfig()
    document = TurnDocument(
        turn_id="turn-001",
        request="Semantic search",
        files_changed=["docs/guide.md"],
    )

    record = upsert_turn_embedding(tmp_path, config, document, provider=FakeProvider())

    assert record is not None
    assert record.turn_id == "turn-001"
    vectors = compatible_vectors(tmp_path, config, "fake", "test-model")
    assert vectors["turn-001"] == [1.0, 0.0, 0.0]


def test_search_uses_semantic_context_when_embeddings_exist(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    config = AICVConfig(embedding_provider="sentence-transformers")

    monkeypatch.setattr("aicv.index.create_embedding_provider", lambda _config: FakeProvider())
    monkeypatch.setattr("aicv.search.create_embedding_provider", lambda _config: FakeProvider())

    index_turn(
        "010",
        request="Create a new dashboard card",
        files=["frontend/src/pages/Dashboard.tsx"],
        validation="ok",
        root=tmp_path,
        config=config,
    )

    results = search_turns("something unrelated", root=tmp_path, config=config)

    assert results[0].turn.turn_id == "turn-010"
    assert results[0].score > 0


def test_index_turn_creates_chunk_embeddings(tmp_path: Path, monkeypatch) -> None:
    config = AICVConfig(embedding_provider="sentence-transformers")
    before_root = tmp_path / ".aicv" / "backups" / "turn-001-before"
    before_root.mkdir(parents=True)
    (before_root / "src").mkdir(parents=True)
    (before_root / "src" / "sample.txt").write_text("alpha\nbeta\n", encoding="utf-8")

    current_file = tmp_path / "src" / "sample.txt"
    current_file.parent.mkdir(parents=True)
    current_file.write_text("alpha\nbeta changed\ngamma\n", encoding="utf-8")

    monkeypatch.setattr("aicv.index.create_embedding_provider", lambda _config: FakeProvider())

    index_turn(
        "011",
        request="Update sample text",
        files=["src/sample.txt"],
        validation="ok",
        backup_before=before_root.as_posix(),
        root=tmp_path,
        config=config,
    )

    store = load_embedding_store(tmp_path, config)
    kinds = {record.kind for record in store.records if record.turn_id == "turn-011"}

    assert len(store.records) >= 2
    assert "turn" in kinds
    assert "snippet" in kinds or "diff" in kinds
