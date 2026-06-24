#!/usr/bin/env bash
set -euo pipefail
cd /home/lserey/repositorio/LULC/etiquetado-muestras
source cluster/activate_mb_labels.sh
python scripts/02_generate_labels_c2_cluster.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/ancillary_data/landcover_col2 \
  --labels-dir /home/lserey/mapbiomas_land/tmp/labels_pilot_anuales_v2 \
  --only-groups anuales \
  --max-rows 5 \
  --overwrite \
  --export-gee-asset \
  --gee-asset-base projects/mapbiomas-chile/assets/LULC/COLLECTION-03/SAMPLES/SAMPLES_COL3/SAMPLES_SSL4EO/pilot_v2
