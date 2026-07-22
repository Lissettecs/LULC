#!/usr/bin/env bash
# Consolida resumen_size_filter_{tile}_{year}.csv leyendo TIF ya generados.

#SBATCH --job-name=seg_slic_sf_csv
#SBATCH --partition=main
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=logs/seg_slic_sf_csv_%j.out
#SBATCH --error=logs/seg_slic_sf_csv_%j.err

set -euo pipefail

SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
mkdir -p "${SCRIPT_DIR}/logs"

if [[ -f /home/lserey/mapbiomas_land/activar_grupo.sh ]]; then
  # shellcheck disable=SC1091
  source /home/lserey/mapbiomas_land/activar_grupo.sh
fi

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
TILE="${TILE:-18HYD}"
YEAR="${YEAR:-2010}"

echo "[INFO] Consolidando CSV filtro tamaño · tile=${TILE} year=${YEAR}"

exec "${PYTHON}" -u "${SCRIPT_DIR}/seg_slic_grid.py" \
  --tile "${TILE}" \
  --year "${YEAR}" \
  --solo-size-filter \
  --resume
