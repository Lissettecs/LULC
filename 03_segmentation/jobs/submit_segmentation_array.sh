#!/usr/bin/env bash
# Submit parallel segmentation array on SLURM (partition main).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

REV_YEAR="${REV_YEAR:-2015}"
ARRAY_THROTTLE="${ARRAY_THROTTLE:-16}"

./jobs/prepare_segmentation_array.sh

MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:-/home/lserey/mapbiomas_land}"
OUTPUT_DIR="${OUTPUT_DIR:-${MAPBIOMAS_ROOT}/prod/segmentacion_slic_rev${REV_YEAR}}"
LIST="${LIST:-${OUTPUT_DIR}/logs/pending_rects_rev${REV_YEAR}.lst}"

N=$(grep -cve '^[[:space:]]*$' "${LIST}" || true)
if (( N == 0 )); then
  echo "Nothing pending — all rectangles already segmented."
  exit 0
fi

MAX=$((N - 1))
echo "Submitting array 0-${MAX}%${ARRAY_THROTTLE} (${N} rectangles)"

JOBID=$(sbatch --parsable \
  --array="0-${MAX}%${ARRAY_THROTTLE}" \
  --export=ALL,REV_YEAR="${REV_YEAR}" \
  jobs/run_segmentation_array.slurm)

echo "Array job: ${JOBID}"
CONSOL=$(sbatch --parsable --dependency="afterok:${JOBID}" \
  --export=ALL,REV_YEAR="${REV_YEAR}" \
  jobs/run_segmentation_consolidate.slurm)
echo "Consolidate job: ${CONSOL} (after array OK)"
echo "Monitor: squeue -u \$USER | grep seg_slic"
