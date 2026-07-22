#!/usr/bin/env bash
# Etiquetado C2 + fusión adyacente — 6 tiles MGRS 2010, τ = 0.95/0.90/0.85/0.80.
#
# Uso:
#   cd coverage_test/labeling/mapbiomas_segmentation/jobs/slurm
#   mkdir -p ../../logs
#   sbatch run_all_tiles_tau.slurm
#
# Un solo tile:
#   TILE=19KDU sbatch --array=5 run_all_tiles_tau.slurm

#SBATCH --job-name=label_tau
#SBATCH --partition=main
#SBATCH --array=0-5%6
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=../../logs/label_tau_%A_%a.out
#SBATCH --error=../../logs/label_tau_%A_%a.err

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SHELL_DIR="${REPO_ROOT}/jobs/shell"
mkdir -p "${REPO_ROOT}/logs" "/home/lserey/mapbiomas_land/test/image_segmentation/logs"

if [[ -f /home/lserey/mapbiomas_land/activar_grupo.sh ]]; then
  # shellcheck disable=SC1091
  source /home/lserey/mapbiomas_land/activar_grupo.sh
fi

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_labels/bin/python}"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="/home/lserey/.conda/envs/mb_coverage/bin/python"
fi
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

TILES=(18FXH 18GXP 18HYD 19HCD 19JCJ 19KDU)
TASK_ID="${SLURM_ARRAY_TASK_ID:-0}"
TILE="${TILE:-${TILES[$TASK_ID]}}"

echo "[INFO] host=$(hostname) job=${SLURM_JOB_ID:-local} array=${TASK_ID}"
echo "[INFO] python=$(${PYTHON} --version 2>&1)"
echo "[INFO] tile=${TILE}"
echo "[INFO] repo=${REPO_ROOT}"

exec env TILE="${TILE}" APPEND_LOG=1 PYTHON="${PYTHON}" \
  bash "${SHELL_DIR}/run_all_tiles_tau.sh"
