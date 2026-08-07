#!/usr/bin/env bash
#SBATCH --job-name=consol_v02
#SBATCH --partition=main
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=logs/consol_%j.out
#SBATCH --error=logs/consol_%j.err

set -euo pipefail

REPO="/home/lserey/repositorio/coverage/ssl4eo-sample-generation_v02"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
cd "${REPO}"
mkdir -p logs

"${PYTHON}" scripts/05_consolidar_grillas.py
