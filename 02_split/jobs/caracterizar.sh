#!/usr/bin/env bash
# Caracteriza todas las cartas de la corrida activa, en serie o con N procesos.
#
#   jobs/caracterizar.sh            # serie
#   jobs/caracterizar.sh 8          # 8 procesos en paralelo
#
# Es reanudable: las cartas ya escritas se omiten, así que se puede volver a
# lanzar tras una caída sin perder lo hecho.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
PARALELO="${1:-1}"

cd "${REPO}"
mkdir -p logs

RUN_DIR="$(cat .ultima_corrida_caract 2>/dev/null || true)"
if [[ -z "${RUN_DIR}" || ! -d "${RUN_DIR}" ]]; then
  echo "No hay corrida activa. Ejecute primero:" >&2
  echo "  ${PYTHON} scripts/03_generar_lista_cartas.py" >&2
  exit 1
fi

LISTA="${RUN_DIR}/cartas.txt"
N="$(wc -l < "${LISTA}")"
echo "[$(date -Iseconds)] Corrida ${RUN_DIR}"
echo "[$(date -Iseconds)] ${N} cartas, ${PARALELO} proceso(s)"

xargs -a "${LISTA}" -P "${PARALELO}" -I{} \
  "${PYTHON}" scripts/04_caracterizar_carta.py --carta {} --resume

echo "[$(date -Iseconds)] Caracterización terminada; consolidando"
"${PYTHON}" scripts/05_consolidar.py
