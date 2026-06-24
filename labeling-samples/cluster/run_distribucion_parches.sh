#!/usr/bin/env bash
# Diagnóstico de tamaños de parche (conect 4 vs 8) sobre *_classes.tif
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/activate_mb_labels.sh"
cd "${SCRIPT_DIR}/.."
python scripts/distribucion_parches_raster.py
