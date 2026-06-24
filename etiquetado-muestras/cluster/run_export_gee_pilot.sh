#!/usr/bin/env bash
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/activate_mb_labels.sh"
cd "${SCRIPT_DIR}/.."

LABELS_DIR="${LABELS_DIR:-/home/lserey/mapbiomas_land/tmp/labels_pilot_anuales}"
GROUP="${GROUP:-anuales}"

python scripts/03_export_labels_gee_asset.py \
  --labels-dir "${LABELS_DIR}" \
  --group "${GROUP}" \
  --overwrite
status=$?

echo ""
if [[ $status -eq 0 ]]; then
  echo "Export GEE completado."
else
  echo "Export fallo (codigo $status). Si faltan credenciales:"
  echo "  bash cluster/print_gee_auth_url.sh"
  echo '  bash cluster/authenticate_gee.sh "TU_CODIGO"'
fi
read -r -p "Presiona Enter para cerrar... " _ || true
exit "$status"
