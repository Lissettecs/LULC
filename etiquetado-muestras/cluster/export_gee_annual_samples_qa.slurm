#!/bin/bash
#SBATCH -J export-gee-annual-qa
#SBATCH -p main
#SBATCH -n 1
#SBATCH -c 2
#SBATCH --mem-per-cpu=4096
#SBATCH --mail-user=lissette.cortes@uchile.cl
#SBATCH --mail-type=ALL
#SBATCH -t 06:00:00
#SBATCH -o /home/lserey/logs/export_gee_annual_samples_qa_%j.out
#SBATCH -e /home/lserey/logs/export_gee_annual_samples_qa_%j.err

set -eo pipefail
echo "Host: $(hostname)"
echo "Inicio: $(date)"
bash /home/lserey/repositorio/LULC/etiquetado-muestras/cluster/run_export_gee_annual_samples_qa.sh
echo "Fin: $(date)"
