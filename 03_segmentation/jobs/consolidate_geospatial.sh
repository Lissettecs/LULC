#!/usr/bin/env bash
# Consolidate per-rectangle segments GPKG / features Parquet (after array completes).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO}"

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python3}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Defina MAPBIOMAS_ROOT}"
REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"
SEG_DIR="${SEGMENTATION_DIR:-${MAPBIOMAS_ROOT}/prod/03_segmentation_cim/${YEAR}}"

echo "Consolidando segmentación → ${SEG_DIR}/consolidado/"
"${PYTHON}" consolidate_pipeline_outputs.py \
  --rev-year "${REV_YEAR}" \
  --year "${YEAR}" \
  --segmentation-dir "${SEG_DIR}" \
  --stage segmentation
