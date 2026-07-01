from __future__ import annotations

from pathlib import Path

from .config import AICVConfig
from .utils import utc_now


def append_session_log(root: Path, config: AICVConfig, title: str, lines: list[str]) -> None:
    path = config.session_log_path(root)
    if not path.exists():
        path.write_text("# AI Session Log\n\n", encoding="utf-8")

    timestamp = utc_now().isoformat()
    entry = [f"## {timestamp} - {title}", ""]
    entry.extend(f"- {line}" for line in lines)
    entry.append("")
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(entry))
