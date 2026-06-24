#!/usr/bin/env bash
# Filtro espacial MMU (conect-8) sobre *_classes.tif → *_classes_sieve.tif
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/activate_mb_labels.sh"
cd "${SCRIPT_DIR}/.."
python scripts/filtro_sieve_etiquetas.py
