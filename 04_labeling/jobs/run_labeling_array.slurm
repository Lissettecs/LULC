#!/usr/bin/env bash
#SBATCH --job-name=label_c2
#SBATCH --partition=main
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G
#SBATCH --time=00:45:00

set -euo pipefail

REPO="${SEGLABEL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${REPO}"

PYTHON="${PYTHON:-python3}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Set MAPBIOMAS_ROOT}"
REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"

LABEL_DIR="${LABEL_DIR:-${MAPBIOMAS_ROOT}/prod/labeling_slic_rev${YEAR}}"
LOG_DIR="${LOG_DIR:-${LABEL_DIR}/logs}"
LIST="${LIST:-${LOG_DIR}/pending_labeling_rev${YEAR}.lst}"

if [[ ! -s "${LIST}" ]]; then
  echo "ERROR: missing ${LIST}"
  exit 1
fi

N_LINES=$(grep -cve '^[[:space:]]*$' "${LIST}" || true)
if (( SLURM_ARRAY_TASK_ID >= N_LINES )); then
  echo "[SKIP] task ${SLURM_ARRAY_TASK_ID} >= ${N_LINES}"
  exit 0
fi

GRID_ID=$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "${LIST}")
TILE="${GRID_ID%%_*}"
OUT_SUMMARY="${LABEL_DIR}/${TILE}/${GRID_ID}/${GRID_ID}_labeling_summary.json"

echo "[TASK ${SLURM_ARRAY_TASK_ID}] labeling ${GRID_ID} · $(date -Iseconds)"

if [[ -f "${OUT_SUMMARY}" ]]; then
  echo "[SKIP] already labeled: ${OUT_SUMMARY}"
  exit 0
fi

"${PYTHON}" etiquetar_segmentos_c2.py \
  --year "${YEAR}" \
  --grid-id "${GRID_ID}"

echo "[OK] ${GRID_ID} · $(date -Iseconds)"
