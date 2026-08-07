#!/usr/bin/env bash
#SBATCH --job-name=consol_cim
#SBATCH --partition=main
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=logs/consol_%j.out
#SBATCH --error=logs/consol_%j.err

set -euo pipefail

REPO="/home/lserey/repositorio/coverage/sample_generation_cim"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
cd "${REPO}"
mkdir -p logs

"${PYTHON}" scripts/05_consolidar.py
