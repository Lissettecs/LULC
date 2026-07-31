#!/usr/bin/env bash
# Deprecated alias — use jobs/run_segmentation.sh
# Maps legacy env names: PRUEBA_TILE → TEST_TILE
export TEST_TILE="${TEST_TILE:-${PRUEBA_TILE:-}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/run_segmentation.sh" "$@"
