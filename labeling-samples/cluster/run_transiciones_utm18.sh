#!/usr/bin/env bash
# Etiqueta rectángulos transición zona UTM18: extrae mosaicos sieved y genera GeoPackage
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/activate_mb_labels.sh"
cd "${SCRIPT_DIR}/.."

SAMPLES_DIR="/home/lserey/mapbiomas_land/prod/samples"
LANDCOVER_DIR="/home/lserey/mapbiomas_land/ancillary_data/landcover_col2"
LABELS_DIR="/home/lserey/mapbiomas_land/prod/labels"

echo "=========================================="
echo " PASO 1: Extraer rectángulos UTM18 (sieve)"
echo "=========================================="
python scripts/02_extract_sieve_rectangles.py \
  --samples-dir   "${SAMPLES_DIR}" \
  --landcover-dir "${LANDCOVER_DIR}" \
  --labels-dir    "${LABELS_DIR}" \
  --only-zones    UTM18 \
  --label-group   transiciones \
  --sieve-size    9 \
  --overwrite

echo ""
echo "=========================================="
echo " PASO 2: Generar GeoPackage transiciones UTM18"
echo "=========================================="
python scripts/03_generate_labels_gpkg.py \
  --samples-dir "${SAMPLES_DIR}" \
  --labels-dir  "${LABELS_DIR}" \
  --only-groups transiciones \
  --only-zones  utm18 \
  --overwrite

echo ""
echo "Listo. Salida en:"
echo "  ${LABELS_DIR}/raster/transition/UTM18/{year}.tif"
echo "  ${LABELS_DIR}/vector/transition/UTM18/transition_samples_UTM18.gpkg"
