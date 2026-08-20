#!/usr/bin/env bash
# Submit SLURM segmentation array (one rectangle per task).
# Parameterized:
#   MOSAIC_KIND / MOSAIC_ROOT  — input mosaic (184_mask_water | 11b)
#   FEATURES_PARQUET           — 1/0 (default: 1 for 184, 0 for 11b if unset via kind policy in Python)
#   BAND_LAYOUT                — auto | 184 | 11b
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"
ARRAY_THROTTLE="${ARRAY_THROTTLE:-16}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Set MAPBIOMAS_ROOT}"
MOSAIC_KIND="${MOSAIC_KIND:-184_mask_water}"
MOSAIC_ROOT="${MOSAIC_ROOT:-}"
BAND_LAYOUT="${BAND_LAYOUT:-auto}"
# Empty FEATURES_PARQUET → let Python apply kind policy (11b → off)
FEATURES_PARQUET="${FEATURES_PARQUET:-}"

./jobs/prepare_segmentation_array.sh

OUTPUT_DIR="${OUTPUT_DIR:-${MAPBIOMAS_ROOT}/prod/03_segmentation_cim/${REV_YEAR}}"
LOG_DIR="${LOG_DIR:-${OUTPUT_DIR}/logs}"
mkdir -p "${LOG_DIR}"
LIST="${LIST:-${LOG_DIR}/pending_rects_rev${REV_YEAR}.lst}"

N=$(grep -cve '^[[:space:]]*$' "${LIST}" 2>/dev/null || true)
if (( N == 0 )); then
  echo "Segmentation: nothing pending (all rectangles with mosaic already processed)."
  echo "CONSOL_JOB="
  exit 0
fi

MAX=$((N - 1))
echo "Submitting segmentation array 0-${MAX}%${ARRAY_THROTTLE} (${N} rectangles)"
echo "  MOSAIC_KIND=${MOSAIC_KIND} MOSAIC_ROOT=${MOSAIC_ROOT:-<preset>}"
echo "  FEATURES_PARQUET=${FEATURES_PARQUET:-<policy>} BAND_LAYOUT=${BAND_LAYOUT}"

JOBID=$(sbatch --parsable \
  --chdir="${REPO}" \
  --array="0-${MAX}%${ARRAY_THROTTLE}" \
  --output="${LOG_DIR}/slurm_seg_%A_%a.out" \
  --error="${LOG_DIR}/slurm_seg_%A_%a.err" \
  --export=ALL,REV_YEAR="${REV_YEAR}",YEAR="${YEAR}",SEGLABEL_REPO="${REPO}",MOSAIC_KIND="${MOSAIC_KIND}",MOSAIC_ROOT="${MOSAIC_ROOT}",BAND_LAYOUT="${BAND_LAYOUT}",FEATURES_PARQUET="${FEATURES_PARQUET}" \
  jobs/run_segmentation_array.slurm)

CONSOL=$(sbatch --parsable --dependency="afterok:${JOBID}" \
  --chdir="${REPO}" \
  --output="${LOG_DIR}/slurm_seg_consolidate_%j.out" \
  --error="${LOG_DIR}/slurm_seg_consolidate_%j.err" \
  --export=ALL,REV_YEAR="${REV_YEAR}",YEAR="${YEAR}",SEGLABEL_REPO="${REPO}",MOSAIC_KIND="${MOSAIC_KIND}",MOSAIC_ROOT="${MOSAIC_ROOT}" \
  jobs/run_segmentation_consolidate.slurm)

echo "Segmentation array: ${JOBID}"
echo "Consolidation:      ${CONSOL} (afterok:${JOBID})"
echo "CONSOL_JOB=${CONSOL}"
