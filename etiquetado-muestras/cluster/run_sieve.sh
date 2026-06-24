#!/usr/bin/env bash
# Extrae rectángulos con filtro sieve y los guarda por zona UTM en prod/labels/rectangulos/
set -euo pipefail
cd /home/lserey/repositorios/LULC/etiquetado-muestras

python scripts/02_extract_sieve_rectangles.py \
  --samples-dir   /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/ancillary_data/landcover_col2 \
  --labels-dir    /home/lserey/mapbiomas_land/prod/labels \
  --sieve-size    9 \
  --overwrite
