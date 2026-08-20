#!/usr/bin/env bash
# Submit SLURM array for C2 labeling (CIM tiles).
# Optional: DEPENDENCY=afterok:JOBID (e.g. segmentation consolidation).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"
ARRAY_THROTTLE="${ARRAY_THROTTLE:-16}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Defina MAPBIOMAS_ROOT}"
DEPENDENCY="${DEPENDENCY:-}"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python3}"
export PYTHON

./jobs/prepare_labeling_array.sh

LABEL_DIR="${LABEL_DIR:-${MAPBIOMAS_ROOT}/prod/04_labeling_cim/${YEAR}}"
SEG_DIR="${SEG_DIR:-${MAPBIOMAS_ROOT}/prod/03_segmentation_cim/${YEAR}}"
LOG_DIR="${LOG_DIR:-${LABEL_DIR}/logs}"
mkdir -p "${LOG_DIR}"
LIST="${LIST:-${LOG_DIR}/pending_labeling_rev${YEAR}.lst}"

N=$(grep -cve '^[[:space:]]*$' "${LIST}" 2>/dev/null || true)
if (( N == 0 )); then
  echo "Etiquetado: nada pendiente."
  exit 0
fi

MAX=$((N - 1))
DEP_ARGS=()
[[ -n "${DEPENDENCY}" ]] && DEP_ARGS=(--dependency="${DEPENDENCY}")

echo "Enviando array etiquetado 0-${MAX}%${ARRAY_THROTTLE} (${N} rectángulos)"

JOBID=$(sbatch --parsable "${DEP_ARGS[@]}" \
  --chdir="${REPO}" \
  --array="0-${MAX}%${ARRAY_THROTTLE}" \
  --output="${LOG_DIR}/slurm_label_%A_%a.out" \
  --error="${LOG_DIR}/slurm_label_%A_%a.err" \
  --export=ALL,REV_YEAR="${REV_YEAR}",YEAR="${YEAR}",SEGLABEL_REPO="${REPO}",SEG_DIR="${SEG_DIR}",LABEL_DIR="${LABEL_DIR}",PYTHON="${PYTHON}" \
  jobs/run_labeling_array.slurm)

CONSOL=$(sbatch --parsable --dependency="afterok:${JOBID}" \
  --chdir="${REPO}" \
  --output="${LOG_DIR}/slurm_label_consolidate_%j.out" \
  --error="${LOG_DIR}/slurm_label_consolidate_%j.err" \
  --export=ALL,YEAR="${YEAR}",REV_YEAR="${REV_YEAR}",SEGLABEL_REPO="${REPO}",SEGLABEL_PIPELINE="${REPO}/..",LABEL_DIR="${LABEL_DIR}",PYTHON="${PYTHON}" \
  jobs/run_labeling_consolidate.slurm)

echo "Labeling array: ${JOBID}"
echo "Consolidation:  ${CONSOL} (afterok:${JOBID})"
