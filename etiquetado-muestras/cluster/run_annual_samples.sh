#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/activate_mb_labels.sh"
cd "${SCRIPT_DIR}/.."

SAMPLES_DIR="${SAMPLES_DIR:-/home/lserey/mapbiomas_land/prod/samples}"
LANDCOVER_DIR="${LANDCOVER_DIR:-/home/lserey/mapbiomas_land/ancillary_data/landcover_col2}"
LABELS_DIR="${LABELS_DIR:-/home/lserey/mapbiomas_land/prod/labels/annual}"
PRODUCT_NAME="${PRODUCT_NAME:-annual_samples}"

mkdir -p "${LABELS_DIR}"

python scripts/02_generate_labels_c2_cluster.py \
  --samples-dir "${SAMPLES_DIR}" \
  --landcover-dir "${LANDCOVER_DIR}" \
  --labels-dir "${LABELS_DIR}" \
  --only-groups anuales \
  --product-name "${PRODUCT_NAME}" \
  --overwrite
