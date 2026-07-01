from pathlib import Path

from aicv.config import AICVConfig
from aicv.index import index_turn
from aicv.search import search_turns


def test_search_finds_turn_by_query_turn_and_file(tmp_path: Path) -> None:
    config = AICVConfig()
    index_turn(
        "004",
        request="Cambiar color del boton de login en navbar",
        files=["src/components/Navbar.tsx"],
        validation="ok",
        root=tmp_path,
        config=config,
    )

    assert search_turns("navbar login", root=tmp_path, config=config)[0].turn.turn_id == "turn-004"
    assert search_turns(turn="turn-4", root=tmp_path, config=config)[0].turn.turn_id == "turn-004"
    assert (
        search_turns(file="Navbar.tsx", root=tmp_path, config=config)[0].turn.turn_id
        == "turn-004"
    )
