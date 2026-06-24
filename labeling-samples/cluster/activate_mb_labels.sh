#!/usr/bin/env bash
# Carga conda + entorno mb_labels (geopandas, rasterio, earthengine-api).
# Uso: source cluster/activate_mb_labels.sh
set -eo pipefail
module load miniconda3/24.7.1-zen4-j
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate mb_labels
