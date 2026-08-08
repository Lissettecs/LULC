#!/bin/bash
#SBATCH --partition=main
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=06:00:00
#SBATCH --array=0-123%8
#SBATCH --job-name=mask_cim_water
#SBATCH --output=/home/lserey/repositorio/mosaico/mosaic_mask_water/logs/slurm_%A_%a.out
#SBATCH --error=/home/lserey/repositorio/mosaico/mosaic_mask_water/logs/slurm_%A_%a.err

set -euo pipefail

REPO="/home/lserey/repositorio/mosaico/mosaic_mask_water"
PYTHON="/home/lserey/.conda/envs/mb_coverage/bin/python3"
YEAR=2015

export GDAL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export GDAL_CACHEMAX=2048

mapfile -t TILES < <("$PYTHON" "$REPO/list_tiles.py" --year "$YEAR" 2>/dev/null)
TILE="${TILES[$SLURM_ARRAY_TASK_ID]}"

echo "[RUN] $TILE (task $SLURM_ARRAY_TASK_ID / ${#TILES[@]}) on $(hostname) at $(date -Iseconds)"
"$PYTHON" "$REPO/mask_mosaic_cim_tile.py" --tile "$TILE" --year "$YEAR"
echo "[OK] $TILE finished at $(date -Iseconds)"
