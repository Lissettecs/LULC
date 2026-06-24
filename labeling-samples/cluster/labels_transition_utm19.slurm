#!/bin/bash
#SBATCH -J labels-transition-utm19
#SBATCH -p main
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=64G
#SBATCH --mail-user=lissette.cortes@uchile.cl
#SBATCH --mail-type=ALL
#SBATCH -t 08:00:00
#SBATCH -o /home/lserey/logs/labels_transition_utm19_%j.out
#SBATCH -e /home/lserey/logs/labels_transition_utm19_%j.err

# Pipeline transiciones UTM19: sieve → mosaicos {year}.tif → transition_samples_UTM19.gpkg
#   mkdir -p /home/lserey/logs
#   sbatch /home/lserey/repositorio/LULC/etiquetado-muestras/cluster/labels_transition_utm19.slurm

set -eo pipefail

echo "Host: $(hostname)"
echo "Inicio: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-local}"

bash /home/lserey/repositorio/LULC/etiquetado-muestras/cluster/run_transiciones_utm19.sh

echo "Fin: $(date)"
