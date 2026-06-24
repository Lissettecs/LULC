#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd

from mb_labels.field_names import rename_geodataframe_columns

DEFAULT_EE_PROJECT = "mapbiomas-chile"
DEFAULT_GEE_ASSET_BASE = (
    "projects/mapbiomas-chile/assets/LULC/COLLECTION-03/SAMPLES/SAMPLES_COL3/SAMPLES_SSL4EO"
)
DEFAULT_GCS_BUCKET = "mapbiomas-chile"
DEFAULT_GCS_PREFIX = "image_download/SAMPLES_SSL4EO"
DIRECT_EXPORT_MAX_BYTES = 9_500_000
INGESTION_TIMEOUT_SEC = 3600


def _auth_help() -> str:
    return (
        "\nCredenciales Earth Engine no validas o expiradas:\n"
        "  bash cluster/print_gee_auth_url.sh\n"
        '  bash cluster/authenticate_gee.sh "TU_CODIGO"'
    )


def init_earth_engine(project: str | None = None, *, force_auth: bool = False) -> None:
    import ee

    project = project or DEFAULT_EE_PROJECT
    print(f"Earth Engine project: {project}")

    if force_auth:
        ee.Authenticate(auth_mode="notebook")
        ee.Initialize(project=project)
        print(f"Autenticacion OK (proyecto: {project}).")
        return

    try:
        ee.Initialize(project=project)
    except Exception as exc:
        msg = str(exc).lower()
        if "authorize" in msg or "authenticate" in msg or "invalid_grant" in msg:
            raise SystemExit(str(exc) + _auth_help()) from exc
        raise


