#!/usr/bin/env bash
# Sequential batch: mask all CIM tiles for one year.
set -euo pipefail

BASE="/home/lserey/mapbiomas_land"
REPO="/home/lserey/repositorio/mosaico/mosaic_mask_water"
YEAR="${YEAR:-2015}"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python3}"

export GDAL_NUM_THREADS="${GDAL_NUM_THREADS:-4}"
export GDAL_CACHEMAX="${GDAL_CACHEMAX:-1024}"

mapfile -t TILES < <("$PYTHON" "$REPO/list_tiles.py" --year "$YEAR" 2>/dev/null)

echo "[INFO] Tiles to process: ${#TILES[@]} (year=$YEAR)"
for tile in "${TILES[@]}"; do
  echo "[RUN] $tile"
  "$PYTHON" "$REPO/mask_mosaic_cim_tile.py" --tile "$tile" --year "$YEAR"
done
echo "[OK] Batch finished"
