#!/usr/bin/env bash
# Piloto anuales: al menos 1 rectángulo por ecorregión (15) → GPKG + raster por UTM.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/activate_mb_labels.sh"
cd "${SCRIPT_DIR}/.."

SAMPLES_DIR="${SAMPLES_DIR:-/home/lserey/mapbiomas_land/prod/samples}"
LANDCOVER_DIR="${LANDCOVER_DIR:-/home/lserey/mapbiomas_land/ancillary_data/landcover_col2}"
LABELS_DIR="${LABELS_DIR:-/home/lserey/mapbiomas_land/tmp/labels_pilot_ecoregion}"
PRODUCT_NAME="${PRODUCT_NAME:-annual_samples_ecoregion_pilot}"
GRID_IDS_CSV="${GRID_IDS_CSV:-${LABELS_DIR}/pilot_grid_ids_por_ecorregion.csv}"

mkdir -p "${LABELS_DIR}"

python scripts/select_pilot_by_ecoregion.py \
  --samples-dir "${SAMPLES_DIR}" \
  --out-csv "${GRID_IDS_CSV}"

python scripts/00_check_inputs.py \
  --samples-dir "${SAMPLES_DIR}" \
  --landcover-dir "${LANDCOVER_DIR}"

python scripts/02_generate_labels_c2_cluster.py \
  --samples-dir "${SAMPLES_DIR}" \
  --landcover-dir "${LANDCOVER_DIR}" \
  --labels-dir "${LABELS_DIR}" \
  --only-groups anuales \
  --grid-ids-file "${GRID_IDS_CSV}" \
  --product-name "${PRODUCT_NAME}" \
  --connectivity 4 \
  --split-by-utm \
  --write-rasters \
  --overwrite
