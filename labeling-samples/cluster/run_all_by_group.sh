#!/usr/bin/env bash
# Pipeline completo: sieve → GeoPackages para todos los grupos y zonas UTM
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "=========================================="
echo " PASO 1: Extraer rectángulos con sieve"
echo "=========================================="
bash cluster/run_sieve.sh

echo ""
echo "=========================================="
echo " PASO 2: Generar GeoPackages"
echo "=========================================="
bash cluster/run_gpkg.sh

echo ""
echo "Pipeline completo."
