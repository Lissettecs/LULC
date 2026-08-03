#!/usr/bin/env bash
# Submit SLURM segmentation array (one rectangle per task).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"
ARRAY_THROTTLE="${ARRAY_THROTTLE:-16}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Set MAPBIOMAS_ROOT}"

./jobs/prepare_segmentation_array.sh

OUTPUT_DIR="${OUTPUT_DIR:-${MAPBIOMAS_ROOT}/prod/segmentacion_slic_rev${REV_YEAR}}"
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

JOBID=$(sbatch --parsable \
  --chdir="${REPO}" \
  --array="0-${MAX}%${ARRAY_THROTTLE}" \
  --output="${LOG_DIR}/slurm_seg_%A_%a.out" \
  --error="${LOG_DIR}/slurm_seg_%A_%a.err" \
  --export=ALL,REV_YEAR="${REV_YEAR}",YEAR="${YEAR}",SEGLABEL_REPO="${REPO}" \
  jobs/run_segmentation_array.slurm)

CONSOL=$(sbatch --parsable --dependency="afterok:${JOBID}" \
  --chdir="${REPO}" \
  --output="${LOG_DIR}/slurm_seg_consolidate_%j.out" \
  --error="${LOG_DIR}/slurm_seg_consolidate_%j.err" \
  --export=ALL,REV_YEAR="${REV_YEAR}",YEAR="${YEAR}",SEGLABEL_REPO="${REPO}" \
  jobs/run_segmentation_consolidate.slurm)

echo "Segmentation array: ${JOBID}"
echo "Consolidation:      ${CONSOL} (afterok:${JOBID})"
echo "CONSOL_JOB=${CONSOL}"
