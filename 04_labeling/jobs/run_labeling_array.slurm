#!/usr/bin/env bash
#SBATCH --job-name=label_c2
#SBATCH --partition=main
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00

set -euo pipefail

REPO="${SEGLABEL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${REPO}"

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python3}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Defina MAPBIOMAS_ROOT}"
REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"

SEG_ROOT="${SEG_ROOT:-${MAPBIOMAS_ROOT}/prod/03_segmentation_cim}"
LABEL_ROOT="${LABEL_ROOT:-${MAPBIOMAS_ROOT}/prod/04_labeling_cim}"
SEG_DIR="${SEG_DIR:-${SEG_ROOT}/${YEAR}}"
LABEL_DIR="${LABEL_DIR:-${LABEL_ROOT}/${YEAR}}"
LOG_DIR="${LOG_DIR:-${LABEL_DIR}/logs}"
LIST="${LIST:-${LOG_DIR}/pending_labeling_rev${YEAR}.lst}"

if [[ ! -s "${LIST}" ]]; then
  echo "ERROR: falta ${LIST}"
  exit 1
fi

N_LINES=$(grep -cve '^[[:space:]]*$' "${LIST}" || true)
if (( SLURM_ARRAY_TASK_ID >= N_LINES )); then
  echo "[SKIP] tarea ${SLURM_ARRAY_TASK_ID} >= ${N_LINES}"
  exit 0
fi

LINE=$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "${LIST}")
if [[ "${LINE}" == *$'\t'* ]]; then
  YEAR_TASK="${LINE%%$'\t'*}"
  GRID_ID="${LINE#*$'\t'}"
else
  YEAR_TASK="${YEAR}"
  GRID_ID="${LINE}"
fi
TILE="${GRID_ID%%_*}"
SEG_YEAR="${SEG_ROOT}/${YEAR_TASK}"
LABEL_YEAR="${LABEL_ROOT}/${YEAR_TASK}"
OUT_SUMMARY="${LABEL_YEAR}/${TILE}/${GRID_ID}/${GRID_ID}_${YEAR_TASK}_labeling_summary.json"

echo "[TASK ${SLURM_ARRAY_TASK_ID}] ${YEAR_TASK} ${GRID_ID} · $(date -Iseconds)"

if [[ -f "${OUT_SUMMARY}" ]]; then
  echo "[SKIP] ya etiquetado: ${OUT_SUMMARY}"
  exit 0
fi

"${PYTHON}" label_segments_c2.py \
  --year "${YEAR_TASK}" \
  --segmentation-dir "${SEG_YEAR}" \
  --output-dir "${LABEL_YEAR}" \
  --grid-id "${GRID_ID}"

echo "[OK] ${YEAR_TASK} ${GRID_ID} · $(date -Iseconds)"
