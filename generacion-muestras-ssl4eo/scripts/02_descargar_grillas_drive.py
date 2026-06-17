#!/usr/bin/env python3
"""
Descarga automatica de grillas exportadas por Earth Engine desde Google Drive.

Busca archivos en la carpeta GEE_exports (por defecto), agrupa los componentes
de cada shapefile (.shp, .shx, .dbf, .prj, .cpg, .fix, ...) y guarda un .zip
en archivos_intermedios/gee_caracterizacion/ (listo para 03_seleccion_rectangulos.py).

Requisitos:
  pip install earthengine-api google-api-python-client pip-system-certs

Usa el mismo token OAuth de Earth Engine (scope drive). Si expiro:
  python caracterizacion_grillas_gee.py --authenticate

Ejemplos:
  python descargar_grillas_drive.py
  python scripts/02_descargar_grillas_drive.py --prefix grilla_ssl4eo_muestras_homogeneo_2x2_UTM18_scale300
  python scripts/02_descargar_grillas_drive.py --scale300-all
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    import pip_system_certs.wrapt_requests  # noqa: F401
except ImportError:
    pass

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

try:
    from ee import oauth as ee_oauth
except ImportError:
    ee_oauth = None

from rutas_proyecto import GEE_CARACTERIZACION_DIR, GRILLAS_ROOT

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = GEE_CARACTERIZACION_DIR
DEFAULT_DRIVE_FOLDER = "GEE_exports"
TOKEN_DIR = Path.home() / ".config" / "grillas_ssl4eo"
TOKEN_PATH = TOKEN_DIR / "drive_token.json"
EE_CRED_PATH = Path.home() / ".config" / "earthengine" / "credentials"

# Mismo scope que Earth Engine (el refresh_token EE ya lo incluye).
SCOPES = ["https://www.googleapis.com/auth/drive"]
EE_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/earthengine",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/devstorage.full_control",
]

SCALE300_PREFIXES = [
    "grilla_ssl4eo_muestras_homogeneo_2x2_UTM18_scale300",
    "grilla_ssl4eo_muestras_mixto_3x3_UTM18_scale300",
    "grilla_ssl4eo_muestras_homogeneo_2x2_UTM19_scale300",
    "grilla_ssl4eo_muestras_mixto_3x3_UTM19_scale300",
]

# Sufijos que caracterizacion_grillas_gee.py agrega segun --class-level
EXPORT_NAME_SUFFIXES = ("", "_n3", "_general")

# Extensiones que GEE/Drive puede exportar para un shapefile.
SHAPEFILE_EXTENSIONS = {
    ".shp", ".shx", ".dbf", ".prj", ".cpg", ".fix", ".sbn", ".sbx", ".xml",
}
REQUIRED_SHAPE_PARTS = {".shp", ".shx", ".dbf"}
MIN_ZIP_BYTES = 50_000


def _load_ee_credentials_file() -> dict:
    if not EE_CRED_PATH.exists():
        raise FileNotFoundError(
            f"No hay credenciales EE en {EE_CRED_PATH}. "
            "Ejecuta primero: python caracterizacion_grillas_gee.py --authenticate"
        )
    return json.loads(EE_CRED_PATH.read_text(encoding="utf-8"))


def _oauth_client_info(ee_cred: dict) -> tuple[str, str]:
    """Client OAuth de Earth Engine (formato nuevo sin client_id en el JSON)."""
    if ee_oauth is None:
        raise ImportError("Falta earthengine-api. Ejecuta: pip install earthengine-api")
    client_id = ee_cred.get("client_id", ee_oauth.CLIENT_ID)
    client_secret = ee_cred.get("client_secret", ee_oauth.CLIENT_SECRET)
    return client_id, client_secret


def _credentials_from_ee_refresh(ee_cred: dict) -> Credentials | None:
    """Reutiliza refresh_token EE (incluye scope drive) sin abrir el navegador."""
    refresh = ee_cred.get("refresh_token")
    if not refresh:
        return None
    client_id, client_secret = _oauth_client_info(ee_cred)
    scopes = ee_cred.get("scopes") or EE_DRIVE_SCOPES
    return Credentials(
        None,
        refresh_token=refresh,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes,
    )


def _refresh_and_cache(creds: Credentials) -> Credentials:
    creds.refresh(Request())
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _credentials_from_token_file() -> Credentials | None:
    if not TOKEN_PATH.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        return _refresh_and_cache(creds)
    return creds if creds.valid else None


def _authenticate_via_earth_engine() -> Credentials:
    """Flujo OAuth oficial de EE (el cliente publico no admite InstalledAppFlow)."""
    import ee

    print("Re-autorizando via Earth Engine...")
    print("  python caracterizacion_grillas_gee.py --authenticate")
    ee.Authenticate()
    ee.Initialize(project="mapbiomas-chile")
    ee_cred = _load_ee_credentials_file()
    creds = _credentials_from_ee_refresh(ee_cred)
    if not creds:
        raise RuntimeError("Earth Engine no devolvio refresh_token.")
    return _refresh_and_cache(creds)


def get_drive_service(*, force_auth: bool = False):
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    if force_auth and TOKEN_PATH.exists():
        TOKEN_PATH.unlink()

    creds: Credentials | None = None

    # 1) Token EE (incluye scope drive)
    try:
        ee_cred = _load_ee_credentials_file()
        creds = _credentials_from_ee_refresh(ee_cred)
        if creds:
            creds = _refresh_and_cache(creds)
            print("Acceso a Drive via credenciales Earth Engine.")
    except Exception as exc:
        print(f"Token EE no disponible ({exc}).")

    # 2) Cache local de sesiones anteriores
    if not creds or not creds.valid:
        creds = _credentials_from_token_file()

    # 3) Re-auth oficial EE (evita error 403 restricted_client)
    if not creds or not creds.valid:
        creds = _authenticate_via_earth_engine()

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def find_folder_id(service, folder_name: str) -> str:
    q = (
        f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    res = service.files().list(
        q=q, spaces="drive", fields="files(id, name)", pageSize=10
    ).execute()
    files = res.get("files", [])
    if not files:
        raise FileNotFoundError(
            f"Carpeta '{folder_name}' no encontrada en Drive. "
            "Verifica que la exportacion EE haya terminado."
        )
    if len(files) > 1:
        print(f"  Advertencia: varias carpetas '{folder_name}', usando la primera.")
    return files[0]["id"]


def list_drive_files(service, folder_id: str, name_contains: str = "") -> list[dict]:
    q = f"'{folder_id}' in parents and trashed = false"
    if name_contains:
        q += f" and name contains '{name_contains}'"
    files: list[dict] = []
    page_token = None
    while True:
        res = service.files().list(
            q=q,
            spaces="drive",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
            pageSize=100,
            pageToken=page_token,
            orderBy="modifiedTime desc",
        ).execute()
        files.extend(res.get("files", []))
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return files


def candidate_prefixes(prefix: str) -> list[str]:
    """Variantes de nombre exportadas por GEE (con/sin _n3 o _general)."""
    base = prefix
    for suf in ("_n3", "_general"):
        if base.endswith(suf):
            base = base[: -len(suf)]
            break
    seen: set[str] = set()
    out: list[str] = []
    for name in (prefix,) + tuple(base + s for s in EXPORT_NAME_SUFFIXES):
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def resolve_drive_prefix(files: list[dict], prefix: str) -> str | None:
    """Devuelve el prefijo real en Drive (p. ej. con sufijo _n3)."""
    for cand in candidate_prefixes(prefix):
        if find_ready_zip(files, cand):
            return cand
        if find_shapefile_components(files, cand):
            return cand
    return None


def find_ready_zip(files: list[dict], prefix: str) -> dict | None:
    """ZIP ya empaquetado en Drive (si existe y no es diminuto)."""
    zips = [f for f in files if f["name"] == f"{prefix}.zip"]
    if not zips:
        return None
    best = max(zips, key=lambda f: f.get("modifiedTime", ""))
    if int(best.get("size") or 0) < MIN_ZIP_BYTES:
        print(f"  ZIP en Drive muy pequeno ({best.get('size')} B); rearmando desde partes.")
        return None
    return best


def find_shapefile_components(files: list[dict], prefix: str) -> list[dict]:
    """Todos los archivos prefix.ext del shapefile (ultima version por extension)."""
    by_ext: dict[str, dict] = {}
    for f in files:
        name = f["name"]
        if not name.startswith(prefix + "."):
            continue
        ext = Path(name).suffix.lower()
        if ext not in SHAPEFILE_EXTENSIONS:
            continue
        prev = by_ext.get(ext)
        if not prev or f.get("modifiedTime", "") > prev.get("modifiedTime", ""):
            by_ext[ext] = f
    return [by_ext[e] for e in sorted(by_ext)]


def download_file(service, file_id: str, dest: Path, *, quiet: bool = False) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(dest, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    if not quiet:
        print(f"    {dest.name}")


def zip_shapefile_components(
    service,
    components: list[dict],
    dest_zip: Path,
) -> None:
    """Descarga componentes a carpeta temporal y crea dest_zip."""
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gee_shp_") as tmp:
        tmp_path = Path(tmp)
        print(f"  Empaquetando {len(components)} archivos -> {dest_zip.name}")
        for f in sorted(components, key=lambda x: x["name"]):
            download_file(service, f["id"], tmp_path / f["name"], quiet=True)
            print(f"    {f['name']}  ({f.get('size', '?')} B)")
        with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(tmp_path.iterdir()):
                zf.write(path, arcname=path.name)
    print(f"  ZIP listo: {dest_zip}  ({dest_zip.stat().st_size} B)")


def download_prefix(
    service,
    folder_id: str,
    prefix: str,
    output_dir: Path,
    *,
    overwrite: bool,
) -> bool:
    files = list_drive_files(service, folder_id, name_contains=prefix.split("_scale300")[0])
    drive_prefix = resolve_drive_prefix(files, prefix)
    if drive_prefix is None:
        tried = ", ".join(candidate_prefixes(prefix))
        print(f"  No encontrado en Drive (probado: {tried})")
        return False

    if drive_prefix != prefix:
        print(f"  Encontrado como: {drive_prefix}")

    dest = output_dir / f"{drive_prefix}.zip"
    if dest.exists() and not overwrite:
        print(f"  Ya existe (omitido): {dest.name}")
        return True

    ready_zip = find_ready_zip(files, drive_prefix)
    if ready_zip:
        size = int(ready_zip.get("size") or 0)
        print(f"  Descargando ZIP de Drive: {ready_zip['name']}  ({size} B)")
        download_file(service, ready_zip["id"], dest)
        return True

    components = find_shapefile_components(files, drive_prefix)
    if not components:
        print(f"  No encontrado en Drive: {drive_prefix}.{{shp,shx,dbf,...}}")
        return False

    present_exts = {Path(f["name"]).suffix.lower() for f in components}
    missing = REQUIRED_SHAPE_PARTS - present_exts
    if missing:
        print(f"  Advertencia: faltan partes esenciales {sorted(missing)}")
    if present_exts == {".fix"}:
        print("  Advertencia: solo .fix (exportacion EE probablemente fallida).")

    zip_shapefile_components(service, components, dest)
    return True


def download_grillas(
    *,
    drive_folder: str = DEFAULT_DRIVE_FOLDER,
    output_dir: Path = DEFAULT_OUTPUT,
    prefixes: list[str] | None = None,
    overwrite: bool = False,
    force_auth: bool = False,
) -> int:
    service = get_drive_service(force_auth=force_auth)
    folder_id = find_folder_id(service, drive_folder)
    print(f"Carpeta Drive: {drive_folder}  (id={folder_id})")
    print(f"Destino local: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    prefixes = prefixes or SCALE300_PREFIXES
    ok = 0
    for prefix in prefixes:
        print(f"\n-- {prefix}")
        if download_prefix(service, folder_id, prefix, output_dir, overwrite=overwrite):
            ok += 1

    print(f"\nDescargados: {ok}/{len(prefixes)}")
    return 0 if ok == len(prefixes) else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Descarga grillas GEE desde Google Drive.")
    p.add_argument("--drive-folder", default=DEFAULT_DRIVE_FOLDER)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--prefix", action="append", dest="prefixes",
                   help="Prefijo de archivo a descargar (repetible).")
    p.add_argument("--scale300-all", action="store_true",
                   help="Descarga las 4 grillas scale300 por defecto.")
    p.add_argument("--overwrite", action="store_true",
                   help="Sobrescribir archivos locales existentes.")
    p.add_argument("--authenticate", action="store_true",
                   help="Re-autorizar acceso a Drive.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    prefixes = args.prefixes
    if args.scale300_all:
        prefixes = SCALE300_PREFIXES
    return download_grillas(
        drive_folder=args.drive_folder,
        output_dir=args.output_dir,
        prefixes=prefixes,
        overwrite=args.overwrite,
        force_auth=args.authenticate,
    )


if __name__ == "__main__":
    sys.exit(main())
