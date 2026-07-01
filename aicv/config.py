from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_EXCLUDES = [
    ".git/",
    ".aicv/",
    "node_modules/",
    "__pycache__/",
    "*.pyc",
    ".venv/",
    "venv/",
    "output/",
    "dist/",
    "build/",
    ".DS_Store",
    ".coverage",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
]
PRIMARY_CONFIG_FILENAME = ".aicv.config.yaml"
LEGACY_CONFIG_FILENAME = ".aicv.yaml"


class AICVConfig(BaseSettings):
    """Runtime configuration loaded from defaults, .aicv.config.yaml and AICV_* env vars."""

    backup_dir: str = ".aicv/backups"
    rag_dir: str = ".aicv/rag"
    excludes: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    embedding_provider: Literal["none", "openai", "ollama", "sentence-transformers"] = "none"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_base_url: str = "http://localhost:11434"
    embedding_endpoint: str = "/api/embed"
    embedding_api_key: str | None = None
    embedding_batch_size: int = 16
    embedding_weight: float = 0.65
    keyword_weight: float = 0.35
    embedding_store: str = ".aicv/rag/embeddings.json"
    auto_index: bool = False
    session_log: str = "AI_SESSION_LOG.md"

    model_config = SettingsConfigDict(env_prefix="AICV_", extra="ignore", enable_decoding=False)

    @field_validator("excludes", mode="before")
    @classmethod
    def parse_excludes(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def backup_path(self, root: Path) -> Path:
        return resolve_project_path(root, self.backup_dir)

    def rag_path(self, root: Path) -> Path:
        return resolve_project_path(root, self.rag_dir)

    def session_log_path(self, root: Path) -> Path:
        return resolve_project_path(root, self.session_log)


def resolve_project_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def find_project_root(start: Path | None = None) -> Path:
    """Find the nearest configured project root, falling back to cwd."""

    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent

    for candidate in [current, *current.parents]:
        if project_has_config(candidate) or (candidate / ".aicv").exists():
            return candidate
    return current


def load_config(root: Path | None = None) -> AICVConfig:
    project_root = find_project_root(root)
    yaml_data = _load_yaml_config(resolve_config_path(project_root))
    env_data = _load_env_overrides()
    return AICVConfig.model_validate({**yaml_data, **env_data})


def resolve_config_path(root: Path) -> Path:
    primary = root / PRIMARY_CONFIG_FILENAME
    if primary.exists():
        return primary
    legacy = root / LEGACY_CONFIG_FILENAME
    if legacy.exists():
        return legacy
    return primary


def project_has_config(root: Path) -> bool:
    return resolve_config_path(root).exists()


def default_project_config(project_name: str | None = None) -> dict[str, object]:
    return {
        "project_name": project_name or "AI Change Vault Project",
        "enabled": True,
        "auto_backup": True,
        "auto_index": False,
        "backup_dir": ".aicv/backups",
        "rag_dir": ".aicv/rag",
        "embedding_provider": "none",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_weight": 0.65,
        "keyword_weight": 0.35,
        "embedding_batch_size": 16,
        "embedding_store": ".aicv/rag/embeddings.json",
        "excludes": list(DEFAULT_EXCLUDES),
    }


def render_project_config(config: Mapping[str, object]) -> str:
    return yaml.safe_dump(dict(config), sort_keys=False, allow_unicode=True)


def _load_yaml_config(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        msg = f"{path} must contain a YAML mapping"
        raise ValueError(msg)
    return data


def _load_env_overrides() -> dict[str, object]:
    values: dict[str, object] = {}
    mapping = {
        "AICV_BACKUP_DIR": "backup_dir",
        "AICV_RAG_DIR": "rag_dir",
        "AICV_EMBEDDING_PROVIDER": "embedding_provider",
        "AICV_EMBEDDING_MODEL": "embedding_model",
        "AICV_EMBEDDING_BASE_URL": "embedding_base_url",
        "AICV_EMBEDDING_ENDPOINT": "embedding_endpoint",
        "AICV_EMBEDDING_API_KEY": "embedding_api_key",
        "AICV_EMBEDDING_BATCH_SIZE": "embedding_batch_size",
        "AICV_EMBEDDING_WEIGHT": "embedding_weight",
        "AICV_KEYWORD_WEIGHT": "keyword_weight",
        "AICV_EMBEDDING_STORE": "embedding_store",
        "AICV_SESSION_LOG": "session_log",
    }
    for env_name, field_name in mapping.items():
        if env_name in os.environ:
            values[field_name] = os.environ[env_name]

    if "AICV_EXCLUDES" in os.environ:
        values["excludes"] = [
            item.strip() for item in os.environ["AICV_EXCLUDES"].split(",") if item.strip()
        ]
    if "AICV_AUTO_INDEX" in os.environ:
        values["auto_index"] = os.environ["AICV_AUTO_INDEX"].lower() in {"1", "true", "yes", "on"}
    return values
