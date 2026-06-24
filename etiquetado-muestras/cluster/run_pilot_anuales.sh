#!/usr/bin/env bash
# Piloto: extrae 5 rectángulos con sieve y genera GeoPackages para anuales
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/activate_mb_labels.sh"
cd "${SCRIPT_DIR}/.."

SAMPLES_DIR="/home/lserey/mapbiomas_land/prod/samples"
LANDCOVER_DIR="/home/lserey/mapbiomas_land/ancillary_data/landcover_col2"
LABELS_DIR="/home/lserey/mapbiomas_land/prod/labels"

echo "--- Paso 1: extracción con sieve (5 rectángulos) ---"
python scripts/02_extract_sieve_rectangles.py \
  --samples-dir   "${SAMPLES_DIR}" \
  --landcover-dir "${LANDCOVER_DIR}" \
  --labels-dir    "${LABELS_DIR}" \
  --label-group   anuales \
  --sieve-size    9 \
  --max-rows      5 \
  --overwrite

echo ""
echo "--- Paso 2: generación de GeoPackages anuales ---"
python scripts/03_generate_labels_gpkg.py \
  --samples-dir "${SAMPLES_DIR}" \
  --labels-dir  "${LABELS_DIR}" \
  --only-groups anuales \
  --max-rows    5 \
  --overwrite
