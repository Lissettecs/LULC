#!/usr/bin/env bash
# Piloto: 5 rectangulos anuales → GPKG + raster por UTM (conectividad 4 / rook).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/activate_mb_labels.sh"
cd "${SCRIPT_DIR}/.."

SAMPLES_DIR="${SAMPLES_DIR:-/home/lserey/mapbiomas_land/prod/samples}"
LANDCOVER_DIR="${LANDCOVER_DIR:-/home/lserey/mapbiomas_land/ancillary_data/landcover_col2}"
LABELS_DIR="${LABELS_DIR:-/home/lserey/mapbiomas_land/tmp/labels_pilot_annual_samples_v2}"
PRODUCT_NAME="${PRODUCT_NAME:-annual_samples_pilot5}"
MAX_RECTANGLES="${MAX_RECTANGLES:-5}"

mkdir -p "${LABELS_DIR}"

python scripts/00_check_inputs.py \
  --samples-dir "${SAMPLES_DIR}" \
  --landcover-dir "${LANDCOVER_DIR}"

python scripts/02_generate_labels_c2_cluster.py \
  --samples-dir "${SAMPLES_DIR}" \
  --landcover-dir "${LANDCOVER_DIR}" \
  --labels-dir "${LABELS_DIR}" \
  --only-groups anuales \
  --max-rectangles "${MAX_RECTANGLES}" \
  --product-name "${PRODUCT_NAME}" \
  --connectivity 4 \
  --split-by-utm \
  --write-rasters \
  --overwrite
