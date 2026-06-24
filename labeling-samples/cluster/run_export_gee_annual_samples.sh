#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/activate_mb_labels.sh"
cd "${SCRIPT_DIR}/.."

LABELS_DIR="${LABELS_DIR:-/home/lserey/mapbiomas_land/prod/labels/annual}"
PRODUCT_NAME="${PRODUCT_NAME:-annual_samples}"
GEE_ASSET_BASE="${GEE_ASSET_BASE:-projects/mapbiomas-chile/assets/LULC/COLLECTION-03/SAMPLES/SAMPLES_COL3/SAMPLES_LABELS_SSL4EO}"
ASSET_ID="${ASSET_ID:-${GEE_ASSET_BASE}/${PRODUCT_NAME}}"
SOURCE_GPKG="${GPKG:-${LABELS_DIR}/${PRODUCT_NAME}.gpkg}"
LOCAL_GPKG="${SLURM_TMPDIR:-${TMPDIR:-/tmp}}/annual_samples_${SLURM_JOB_ID:-$$}.gpkg"
echo "Copiando GPKG a storage local (${SOURCE_GPKG} -> ${LOCAL_GPKG})"
cp "${SOURCE_GPKG}" "${LOCAL_GPKG}"
GPKG="${LOCAL_GPKG}"

python scripts/03_export_labels_gee_asset.py \
  --labels-dir "${LABELS_DIR}" \
  --group anuales \
  --gpkg "${GPKG}" \
  --layer "${PRODUCT_NAME}" \
  --asset-id "${ASSET_ID}" \
  --local-geojson "${LABELS_DIR}/${PRODUCT_NAME}.geojson" \
  --overwrite \
  --wait