def _sanitize_property(value: Any) -> Any:
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def prepare_gdf_for_export(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = gdf.copy()
    for col in out.columns:
        if col == "geometry":
            continue
        out[col] = out[col].map(_sanitize_property)
    return out


def rename_columns_for_gee(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Valida/ajusta nombres de columna (GeoPackage y GEE usan el mismo esquema)."""
    return rename_geodataframe_columns(gdf.copy())


def gdf_payload_bytes(gdf: gpd.GeoDataFrame) -> int:
    return len(gdf.to_json().encode("utf-8"))


def simplify_for_direct_export(
    gdf: gpd.GeoDataFrame,
    *,
    max_bytes: int = DIRECT_EXPORT_MAX_BYTES,
) -> tuple[gpd.GeoDataFrame, float | None]:
    import ee

    init_earth_engine()

    def payload_size(trial: gpd.GeoDataFrame) -> int:
        return len(json.dumps(gdf_to_feature_collection(trial).serialize()))

    trial = prepare_gdf_for_export(gdf)
    if payload_size(trial) <= max_bytes:
        return trial, None

    work = gdf.to_crs(gdf.estimate_utm_crs() or "EPSG:32719")
    for tol in (5, 10, 15, 20, 30, 50, 75, 100, 150, 200, 300):
        trial = work.copy()
        trial["geometry"] = trial.geometry.simplify(tol, preserve_topology=True)
        trial = prepare_gdf_for_export(trial.to_crs(4326))
        size = payload_size(trial)
        if size <= max_bytes:
            print(f"  Geometria simplificada a {tol} m para export directo ({size/1e6:.2f} MB).")
            return trial, float(tol)
    raise ValueError("No se pudo reducir el payload bajo 10 MB para export directo.")


def gdf_to_feature_collection(gdf: gpd.GeoDataFrame):
    import ee

    geojson = json.loads(gdf.to_json())
    features = []
    for feat in geojson.get("features", []):
        props = {
            k: _sanitize_property(v)
            for k, v in feat.get("properties", {}).items()
            if k != "geometry"
        }
        features.append(ee.Feature(ee.Geometry(feat["geometry"]), props))
    if not features:
        raise ValueError("GeoDataFrame vacio: no hay features para exportar a Earth Engine.")
    return ee.FeatureCollection(features)


def asset_exists(asset_id: str) -> bool:
    import ee

    try:
        ee.data.getAsset(asset_id)
        return True
    except ee.EEException:
        return False


def delete_asset_if_exists(asset_id: str) -> None:
    import ee

    if asset_exists(asset_id):
        print(f"  Eliminando asset existente: {asset_id}")
        ee.data.deleteAsset(asset_id)


def ensure_parent_folders(asset_id: str) -> None:
    import ee

    if "/assets/" not in asset_id:
        raise ValueError(f"Asset ID invalido: {asset_id}")
    root, rest = asset_id.split("/assets/", 1)
    prefix = f"{root}/assets"
    parts = rest.split("/")
    current = prefix
    for part in parts[:-1]:
        current = f"{current}/{part}"
        if asset_exists(current):
            continue
        print(f"  Creando carpeta GEE: {current}")
        ee.data.createAsset({"type": "FOLDER"}, current)


def _task_id_to_operation_name(task_id: str) -> str:
    import ee

    return ee._cloud_api_utils.convert_task_id_to_operation_name(  # noqa: SLF001
        ee.data._get_state().cloud_api_user_project, task_id
    )


def wait_for_ingestion_task(task_id: str, *, timeout_sec: int = INGESTION_TIMEOUT_SEC) -> None:
    import ee

    start = time.time()
    while True:
        status = ee.data.getOperation(_task_id_to_operation_name(task_id))
        state = status["metadata"]["state"]
        if status.get("done", False):
            error_message = status.get("error", {}).get("message")
            print(f"  Tarea {task_id}: {state}")
            if error_message:
                raise RuntimeError(f"Tarea GEE fallida: {error_message}")
            return
        elapsed = time.time() - start
        if elapsed > timeout_sec:
            raise TimeoutError(f"Timeout esperando tarea {task_id}")
        print(f"  Tarea {task_id}: {state} ...")
        time.sleep(15)


def wait_for_batch_task(task, poll_seconds: int = 15) -> None:
    status = task.status()
    state = status["state"]
    while state in ("READY", "RUNNING"):
        print(f"  Tarea {task.id}: {state} ...")
        time.sleep(poll_seconds)
        status = task.status()
        state = status["state"]
    if state != "COMPLETED":
        raise RuntimeError(f"Tarea GEE fallida: {status}")
    print(f"  Tarea {task.id}: COMPLETED")


def write_local_geojson(gdf: gpd.GeoDataFrame, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prepare_gdf_for_export(gdf).to_file(out_path, driver="GeoJSON")
    print(f"  GeoJSON local: {out_path}")
    return out_path


def _gcs_client(project: str):
    import google.auth.transport.requests
    from google.cloud import storage
    from google.oauth2.credentials import Credentials

    creds_path = Path.home() / ".config/earthengine/credentials"
    if not creds_path.exists():
        raise FileNotFoundError(
            f"No hay credenciales EE en {creds_path}. Ejecuta cluster/authenticate_gee.sh"
        )
    info = json.loads(creds_path.read_text(encoding="utf-8"))
    creds = Credentials(
        token=None,
        refresh_token=info["refresh_token"],
        client_id=info["client_id"],
        client_secret=info["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=info.get("scopes"),
    )
    creds.refresh(google.auth.transport.requests.Request())
    return storage.Client(project=project, credentials=creds)


def upload_file_to_gcs(
    local_path: Path,
    *,
    bucket: str,
    blob_name: str,
    project: str,
) -> str:
    client = _gcs_client(project)
    blob = client.bucket(bucket).blob(blob_name)
    print(f"  Subiendo a gs://{bucket}/{blob_name}")
    blob.upload_from_filename(str(local_path))
    return f"gs://{bucket}/{blob_name}"


def write_shapefile_zip(gdf: gpd.GeoDataFrame, out_zip: Path) -> Path:
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    staging = out_zip.with_suffix("")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    shp_path = staging / "subdivisiones.shp"
    rename_columns_for_gee(prepare_gdf_for_export(gdf)).to_file(shp_path, driver="ESRI Shapefile")
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for part in staging.glob("subdivisiones.*"):
            zf.write(part, arcname=part.name)
    shutil.rmtree(staging)
    print(f"  Shapefile zip local: {out_zip}")
    return out_zip


def export_via_gcs_ingestion(
    gdf: gpd.GeoDataFrame,
    asset_id: str,
    *,
    project: str,
    overwrite: bool,
    wait: bool,
    max_error_meters: float = 30.0,
    gcs_bucket: str = DEFAULT_GCS_BUCKET,
    gcs_prefix: str = DEFAULT_GCS_PREFIX,
) -> str:
    import ee

    local_zip = Path.home() / ".cache" / f"mb_labels_gee_upload_{uuid.uuid4().hex[:8]}.zip"
    write_shapefile_zip(gdf, local_zip)

    blob_name = f"{gcs_prefix.strip('/')}/{asset_id.split('/')[-1]}_{uuid.uuid4().hex[:8]}.zip"
    gcs_uri = upload_file_to_gcs(
        local_zip,
        bucket=gcs_bucket,
        blob_name=blob_name,
        project=project,
    )
    local_zip.unlink(missing_ok=True)

    if overwrite:
        delete_asset_if_exists(asset_id)

    ensure_parent_folders(asset_id)

    manifest = {
        "name": asset_id,
        "sources": [
            {
                "uris": [gcs_uri],
                "maxErrorMeters": max_error_meters,
            }
        ],
    }
    request_id = ee.data.newTaskId()[0]
    result = ee.data.startTableIngestion(request_id, manifest, allow_overwrite=overwrite)
    task_id = result["id"]
    print(f"  Ingestion GEE iniciada: {asset_id}")
    print(f"  Task ID: {task_id}")
    print(f"  Fuente: {gcs_uri}")
    if wait:
        wait_for_ingestion_task(task_id)
    else:
        print("  Monitoreo: https://code.earthengine.google.com/tasks")
        print("  o: earthengine task list")
    return task_id


def export_via_direct_api(
    gdf: gpd.GeoDataFrame,
    asset_id: str,
    *,
    description: str | None,
    overwrite: bool,
    wait: bool,
) -> str:
    import ee

    if overwrite:
        delete_asset_if_exists(asset_id)

    export_gdf, tol = simplify_for_direct_export(gdf)
    if tol is not None:
        print(f"  Nota: asset GEE con geometria simplificada (~{tol:.0f} m). GPKG local conserva detalle.")

    export_gdf = rename_columns_for_gee(export_gdf)
    fc = gdf_to_feature_collection(export_gdf)
    task = ee.batch.Export.table.toAsset(
        collection=fc,
        description=description or Path(asset_id).name,
        assetId=asset_id,
    )
    task.start()
    print(f"  Export GEE directo iniciado: {asset_id}")
    print(f"  Task ID: {task.id}")
    if wait:
        wait_for_batch_task(task)
    else:
        print("  Monitoreo: earthengine task list")
    return task.id


def export_gdf_to_asset(
    gdf: gpd.GeoDataFrame,
    asset_id: str,
    *,
    project: str = DEFAULT_EE_PROJECT,
    description: str | None = None,
    local_geojson: Path | None = None,
    overwrite: bool = True,
    wait: bool = False,
    force_auth: bool = False,
    upload_method: str = "auto",
    max_error_meters: float = 30.0,
    gcs_bucket: str = DEFAULT_GCS_BUCKET,
    gcs_prefix: str = DEFAULT_GCS_PREFIX,
) -> str:
    gdf = prepare_gdf_for_export(gdf)
    if local_geojson is not None:
        write_local_geojson(gdf, local_geojson)
    elif upload_method in ("auto", "gcs"):
        staging = Path.home() / ".cache" / "mb_labels_gee_upload.geojson"
        staging.parent.mkdir(parents=True, exist_ok=True)
        write_local_geojson(gdf, staging)
        local_geojson = staging

    init_earth_engine(project, force_auth=force_auth)

    payload = gdf_payload_bytes(gdf)
    use_gcs = upload_method == "gcs" or (
        upload_method == "auto" and payload > DIRECT_EXPORT_MAX_BYTES
    )
    if use_gcs:
        print(f"  Payload {payload / 1e6:.2f} MB -> ingestion via GCS (shapefile zip)")
        return export_via_gcs_ingestion(
            gdf,
            asset_id,
            project=project,
            overwrite=overwrite,
            wait=wait,
            max_error_meters=max_error_meters,
            gcs_bucket=gcs_bucket,
            gcs_prefix=gcs_prefix,
        )

    print(f"  Payload {payload / 1e6:.2f} MB -> export directo")
    return export_via_direct_api(
        gdf,
        asset_id,
        description=description,
        overwrite=overwrite,
        wait=wait,
    )


def build_asset_id(base: str, group_name: str, suffix: str) -> str:
    base = base.rstrip("/")
    return f"{base}/{group_name}/subdivisiones_C2_{suffix}"


def local_gee_path(labels_dir: Path, group_name: str, suffix: str) -> Path:
    return labels_dir / "SAMPLES_SSL4EO" / group_name / f"subdivisiones_C2_{suffix}.geojson"
