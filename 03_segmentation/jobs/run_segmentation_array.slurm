#!/usr/bin/env bash
#SBATCH --job-name=seg_slic
#SBATCH --partition=main
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00

set -euo pipefail

REPO="${SEGLABEL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${REPO}"

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python3}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Defina MAPBIOMAS_ROOT (ver env.example)}"
REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"
MOSAIC_KIND="${MOSAIC_KIND:-184_mask_water}"
MOSAIC_ROOT="${MOSAIC_ROOT:-}"
BAND_LAYOUT="${BAND_LAYOUT:-auto}"
# Vacío → política Python (11b → off / pendiente)
FEATURES_PARQUET="${FEATURES_PARQUET:-}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${MAPBIOMAS_ROOT}/prod/03_segmentation_cim}"
OUTPUT_DIR="${OUTPUT_DIR:-${OUTPUT_ROOT}/${YEAR}}"
LOG_DIR="${LOG_DIR:-${OUTPUT_DIR}/logs}"
LIST="${LIST:-${LOG_DIR}/pending_rects_rev${REV_YEAR}.lst}"
SLIC_SCALE="${SLIC_SCALE:-}"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export NUMEXPR_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

if [[ ! -s "${LIST}" ]]; then
  echo "ERROR: falta ${LIST} — ejecute prepare / submit_segmentation_11b_plan.sh"
  exit 1
fi

N_LINES=$(grep -cve '^[[:space:]]*$' "${LIST}" || true)
if (( SLURM_ARRAY_TASK_ID >= N_LINES )); then
  echo "[SKIP] tarea ${SLURM_ARRAY_TASK_ID} >= ${N_LINES} rectángulos"
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
OUT_YEAR="${OUTPUT_ROOT}/${YEAR_TASK}"
SUMMARY="${OUT_YEAR}/${TILE}/${GRID_ID}/${GRID_ID}_${YEAR_TASK}_summary.json"

echo "[TASK ${SLURM_ARRAY_TASK_ID}] ${YEAR_TASK} ${GRID_ID} en $(hostname) · $(date -Iseconds)"

if [[ -f "${SUMMARY}" ]]; then
  echo "[SKIP] ya procesado: ${SUMMARY}"
  exit 0
fi

EXTRA_ARGS=()
[[ -n "${MOSAIC_ROOT}" ]] && EXTRA_ARGS+=(--mosaic-root "${MOSAIC_ROOT}")
[[ -n "${MOSAIC_KIND}" ]] && EXTRA_ARGS+=(--mosaic-kind "${MOSAIC_KIND}")
[[ -n "${BAND_LAYOUT}" ]] && EXTRA_ARGS+=(--band-layout "${BAND_LAYOUT}")
if [[ -n "${FEATURES_PARQUET}" ]]; then
  if [[ "${FEATURES_PARQUET}" == "0" || "${FEATURES_PARQUET}" == "false" || "${FEATURES_PARQUET}" == "no" ]]; then
    EXTRA_ARGS+=(--no-features-parquet)
  else
    EXTRA_ARGS+=(--features-parquet)
  fi
fi
if [[ -n "${SLIC_SCALE}" ]]; then
  EXTRA_ARGS+=(--slic-scale "${SLIC_SCALE}")
fi

"${PYTHON}" run_slic_segmentation.py \
  --rev-year "${YEAR_TASK}" \
  --year "${YEAR_TASK}" \
  --output-dir "${OUT_YEAR}" \
  --grid-id "${GRID_ID}" \
  --require-mosaic \
  --skip-existing \
  "${EXTRA_ARGS[@]}"

echo "[OK] ${YEAR_TASK} ${GRID_ID} · $(date -Iseconds)"
