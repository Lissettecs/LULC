#!/usr/bin/env bash
# Genera GeoPackages por grupo y zona UTM desde los rasters sieved
set -euo pipefail
cd /home/lserey/repositorios/LULC/etiquetado-muestras

for group in anuales estables transiciones; do
  echo "=== Generando GeoPackages: ${group} ==="
  python scripts/03_generate_labels_gpkg.py \
    --samples-dir /home/lserey/mapbiomas_land/prod/samples \
    --labels-dir  /home/lserey/mapbiomas_land/prod/labels \
    --only-groups "${group}" \
    --overwrite
done

echo "=== Generando GeoPackages: clases_raras ==="
python scripts/03_generate_labels_gpkg.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --labels-dir  /home/lserey/mapbiomas_land/prod/labels \
  --only-groups clases_raras \
  --write-rare-copy \
  --overwrite
