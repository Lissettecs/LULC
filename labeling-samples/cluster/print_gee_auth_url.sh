#!/usr/bin/env bash
# Paso 1: muestra URL de autorizacion y guarda el code_verifier (no pide input).
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/activate_mb_labels.sh"
cd "${SCRIPT_DIR}/.."

python - <<'PY'
import json
from pathlib import Path
from ee.oauth import Flow

pending_path = Path.home() / ".config/earthengine/pending_auth.json"
pending_path.parent.mkdir(parents=True, exist_ok=True)

flow = Flow("notebook")
pending = {"auth_url": flow.auth_url, "code_verifier": flow.code_verifier}
pending_path.write_text(json.dumps(pending, indent=2), encoding="utf-8")

print("=== Earth Engine — paso 1 de 2 ===\n")
print("1. Abre esta URL en el navegador de tu PC:\n")
print(flow.auth_url)
print("\n2. Inicia sesion y pulsa 'Generar token'.")
print("3. Copia el codigo y ejecuta en ESTA misma carpeta:\n")
print('   bash cluster/authenticate_gee.sh "TU_CODIGO_AQUI"\n')
print(f"Verificador guardado en: {pending_path}")
PY

echo ""
read -r -p "Presiona Enter para cerrar... " _ || true
exit 0
