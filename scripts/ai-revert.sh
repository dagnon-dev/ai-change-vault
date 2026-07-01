#!/usr/bin/env bash
set -euo pipefail

# ai-revert.sh
# Revert a turn or a file through the AICV CLI.
#
# Usage:
#   ./scripts/ai-revert.sh --list
#   ./scripts/ai-revert.sh turn-003
#   ./scripts/ai-revert.sh turn-003 frontend/src/components/Navbar.tsx

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${1:-}" == "--list" ]]; then
  cd "${PROJECT_ROOT}"
  python3 -m aicv list --kind backups
  exit 0
fi

TURN="${1:-}"
TARGET_FILE="${2:-}"

if [[ -z "${TURN}" ]]; then
  echo "Usage:"
  echo "  ./scripts/ai-revert.sh --list"
  echo "  ./scripts/ai-revert.sh <turn-id> [file-path]"
  exit 1
fi

cd "${PROJECT_ROOT}"
if [[ -n "${TARGET_FILE}" ]]; then
  python3 -m aicv revert --turn "${TURN}" --file "${TARGET_FILE}" --yes
else
  python3 -m aicv revert --turn "${TURN}" --yes
fi
