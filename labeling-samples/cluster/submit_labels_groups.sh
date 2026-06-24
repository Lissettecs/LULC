#!/usr/bin/env bash
# Envía jobs SLURM de etiquetado por grupo y zona UTM.
# Uso:
#   bash cluster/submit_labels_groups.sh              # stable + transition + rare (pendientes)
#   bash cluster/submit_labels_groups.sh --all          # incluye annual (re-ejecución)
#   bash cluster/submit_labels_groups.sh stable         # solo stable UTM18+19
set -euo pipefail

CLUSTER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /home/lserey/logs

submit() {
  local slurm="$1"
  echo "sbatch ${slurm}"
  sbatch "${slurm}"
}

run_group() {
  local group="$1"
  case "${group}" in
    annual)
      submit "${CLUSTER_DIR}/labels_annual_utm18.slurm"
      submit "${CLUSTER_DIR}/labels_annual_utm19.slurm"
      ;;
    stable)
      submit "${CLUSTER_DIR}/labels_stable_utm18.slurm"
      submit "${CLUSTER_DIR}/labels_stable_utm19.slurm"
      ;;
    transition)
      submit "${CLUSTER_DIR}/labels_transition_utm18.slurm"
      submit "${CLUSTER_DIR}/labels_transition_utm19.slurm"
      ;;
    rare|rare_classes)
      submit "${CLUSTER_DIR}/labels_rare_classes_utm18.slurm"
      submit "${CLUSTER_DIR}/labels_rare_classes_utm19.slurm"
      ;;
    *)
      echo "Grupo desconocido: ${group}" >&2
      exit 1
      ;;
  esac
}

if [[ $# -eq 0 ]]; then
  run_group stable
  run_group transition
  run_group rare_classes
elif [[ "$1" == "--all" ]]; then
  run_group annual
  run_group stable
  run_group transition
  run_group rare_classes
else
  for group in "$@"; do
    run_group "${group}"
  done
fi
