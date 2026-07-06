from __future__ import annotations

import base64
import hashlib
import io
import os
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import tomllib

PROJECT_NAME = "ai-change-vault"
DIST_NAME = "ai_change_vault"
VERSION = "0.1.2"
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
    package_root = f"{PROJECT_NAME}-{VERSION}"

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

    with tempfile.NamedTemporaryFile(
        suffix=".tar.gz", delete=False, dir=sdist_directory
    ) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        with tarfile.open(temp_path, "w:gz") as archive:
            pkg_info = _metadata(include_description=True).encode("utf-8")
            pkg_info_tar = tarfile.TarInfo(name=f"{package_root}/PKG-INFO")
            pkg_info_tar.size = len(pkg_info)
            archive.addfile(pkg_info_tar, fileobj=io.BytesIO(pkg_info))
            for filename in files:
                file_path = source_root / filename
                if file_path.exists():
                    archive.add(file_path, arcname=f"{package_root}/{filename}")
            for directory in directories:
                dir_path = source_root / directory
                if dir_path.exists():
                    archive.add(dir_path, arcname=f"{package_root}/{directory}")
        os.replace(temp_path, sdist_path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    return sdist_name


def _build_wheel(wheel_directory: Path, *, editable: bool) -> str:
    wheel_directory.mkdir(parents=True, exist_ok=True)
    wheel_name = f"{DIST_NAME}-{VERSION}-{WHEEL_TAG}.whl"
    wheel_path = wheel_directory / wheel_name
    dist_info = f"{DIST_NAME}-{VERSION}.dist-info"

    files = [
        _WheelFile(
            path=f"{dist_info}/METADATA",
            data=_metadata(include_description=True).encode("utf-8"),
        ),
        _WheelFile(path=f"{dist_info}/WHEEL", data=_wheel_metadata().encode("utf-8")),
        _WheelFile(path=f"{dist_info}/entry_points.txt", data=_entry_points().encode("utf-8")),
    ]
    if editable:
        files.insert(
            0,
            _WheelFile(
                path=f"{DIST_NAME}.pth",
                data=_source_root().as_posix().encode("utf-8") + b"\n",
            ),
        )
    else:
        files = _package_files(files)

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


def _metadata(*, include_description: bool = False) -> str:
    lines = [
        "Metadata-Version: 2.1\n",
        f"Name: {PROJECT_NAME}\n",
        f"Version: {VERSION}\n",
        "Summary: Local snapshots, turn indexing and reversions for AI-assisted coding.\n",
        f"Requires-Python: {PROJECT.get('requires-python', '>=3.10')}\n",
    ]
    authors = PROJECT.get("authors", [])
    if isinstance(authors, list) and authors:
        first_author = authors[0]
        if isinstance(first_author, dict):
            name = first_author.get("name")
            email = first_author.get("email")
            if name:
                lines.append(f"Author: {name}\n")
            if email:
                lines.append(f"Author-email: {email}\n")

    license_value = PROJECT.get("license")
    if isinstance(license_value, str):
        lines.append(f"License: {license_value}\n")
    elif isinstance(license_value, dict):
        license_text = license_value.get("text")
        license_file = license_value.get("file")
        if isinstance(license_text, str):
            lines.append(f"License: {license_text}\n")
        elif isinstance(license_file, str):
            lines.append(f"License: {license_file}\n")

    keywords = PROJECT.get("keywords", [])
    if isinstance(keywords, list) and keywords:
        lines.append(f"Keywords: {', '.join(str(keyword) for keyword in keywords)}\n")

    for classifier in PROJECT.get("classifiers", []):
        lines.append(f"Classifier: {classifier}\n")

    project_urls = PROJECT.get("urls", {})
    if isinstance(project_urls, dict):
        for label, url in project_urls.items():
            lines.append(f"Project-URL: {label}, {url}\n")

    for dependency in PROJECT.get("dependencies", []):
        lines.append(f"Requires-Dist: {dependency}\n")
    for extra_name, dependencies in PROJECT.get("optional-dependencies", {}).items():
        lines.append(f"Provides-Extra: {extra_name}\n")
        for dependency in dependencies:
            lines.append(f'Requires-Dist: {dependency} ; extra == "{extra_name}"\n')
    if include_description:
        readme = PROJECT_DATA.get("project", {}).get("readme")
        if isinstance(readme, str):
            readme_path = Path(__file__).resolve().with_name(readme)
            if readme_path.exists():
                lines.append("Description-Content-Type: text/markdown; charset=UTF-8\n")
                lines.append("\n")
                lines.append(readme_path.read_text(encoding="utf-8"))
                if not lines[-1].endswith("\n"):
                    lines[-1] = lines[-1] + "\n"
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


def _package_files(files: list[_WheelFile]) -> list[_WheelFile]:
    package_root = _source_root() / "aicv"
    for path in sorted(package_root.rglob("*")):
        if path.is_dir():
            continue
        if path.suffix == ".pyc" or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(_source_root()).as_posix()
        files.append(_WheelFile(path=relative, data=path.read_bytes()))
    return files


def _record_hash(data: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"sha256={encoded}", str(len(data))


def _render_record(rows: list[tuple[str, str, str]]) -> str:
    lines: list[str] = []
    for row in rows:
        lines.append(",".join(row))
    return "\n".join(lines) + "\n"
