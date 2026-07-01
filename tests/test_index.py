from pathlib import Path

from aicv.config import AICVConfig
from aicv.index import index_turn


def test_index_creates_turn_document_and_inverted_index(tmp_path: Path) -> None:
    document = index_turn(
        "1",
        request="Cambiar color del boton de login",
        files=["src/components/Navbar.tsx"],
        validation="lint + tests OK",
        root=tmp_path,
        config=AICVConfig(),
    )

    assert document.turn_id == "turn-1"
    assert (tmp_path / ".aicv" / "rag" / "turns" / "turn-1.json").exists()
    index_path = tmp_path / ".aicv" / "rag" / "index.json"
    assert index_path.exists()
    assert "navbar.tsx" in index_path.read_text(encoding="utf-8").lower()

