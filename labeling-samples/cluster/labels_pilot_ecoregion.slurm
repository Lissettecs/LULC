#!/bin/bash
#SBATCH -J labels-pilot-eco
#SBATCH -p main
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem-per-cpu=4096
#SBATCH --mail-user=lissette.cortes@uchile.cl
#SBATCH --mail-type=ALL
#SBATCH -t 04:00:00
#SBATCH -o /home/lserey/logs/labels_pilot_ecoregion_%j.out
#SBATCH -e /home/lserey/logs/labels_pilot_ecoregion_%j.err

# Piloto: 1 rectángulo anual por ecorregión (15) + rasters/GPKG por UTM.
#   mkdir -p /home/lserey/logs
#   sbatch /home/lserey/repositorio/LULC/etiquetado-muestras/cluster/labels_pilot_ecoregion.slurm

set -eo pipefail

echo "Host: $(hostname)"
echo "Inicio: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-local}"

bash /home/lserey/repositorio/LULC/etiquetado-muestras/cluster/run_pilot_ecoregion_coverage.sh

echo "Fin: $(date)"
