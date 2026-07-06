from __future__ import annotations

import fnmatch
import hashlib
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

TOKEN_RE = re.compile(r"[a-zA-Z0-9_./-]+")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def slugify(value: str, fallback: str = "snapshot") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:60] or fallback


def normalize_turn_id(value: str) -> str:
    raw = value.strip().lower()
    if not raw:
        msg = "turn id cannot be empty"
        raise ValueError(msg)
    if raw.startswith("turn-"):
        return raw
    return f"turn-{raw}"


def turn_number(value: str) -> int | None:
    match = re.search(r"turn-(\d+)", normalize_turn_id(value))
    return int(match.group(1)) if match else None


def turn_matches(left: str, right: str) -> bool:
    normalized_left = normalize_turn_id(left)
    normalized_right = normalize_turn_id(right)
    if normalized_left == normalized_right:
        return True
    left_number = turn_number(normalized_left)
    right_number = turn_number(normalized_right)
    return left_number is not None and left_number == right_number


def tokenize(*values: object) -> list[str]:
    tokens: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            tokens.extend(tokenize(*value))
            continue
        tokens.extend(match.group(0).lower() for match in TOKEN_RE.finditer(str(value)))
    return tokens


def split_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    parts: list[str] = []
    for value in values:
        parts.extend(item.strip() for item in value.split(",") if item.strip())
    return parts


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        msg = f"unsafe relative path: {value}"
        raise ValueError(msg)
    return path


def should_exclude(
    path: Path, root: Path, patterns: list[str], *, is_dir: bool | None = None
) -> bool:
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    name = path.name
    directory = path.is_dir() if is_dir is None else is_dir

    for pattern in patterns:
        normalized = pattern.replace("\\", "/")
        dir_pattern = normalized.endswith("/")
        clean_pattern = normalized.rstrip("/")

        if dir_pattern and directory:
            if name == clean_pattern or rel == clean_pattern or rel.startswith(f"{clean_pattern}/"):
                return True
            if fnmatch.fnmatch(rel + "/", normalized) or fnmatch.fnmatch(name + "/", normalized):
                return True
            continue

        if fnmatch.fnmatch(name, clean_pattern) or fnmatch.fnmatch(rel, clean_pattern):
            return True
    return False


def copy_tree_filtered(source: Path, destination: Path, excludes: list[str]) -> int:
    files_copied = 0
    for item in source.iterdir():
        if should_exclude(item, source, excludes):
            continue
        target = destination / item.name
        if item.is_dir():
            files_copied += _copy_dir(item, target, source, excludes)
        else:
            ensure_directory(target.parent)
            shutil.copy2(item, target)
            files_copied += 1
    return files_copied


def _copy_dir(source: Path, destination: Path, root: Path, excludes: list[str]) -> int:
    files_copied = 0
    ensure_directory(destination)
    for item in source.iterdir():
        if should_exclude(item, root, excludes):
            continue
        target = destination / item.name
        if item.is_dir():
            files_copied += _copy_dir(item, target, root, excludes)
        else:
            ensure_directory(target.parent)
            shutil.copy2(item, target)
            files_copied += 1
    return files_copied
