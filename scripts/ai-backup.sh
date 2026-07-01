#!/usr/bin/env bash
set -euo pipefail

# ai-backup.sh
# Create a local backup snapshot through the AICV CLI.
#
# Usage:
#   ./scripts/ai-backup.sh "before navbar refactor"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MESSAGE="${1:-snapshot}"

cd "${PROJECT_ROOT}"
python3 -m aicv backup --message "${MESSAGE}"
