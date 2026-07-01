#!/usr/bin/env python3
"""Query indexed turns through the AICV CLI."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Search stored turns or inspect one turn.")
    parser.add_argument("query", nargs="?", help="Search query.")
    parser.add_argument("--turn", help="Show a specific turn.")
    parser.add_argument("--file", help="Filter by a file path.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    command = ["python3", "-m", "aicv", "search"]
    if args.turn:
        command.extend(["--turn", args.turn])
    elif args.file:
        command.extend(["--file", args.file])
    elif args.query:
        command.append(args.query)
    else:
        parser.print_help()
        return 1

    result = subprocess.run(command, cwd=project_root, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
