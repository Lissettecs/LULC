#!/usr/bin/env bash
# Piloto: extrae 5 rectángulos con sieve y genera GeoPackages para anuales
set -euo pipefail
cd /home/lserey/repositorios/LULC/etiquetado-muestras

echo "--- Paso 1: extracción con sieve (5 rectángulos) ---"
python scripts/02_extract_sieve_rectangles.py \
  --samples-dir   /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/ancillary_data/landcover_col2 \
  --labels-dir    /home/lserey/mapbiomas_land/prod/labels \
  --sieve-size    9 \
  --max-rows      5 \
  --overwrite

echo ""
echo "--- Paso 2: generación de GeoPackages anuales ---"
python scripts/03_generate_labels_gpkg.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --labels-dir  /home/lserey/mapbiomas_land/prod/labels \
  --only-groups anuales \
  --max-rows    5 \
  --overwrite
