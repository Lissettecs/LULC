#!/usr/bin/env bash
# Etiqueta rectángulos anuales zona UTM18: extrae clips sieved y genera GeoPackage
set -euo pipefail
cd /home/lserey/repositorios/LULC/etiquetado-muestras

SAMPLES_DIR="/home/lserey/mapbiomas_land/prod/samples"
LANDCOVER_DIR="/home/lserey/mapbiomas_land/ancillary_data/landcover_col2"
LABELS_DIR="/home/lserey/mapbiomas_land/prod/labels"

echo "=========================================="
echo " PASO 1: Extraer rectángulos UTM18 (sieve)"
echo "=========================================="
python scripts/02_extract_sieve_rectangles.py \
  --samples-dir   "${SAMPLES_DIR}" \
  --landcover-dir "${LANDCOVER_DIR}" \
  --labels-dir    "${LABELS_DIR}" \
  --only-zones    UTM18 \
  --sieve-size    9 \
  --overwrite

echo ""
echo "=========================================="
echo " PASO 2: Generar GeoPackage anuales UTM18"
echo "=========================================="
python scripts/03_generate_labels_gpkg.py \
  --samples-dir "${SAMPLES_DIR}" \
  --labels-dir  "${LABELS_DIR}" \
  --only-groups anuales \
  --only-zones  UTM18 \
  --overwrite

echo ""
echo "Listo. Salida en:"
echo "  ${LABELS_DIR}/rectangulos/UTM18/"
echo "  ${LABELS_DIR}/anuales/UTM18/subdivisiones_C2_anuales_UTM18.gpkg"
