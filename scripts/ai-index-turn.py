#!/usr/bin/env python3
"""Index an AI turn through the AICV CLI."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Index a turn for later search and revert.")
    parser.add_argument("--turn", required=True, help="Turn number or id, for example 001.")
    parser.add_argument("--request", required=True, help="Original user request.")
    parser.add_argument("--files", default="", help="Comma-separated changed files.")
    parser.add_argument("--backup-before", default="", help="Backup path before the change.")
    parser.add_argument("--backup-after", default="", help="Backup path after the change.")
    parser.add_argument("--validation", default="", help="Validation summary.")
    parser.add_argument("--status", default="indexed", help="Turn status.")
    parser.add_argument("--description", default="", help="Optional extra description.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    command = [
        "python3",
        "-m",
        "aicv",
        "index",
        "--turn",
        args.turn,
        "--request",
        args.request,
        "--status",
        args.status,
    ]
    if args.files:
        command.extend(["--files", args.files])
    if args.backup_before:
        command.extend(["--backup-before", args.backup_before])
    if args.backup_after:
        command.extend(["--backup-after", args.backup_after])
    if args.validation:
        command.extend(["--validation", args.validation])
    if args.description:
        command.extend(["--description", args.description])

    result = subprocess.run(command, cwd=project_root, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
