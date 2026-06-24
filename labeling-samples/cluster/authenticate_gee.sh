#!/usr/bin/env bash
# Paso 2: completa autenticacion con el codigo de GEE.
# Uso: bash cluster/authenticate_gee.sh "CODIGO_DE_VERIFICACION"
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/activate_mb_labels.sh"
cd "${SCRIPT_DIR}/.."

CODE="${1:-}"
if [[ -z "${CODE}" ]]; then
  echo "ERROR: falta el codigo de verificacion."
  echo ""
  echo "Primero ejecuta:"
  echo "  bash cluster/print_gee_auth_url.sh"
  echo ""
  echo "Luego, con el codigo de GEE:"
  echo '  bash cluster/authenticate_gee.sh "TU_CODIGO"'
  read -r -p "Presiona Enter para cerrar... " _ || true
  exit 1
fi

PENDING="${HOME}/.config/earthengine/pending_auth.json"
if [[ ! -f "${PENDING}" ]]; then
  echo "ERROR: no hay sesion de auth pendiente."
  echo "Ejecuta primero: bash cluster/print_gee_auth_url.sh"
  read -r -p "Presiona Enter para cerrar... " _ || true
  exit 1
fi

python - "${CODE}" "${PENDING}" <<'PY'
import json
import sys
import ee

code = sys.argv[1]
pending_path = sys.argv[2]
pending = json.loads(open(pending_path, encoding="utf-8").read())

print("=== Earth Engine — paso 2 de 2 ===\n")
ee.Authenticate(
    authorization_code=code.strip(),
    code_verifier=pending["code_verifier"],
)
print("\nCredenciales guardadas en ~/.config/earthengine/credentials")

print("\nProbando proyecto mapbiomas-chile...")
try:
    ee.Initialize(project="mapbiomas-chile")
    print("OK: Earth Engine listo.")
except Exception as exc:
    print(f"ADVERTENCIA: autenticacion OK pero Initialize fallo: {exc}")
PY

status=$?
echo ""
if [[ $status -eq 0 ]]; then
  echo "Siguiente paso:"
  echo "  bash cluster/run_export_gee_pilot.sh"
else
  echo "Fallo la autenticacion. Genera un codigo nuevo:"
  echo "  bash cluster/print_gee_auth_url.sh"
fi
read -r -p "Presiona Enter para cerrar... " _ || true
exit "$status"
