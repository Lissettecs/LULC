#!/usr/bin/env bash
set -euo pipefail
cd /home/lserey/repositorio/LULC/etiquetado-muestras
python scripts/00_check_inputs.py   --samples-dir /home/lserey/mapbiomas_land/prod/samples   --landcover-dir /home/lserey/mapbiomas_land/ancillary_data/landcover_col2
