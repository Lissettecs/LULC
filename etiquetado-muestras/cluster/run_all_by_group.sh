#!/usr/bin/env bash
set -euo pipefail
cd /home/lserey/repositorios/LULC/etiquetado-muestras
for group in anuales estables transiciones; do
  echo "Procesando ${group}"
  python scripts/02_generate_labels_c2_cluster.py     --samples-dir /home/lserey/mapbiomas_land/prod/samples     --landcover-dir /home/lserey/mapbiomas_land/landcover_col2     --labels-dir /home/lserey/mapbiomas_land/prod/labels     --only-groups "${group}"     --overwrite
done
python scripts/02_generate_labels_c2_cluster.py   --samples-dir /home/lserey/mapbiomas_land/prod/samples   --landcover-dir /home/lserey/mapbiomas_land/landcover_col2   --labels-dir /home/lserey/mapbiomas_land/prod/labels   --only-groups clases_raras   --write-rare-copy   --overwrite
