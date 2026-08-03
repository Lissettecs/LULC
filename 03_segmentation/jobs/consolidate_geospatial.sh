#!/usr/bin/env bash
# Consolidate segmentation GPKG/Parquet (run after array completes).
set -euo pipefail

PIPELINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PIPELINE}"

PYTHON="${PYTHON:-python3}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Set MAPBIOMAS_ROOT}"
REV_YEAR="${REV_YEAR:-2015}"

"${PYTHON}" consolidate_pipeline_outputs.py \
  --rev-year "${REV_YEAR}" \
  --stage segmentation
