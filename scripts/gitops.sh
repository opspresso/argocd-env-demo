#!/bin/bash
#
# Thin wrapper kept for the workflow's call convention. All logic lives in
# gitops.py; the TG_* environment variables carry the dispatch payload.

set -euo pipefail

SHELL_DIR=$(dirname "$0")

exec python3 "${SHELL_DIR}/gitops.py" "$@"
