from __future__ import annotations

import base64
import hashlib
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import tomllib

PROJECT_NAME = "ai-change-vault"
DIST_NAME = "ai_change_vault"
VERSION = "0.1.0"
WHEEL_TAG = "py3-none-any"
ENTRY_POINT = "aicv = aicv.cli:app"
PYPROJECT = Path(__file__).resolve().with_name("pyproject.toml")
PROJECT_DATA = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
PROJECT = PROJECT_DATA["project"]


@dataclass(slots=True)
class _WheelFile:
    path: str
    data: bytes


def get_requires_for_build_wheel(config_settings=None):  # noqa: D401, ARG001
    return []


def get_requires_for_build_editable(config_settings=None):  # noqa: D401, ARG001
    return []


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):  # noqa: D401, ARG001
    return _write_metadata(Path(metadata_directory))


def prepare_metadata_for_build_editable(metadata_directory, config_settings=None):  # noqa: D401, ARG001
    return _write_metadata(Path(metadata_directory))


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):  # noqa: D401, ARG001
    return _build_wheel(Path(wheel_directory), editable=False)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):  # noqa: D401, ARG001
    return _build_wheel(Path(wheel_directory), editable=True)


def build_sdist(sdist_directory, config_settings=None):  # noqa: D401, ARG001
    sdist_directory = Path(sdist_directory)
    sdist_directory.mkdir(parents=True, exist_ok=True)
    sdist_name = f"{PROJECT_NAME}-{VERSION}.tar.gz"
    sdist_path = sdist_directory / sdist_name
    source_root = _source_root()

    files = [
        "pyproject.toml",
        "build_backend.py",
        "README.md",
        "LICENSE",
    ]
    directories = [
        "aicv",
        "docs",
        "tests",
    ]

    with tarfile.open(sdist_path, "w:gz") as archive:
        for filename in files:
            file_path = source_root / filename
            if file_path.exists():
                archive.add(file_path, arcname=f"{PROJECT_NAME}-{VERSION}/{filename}")
        for directory in directories:
            dir_path = source_root / directory
            if dir_path.exists():
                archive.add(dir_path, arcname=f"{PROJECT_NAME}-{VERSION}/{directory}")

    return sdist_name


def _build_wheel(wheel_directory: Path, *, editable: bool) -> str:
    wheel_directory.mkdir(parents=True, exist_ok=True)
    wheel_name = f"{DIST_NAME}-{VERSION}-{WHEEL_TAG}.whl"
    wheel_path = wheel_directory / wheel_name
    dist_info = f"{DIST_NAME}-{VERSION}.dist-info"

    files = [
        _WheelFile(
            path=f"{DIST_NAME}.pth",
            data=_source_root().as_posix().encode("utf-8") + b"\n",
        ),
        _WheelFile(path=f"{dist_info}/METADATA", data=_metadata().encode("utf-8")),
        _WheelFile(path=f"{dist_info}/WHEEL", data=_wheel_metadata().encode("utf-8")),
        _WheelFile(path=f"{dist_info}/entry_points.txt", data=_entry_points().encode("utf-8")),
    ]

    records: list[tuple[str, str, str]] = []
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            archive.writestr(file.path, file.data)
            records.append((file.path, *_record_hash(file.data)))
        records.append((f"{dist_info}/RECORD", "", ""))
        archive.writestr(f"{dist_info}/RECORD", _render_record(records).encode("utf-8"))

    return wheel_path.name


def _write_metadata(metadata_directory: Path) -> str:
    dist_info = metadata_directory / f"{DIST_NAME}-{VERSION}.dist-info"
    dist_info.mkdir(parents=True, exist_ok=True)
    (dist_info / "METADATA").write_text(_metadata(), encoding="utf-8")
    (dist_info / "WHEEL").write_text(_wheel_metadata(), encoding="utf-8")
    (dist_info / "entry_points.txt").write_text(_entry_points(), encoding="utf-8")
    return dist_info.name


def _metadata() -> str:
    lines = [
        "Metadata-Version: 2.1\n"
        f"Name: {PROJECT_NAME}\n"
        f"Version: {VERSION}\n"
        "Summary: Local snapshots, turn indexing and reversions for AI-assisted coding.\n"
        f"Requires-Python: {PROJECT.get('requires-python', '>=3.10')}\n"
    ]
    for dependency in PROJECT.get("dependencies", []):
        lines.append(f"Requires-Dist: {dependency}\n")
    for extra_name, dependencies in PROJECT.get("optional-dependencies", {}).items():
        lines.append(f"Provides-Extra: {extra_name}\n")
        for dependency in dependencies:
            lines.append(f'Requires-Dist: {dependency} ; extra == "{extra_name}"\n')
    return "".join(lines)


def _wheel_metadata() -> str:
    return (
        "Wheel-Version: 1.0\n"
        "Generator: local-backend\n"
        "Root-Is-Purelib: true\n"
        f"Tag: {WHEEL_TAG}\n"
    )


def _entry_points() -> str:
    return f"[console_scripts]\n{ENTRY_POINT}\n"


def _source_root() -> Path:
    return Path(__file__).resolve().parent


def _record_hash(data: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"sha256={encoded}", str(len(data))


def _render_record(rows: list[tuple[str, str, str]]) -> str:
    lines: list[str] = []
    for row in rows:
        lines.append(",".join(row))
    return "\n".join(lines) + "\n"
