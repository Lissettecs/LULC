#!/usr/bin/env bash
# Run SLIC+RAG segmentation for all rectangles with an available masked mosaic.
#
# Usage (2015 production):
#   cd 03_segmentation
#   REV_YEAR=2015 ./jobs/run_segmentation.sh
#
# Test one tile:
#   REV_YEAR=2015 TEST_TILE=18GXA ./jobs/run_segmentation.sh
#
# Another year (when mask_mosaic_{YEAR} exists):
#   REV_YEAR=2009 YEAR=2009 ./jobs/run_segmentation.sh
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

PYTHON="${PYTHON:-python3}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Defina MAPBIOMAS_ROOT (ver env.example)}"
REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"
SKIP_EXISTING="${SKIP_EXISTING:-1}"
DRY_RUN="${DRY_RUN:-0}"
TEST_TILE="${TEST_TILE:-}"
GRID_ID="${GRID_ID:-}"
LIMIT="${LIMIT:-}"

MOSAIC_ROOT="${MOSAIC_ROOT:-${MAPBIOMAS_ROOT}/tmp/mask_mosaic_${YEAR}}"
OUTPUT_DIR="${OUTPUT_DIR:-${MAPBIOMAS_ROOT}/prod/segmentacion_slic_rev${REV_YEAR}}"
PLAN_JSON="${PLAN_JSON:-${OUTPUT_DIR}/plan_rev${REV_YEAR}.json}"
LOG_DIR="${LOG_DIR:-${OUTPUT_DIR}/logs}"
mkdir -p "${LOG_DIR}"
LOG="${LOG_DIR}/segmentation_$(date +%Y%m%d_%H%M).log"

echo "[$(date)] Plan rev_year=${REV_YEAR} · mosaic year=${YEAR}" | tee -a "${LOG}"
echo "[$(date)] mosaic_root=${MOSAIC_ROOT}" | tee -a "${LOG}"
echo "[$(date)] output_dir=${OUTPUT_DIR}" | tee -a "${LOG}"

PLAN_ARGS=(--rev-year "${REV_YEAR}" --year "${YEAR}" --mosaic-root "${MOSAIC_ROOT}"
           --output-dir "${OUTPUT_DIR}" --require-mosaic --export-plan "${PLAN_JSON}")
[[ -n "${TEST_TILE}" ]] && PLAN_ARGS+=(--test-tile "${TEST_TILE}")
[[ -n "${GRID_ID}" ]] && PLAN_ARGS+=(--grid-id "${GRID_ID}")
[[ "${SKIP_EXISTING}" == "1" ]] && PLAN_ARGS+=(--skip-existing)

"${PYTHON}" plan_segmentation.py "${PLAN_ARGS[@]}" 2>&1 | tee -a "${LOG}"

SEG_ARGS=(--rev-year "${REV_YEAR}" --year "${YEAR}" --mosaic-root "${MOSAIC_ROOT}"
          --output-dir "${OUTPUT_DIR}" --require-mosaic)
[[ -n "${TEST_TILE}" ]] && SEG_ARGS+=(--test-tile "${TEST_TILE}")
[[ -n "${GRID_ID}" ]] && SEG_ARGS+=(--grid-id "${GRID_ID}")
[[ "${SKIP_EXISTING}" == "1" ]] && SEG_ARGS+=(--skip-existing)
[[ -n "${LIMIT}" ]] && SEG_ARGS+=(--limit "${LIMIT}")
[[ "${DRY_RUN}" == "1" ]] && SEG_ARGS+=(--dry-run)

echo "[$(date)] Starting segmentation" | tee -a "${LOG}"
"${PYTHON}" run_slic_segmentation.py "${SEG_ARGS[@]}" 2>&1 | tee -a "${LOG}"
echo "[$(date)] Segmentation finished" | tee -a "${LOG}"
