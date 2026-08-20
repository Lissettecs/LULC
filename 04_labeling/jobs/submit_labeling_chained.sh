#!/usr/bin/env bash
# Chain labeling after prepare_labeling (SLURM job PREP_JOB).
# Usage: ./jobs/submit_labeling_chained.sh PREP_JOB_ID
set -euo pipefail

PREP_JOB="${1:?Missing PREP_JOB_ID}"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"
ARRAY_THROTTLE="${ARRAY_THROTTLE:-16}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Set MAPBIOMAS_ROOT}"

LABEL_DIR="${LABEL_DIR:-${MAPBIOMAS_ROOT}/prod/04_labeling_cim/${YEAR}}"
LOG_DIR="${LOG_DIR:-${LABEL_DIR}/logs}"
LIST="${LOG_DIR}/pending_labeling_rev${YEAR}.lst"

mkdir -p "${LOG_DIR}"

WRAP=$(sbatch --parsable --dependency="afterok:${PREP_JOB}" \
  --chdir="${REPO}" \
  --output="${LOG_DIR}/submit_label_%j.out" \
  --error="${LOG_DIR}/submit_label_%j.err" \
  --export=ALL,REV_YEAR="${REV_YEAR}",YEAR="${YEAR}",PREP_JOB="${PREP_JOB}",SEGLABEL_REPO="${REPO}" \
  jobs/submit_labeling_from_list.slurm)

echo "Submit labeling (post-prepare): ${WRAP}"
echo "LABEL_SUBMIT_JOB=${WRAP}"
