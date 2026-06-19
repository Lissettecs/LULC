#!/usr/bin/env bash
set -euo pipefail
cd /home/lserey/repositorios/LULC/etiquetado-muestras
python scripts/00_check_inputs.py   --samples-dir /home/lserey/mapbiomas_land/prod/samples   --landcover-dir /home/lserey/mapbiomas_land/landcover_col2
