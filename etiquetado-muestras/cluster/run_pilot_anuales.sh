#!/usr/bin/env bash
set -euo pipefail
cd /home/lserey/repositorios/LULC/etiquetado-muestras
python scripts/02_generate_labels_c2_cluster.py   --samples-dir /home/lserey/mapbiomas_land/prod/samples   --landcover-dir /home/lserey/mapbiomas_land/landcover_col2   --labels-dir /home/lserey/mapbiomas_land/prod/labels   --only-groups anuales   --max-rows 5   --overwrite
