#!/usr/bin/env python3
"""
Segmentación SLIC (s=50, σ=0.1) + RAG p10 sobre rectángulos del plan de revisión.

Entradas: GPKG nacional con rev_year1/2/3 (EPSG:4326) y mosaicos CIM 184F-HARM
enmascarados (agua/glaciar). Máscara espacial adicional de ecorregiones.

Salidas por (grid_id, año):
  - labels.tif (segment_id INT)
  - segments.gpkg (vía caracterización; geometría 4326)
  - features.parquet (opcional)
  - summary.json

No reescribe el algoritmo SLIC+RAG. No modifica 04_labeling.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from skimage.measure import label as cc_label
from skimage.segmentation import slic

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from config.bands_184b import SEGMENTATION_BANDS, SIGNATURE_BANDS  # noqa: F401 — default import
from config.mosaic_presets import (
    cargar_bandas_layout,
    resolve_anios_permitidos,
    resolve_band_layout,
    resolve_features_parquet,
    resolve_mosaic_root,
)
from config.run_refs import GPKG_SELECCION, GPKG_UTM18, GPKG_UTM19, RASTER_ECORREGIONES
from config.params_slic import (
    BUFFER_PX,
    RAG_PERCENTILE,
    SLIC_COMPACTNESS,
    SLIC_SCALE,
    SLIC_SIGMA,
)
from config.paths import mosaic_root, output_dir, masked_mosaic_path
from mosaic_io import (
    leer_bandas_recorte as _leer_bandas,
    leer_ventana_ampliada as _leer_ventana_ampliada,
    recortar_centro as _recortar_centro,
    ventana_con_buffer,
    ventana_rectangulo,
)
from ecoregion_mask import mascara_ecorregion_en_ventana
from rag import fusionar_rag_threshold
from rectangles import (
    construir_plan,
    filtrar_plan,
    guardar_plan,
    iterar_filas_plan,
    utm_epsg_desde_fila,
)

# === FUENTE DE SELECCIÓN (un solo archivo nacional, EPSG:4326) ===
GPKG_SELECCION_DEFAULT = GPKG_SELECCION
COLUMNAS_REV_YEAR = ["rev_year1", "rev_year2", "rev_year3"]
COLUMNAS_REV_ROLE = ["rev_role1", "rev_role2", "rev_role3"]

# === MÁSCARA ESPACIAL (evitar océano) ===
RASTER_ECORREGIONES_DEFAULT = RASTER_ECORREGIONES

# === IDENTIFICACIÓN ===
PLANTILLA_UID = "{grid_id}_{rev_year}_{label:06d}"


def cargar_bandas(
    layout: str = "184",
) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """Bandas de segmentación y de firma espectral según layout (184|11b)."""
    return cargar_bandas_layout(layout)


def _mosaico_o_error(mosaic_root_dir: Path, tile: str, year: int) -> Path:
    path = masked_mosaic_path(mosaic_root_dir, tile, year)
    if path is None or not path.is_file():
        raise FileNotFoundError(
            f"Sin mosaico para tile {tile} year={year} en {mosaic_root_dir}"
        )
    return path


def _reetiquetar_componentes_conexas(labels: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Asigna un segment_id único por componente conexa dentro de cada etiqueta SLIC/RAG."""
    out = np.zeros_like(labels, dtype=np.int32)
    fg = (labels > 0) & valid
    if not fg.any():
        return out
    next_id = 1
    for seg_id in np.unique(labels[fg]):
        mask_seg = (labels == seg_id) & fg
        cc = cc_label(mask_seg, connectivity=2)
        cc_pos = cc > 0
        if not cc_pos.any():
            continue
        cc[cc_pos] += next_id - 1
        out[mask_seg] = cc[mask_seg]
        next_id = int(out.max()) + 1
    return out


def _finalizar_recorte_rectangulo(
    labels_buf: np.ndarray,
    valid_buf: np.ndarray,
    buffer_effective: dict[str, int],
    geom,
    transform_rect: rasterio.Affine,
) -> tuple[np.ndarray, np.ndarray]:
    """Recorta el buffer, aplica máscara geométrica y reetiqueta componentes conexas."""
    labels = _recortar_centro(labels_buf, buffer_effective)
    valid = _recortar_centro(valid_buf.astype(np.int8), buffer_effective).astype(bool)
    inside = geometry_mask(
        [geom],
        out_shape=labels.shape[:2],
        transform=transform_rect,
        invert=True,
    )
    valid &= inside
    labels[~valid] = 0
    return _reetiquetar_componentes_conexas(labels, valid), valid


def _preparar_imagen_slic(feats: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Rellena píxeles inválidos con la mediana por banda antes de SLIC."""
    out_arr = feats.astype(np.float32, copy=True)
    for c in range(out_arr.shape[-1]):
        band = out_arr[..., c]
        median = float(np.median(band[valid])) if np.any(valid) else 0.0
        band[~valid] = median
        out_arr[..., c] = band
    return out_arr


def ejecutar_slic(feats: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Ejecuta SLIC y pone a 0 las etiquetas fuera de la máscara válida."""
    n_valid = int(valid.sum())
    n_segments = max(2, n_valid // SLIC_SCALE)
    img = _preparar_imagen_slic(feats, valid)
    labels = slic(
        img,
        n_segments=n_segments,
        compactness=SLIC_COMPACTNESS,
        sigma=SLIC_SIGMA,
        channel_axis=-1,
        enforce_connectivity=True,
        start_label=1,
    ).astype(np.int32)
    labels[~valid] = 0
    return labels


def procesar_rectangulo(
    row: pd.Series,
    mosaic_root_dir: Path,
    year: int,
    out_dir: Path,
    seg_bands: list[tuple[str, int]],
    sig_bands: list[tuple[str, int]],
    buffer_px: int = BUFFER_PX,
    *,
    caracterizar: bool = True,
    ruta_ecorregiones: Path = RASTER_ECORREGIONES_DEFAULT,
    generar_features_parquet: bool = True,
) -> dict:
    """Segmenta un rectángulo (SLIC+RAG), escribe raster/summary y opcionalmente caracteriza."""
    grid_id = row["grid_id"]
    tile = row["_tile"]
    rev_year = int(row.get("rev_year", row.get("rev_year1", year)))
    rev_slot = int(row.get("rev_slot", 1) or 1)
    rev_role = str(row.get("rev_role", row.get("rev_role1", "")) or "")
    mosaic_path = _mosaico_o_error(mosaic_root_dir, tile, year)
    utm_epsg = utm_epsg_desde_fila(row)

    idx_seg = [i for _, i in seg_bands]
    idx_firma = [i for _, i in sig_bands]
    sig_names = [n for n, _ in sig_bands]
    idx_all = sorted(set(idx_seg + idx_firma))

    rect_dir = out_dir / tile / grid_id
    rect_dir.mkdir(parents=True, exist_ok=True)

    ocean_masked_frac = 0.0

    with rasterio.open(mosaic_path) as src:
        if buffer_px > 0:
            feats_buf, valid_buf, _, buffer_effective, transform_rect = _leer_ventana_ampliada(
                src, row.geometry, idx_seg, buffer_px
            )
            stack_all_buf, valid2_buf, _, _, _ = _leer_ventana_ampliada(
                src, row.geometry, idx_all, buffer_px
            )
            valid_buf &= valid2_buf

            # Máscara ecorregión sobre la ventana con buffer (antes de SLIC)
            win_rect = ventana_rectangulo(src, row.geometry)
            win_buf, _ = ventana_con_buffer(win_rect, buffer_px, src.width, src.height)
            transform_buf = src.window_transform(win_buf)
            eco_ok, ocean_masked_frac = mascara_ecorregion_en_ventana(
                ruta_ecorregiones,
                transform=transform_buf,
                crs=src.crs,
                height=feats_buf.shape[0],
                width=feats_buf.shape[1],
            )
            valid_buf &= eco_ok

            labels_slic_buf = ejecutar_slic(feats_buf, valid_buf)
            labels_buf, rag_stats = fusionar_rag_threshold(
                labels_slic_buf, feats_buf, valid_buf, RAG_PERCENTILE
            )
            labels, valid = _finalizar_recorte_rectangulo(
                labels_buf, valid_buf, buffer_effective, row.geometry, transform_rect
            )
            meta = {
                "transform": transform_rect,
                "width": labels.shape[1],
                "height": labels.shape[0],
                "crs": src.crs.to_string(),
            }
        else:
            feats_seg, valid, meta = _leer_bandas(src, row.geometry, idx_seg)
            stack_all, valid2, _ = _leer_bandas(src, row.geometry, idx_all)
            valid = valid & valid2
            eco_ok, ocean_masked_frac = mascara_ecorregion_en_ventana(
                ruta_ecorregiones,
                transform=meta["transform"],
                crs=src.crs,
                height=meta["height"],
                width=meta["width"],
            )
            valid &= eco_ok
            labels_slic = ejecutar_slic(feats_seg, valid)
            labels, rag_stats = fusionar_rag_threshold(
                labels_slic, feats_seg, valid, RAG_PERCENTILE
            )
            buffer_effective = {"left": 0, "right": 0, "top": 0, "bottom": 0}

    if valid.sum() < SLIC_SCALE:
        raise ValueError(f"{grid_id}: píxeles válidos insuficientes ({int(valid.sum())})")

    label_path = (
        rect_dir / f"{grid_id}_{year}_slic_ragp10_s{SLIC_SCALE}_sig{SLIC_SIGMA:.1f}_labels.tif"
    )
    profile = {
        "driver": "GTiff",
        "dtype": "int32",
        "count": 1,
        "width": meta["width"],
        "height": meta["height"],
        "crs": meta["crs"],
        "transform": meta["transform"],
        "nodata": 0,
        "compress": "deflate",
    }
    out_labels = labels.copy()
    out_labels[~valid] = 0
    with rasterio.open(label_path, "w", **profile) as dst:
        dst.write(out_labels, 1)

    # ejecutar_slic ya no escribe segments.gpkg (único GPKG lo genera caracterizar)
    summary = {
        "grid_id": grid_id,
        "tile": tile,
        "rev_year": rev_year,
        "rev_slot": rev_slot,
        "rev_role": rev_role,
        "rev_year1": rev_year,
        "rev_role1": rev_role,
        "utm_epsg": utm_epsg,
        "utm_zone": int(str(utm_epsg)[-2:]) if utm_epsg else None,
        "mosaic_path": str(mosaic_path),
        "n_pixels_valid": int(valid.sum()),
        "ocean_masked_frac": round(float(ocean_masked_frac), 6),
        "n_segments": int(len(np.unique(labels[labels > 0]))),
        "n_segments_slic": rag_stats["n_segments_slic"],
        "n_segments_rag": rag_stats["n_segments_rag"],
        "rag_percentil": rag_stats["rag_percentil"],
        "rag_threshold": rag_stats["rag_threshold"],
        "rag_reduction_pct": rag_stats["rag_reduction_pct"],
        "slic_scale": SLIC_SCALE,
        "slic_sigma": SLIC_SIGMA,
        "buffer_px": buffer_px,
        "buffer_effective_px": buffer_effective,
        "rag_mode": "threshold",
        "bands_segmentation": [n for n, _ in seg_bands],
        "bands_signature": sig_names,
        "label_raster": str(label_path),
        "segments_gpkg": None,
        "features_parquet": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if caracterizar:
        from characterize_segments import caracterizar_rectangulo, leer_stack_rectangulo

        stack_full, _, nombres_bandas = leer_stack_rectangulo(
            mosaic_path,
            row.geometry,
            buffer_px=buffer_px,
            buffer_efectivo=buffer_effective,
        )
        # Aplicar misma máscara valid a caracterización (ya recortada)
        if stack_full.shape[:2] != labels.shape:
            raise ValueError(
                f"Stack {stack_full.shape[:2]} != labels {labels.shape} en {grid_id}"
            )
        params_seg = {
            "slic_scale": SLIC_SCALE,
            "slic_sigma": SLIC_SIGMA,
            "slic_compactness": SLIC_COMPACTNESS,
            "rag_percentil": RAG_PERCENTILE,
            "buffer_px": buffer_px,
        }
        # Asegurar metadatos en la fila para el GPKG
        fila = row.copy()
        fila["rev_year"] = rev_year
        fila["rev_slot"] = rev_slot
        fila["rev_role"] = rev_role
        fila["utm_epsg"] = utm_epsg
        if "rect_id" not in fila.index or pd.isna(fila.get("rect_id")):
            fila["rect_id"] = grid_id

        caract = caracterizar_rectangulo(
            etiquetas=labels,
            valido=valid,
            stack=stack_full,
            nombres_bandas=nombres_bandas,
            transform=meta["transform"],
            crs=meta["crs"],
            fila=fila,
            params_segmentacion=params_seg,
            dir_corrida=rect_dir,
            dir_salida_base=out_dir,
            generar_features_parquet=generar_features_parquet,
        )
        summary["segments_gpkg"] = caract.get("segments_gpkg")
        summary["features_parquet"] = caract.get("features_parquet")
        summary["n_segments"] = caract.get("n_segmentos", summary["n_segments"])
        summary["caracterizacion"] = caract
        if "slots_extra" in row.index or "_slots" in row.index:
            summary["slots_extra"] = list(row.get("_slots") or [])

    summary_path = rect_dir / f"{grid_id}_{year}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def parsear_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="SLIC s50 σ0.1 + RAG p10 sobre rectángulos del plan de revisión."
    )
    p.add_argument(
        "--gpkg-seleccion",
        type=Path,
        default=GPKG_SELECCION_DEFAULT,
        help="GPKG nacional de selección (EPSG:4326)",
    )
    p.add_argument("--gpkg-utm18", type=Path, default=GPKG_UTM18, help="GPKG huso 18 (fallback)")
    p.add_argument("--gpkg-utm19", type=Path, default=GPKG_UTM19, help="GPKG huso 19 (fallback)")
    p.add_argument("--rev-year", type=int, default=2015, help="Año de revisión a procesar")
    p.add_argument(
        "--year",
        type=int,
        default=None,
        help="Año del mosaico (default: igual a --rev-year)",
    )
    p.add_argument(
        "--mosaic-kind",
        type=str,
        default=None,
        help="Preset de mosaico: 184_mask_water | 11b (env MOSAIC_KIND)",
    )
    p.add_argument(
        "--mosaic-root",
        type=Path,
        default=None,
        help="Raíz de mosaicos (env MOSAIC_ROOT; tiene prioridad sobre --mosaic-kind)",
    )
    p.add_argument(
        "--band-layout",
        type=str,
        default=None,
        help="Layout de bandas: auto | 184 | 11b (env BAND_LAYOUT)",
    )
    p.add_argument("--output-dir", type=Path, default=None, help="Directorio de salida de segmentación")
    p.add_argument(
        "--slic-scale",
        type=int,
        default=None,
        help="Escala SLIC (n_píxeles / n_segmentos). Default: SLIC_SCALE del config (50). "
        "También se puede fijar con env SLIC_SCALE.",
    )
    p.add_argument(
        "--ecorregiones",
        type=Path,
        default=RASTER_ECORREGIONES_DEFAULT,
        help="Raster de ecorregiones para máscara océano",
    )
    p.add_argument("--test-tile", type=str, default=None, help="Procesar solo un tile")
    p.add_argument("--grid-id", type=str, default=None, help="Procesar solo un grid_id")
    p.add_argument(
        "--require-mosaic",
        action="store_true",
        help="Excluir rectángulos cuyo tile no tenga mosaico enmascarado",
    )
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="Omitir rectángulos que ya tienen summary.json",
    )
    p.add_argument("--force", action="store_true", help="Forzar reproceso (anula --skip-existing)")
    p.add_argument("--dry-run", action="store_true", help="Solo planifica; no segmenta")
    p.add_argument("--limit", type=int, default=None, help="Máximo de rectángulos a procesar")
    p.add_argument("--export-plan", type=Path, default=None, help="Ruta para exportar el plan JSON")
    p.add_argument("--buffer-px", type=int, default=BUFFER_PX, help="Buffer en píxeles alrededor del rectángulo")
    p.add_argument(
        "--no-characterize",
        "--sin-caracterizar",
        action="store_true",
        dest="no_characterize",
        help="No ejecutar caracterización zonal post-SLIC",
    )
    p.add_argument(
        "--features-parquet",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Generar features.parquet. Default: ON para 184_mask_water, "
        "OFF (pendiente) para 11b. Override con --features-parquet / "
        "--no-features-parquet o env FEATURES_PARQUET=0|1.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    global SLIC_SCALE
    args = parsear_args(argv)
    env_scale = os.environ.get("SLIC_SCALE")
    if args.slic_scale is not None:
        SLIC_SCALE = int(args.slic_scale)
    elif env_scale is not None and env_scale.strip() != "":
        SLIC_SCALE = int(env_scale)
    import config.params_slic as _params_slic

    _params_slic.SLIC_SCALE = SLIC_SCALE
    year = args.year if args.year is not None else args.rev_year
    mroot, mosaic_kind = resolve_mosaic_root(
        mosaic_root=args.mosaic_root,
        mosaic_kind=args.mosaic_kind,
        year=year,
    )
    out = args.output_dir or output_dir(args.rev_year)
    skip_existing = args.skip_existing and not args.force
    do_parquet = resolve_features_parquet(
        features_parquet=args.features_parquet,
        mosaic_kind=mosaic_kind,
    )
    anios = resolve_anios_permitidos(mosaic_kind=mosaic_kind)
    layout = resolve_band_layout(band_layout=args.band_layout, mosaic_kind=mosaic_kind)

    plan = construir_plan(
        rev_year=args.rev_year,
        year=year,
        mosaic_root_dir=mroot,
        output_root=out,
        gpkg_utm18=args.gpkg_utm18,
        gpkg_utm19=args.gpkg_utm19,
        test_tile=args.test_tile,
        grid_id=args.grid_id,
        gpkg_seleccion=args.gpkg_seleccion,
        anios_permitidos=anios,
    )

    res = plan.summary()
    to_process = filtrar_plan(
        plan,
        require_mosaic=args.require_mosaic,
        skip_existing=skip_existing,
    )
    print(f"Plan rev_year={args.rev_year} · mosaico year={year}")
    print(f"  mosaic_kind={mosaic_kind} · band_layout={layout} · features_parquet={do_parquet}")
    print(f"  mosaic_root={mroot}")
    print(
        f"  Total: {res['n_total']} · mosaico OK: {res['n_mosaic_ok']} · "
        f"ya hechos: {res['n_already_processed']} · a procesar: {len(to_process)}"
    )
    if res["tiles_missing_mosaic"]:
        print(f"  Tiles sin mosaico: {', '.join(res['tiles_missing_mosaic'])}")

    plan_path = args.export_plan or (out / f"plan_rev{args.rev_year}.json")
    guardar_plan(plan, plan_path)
    print(f"  Plan → {plan_path}")

    if args.dry_run:
        print("Dry-run: no se segmenta.")
        return 0

    if args.limit is not None:
        to_process = to_process[: args.limit]

    if not to_process:
        print("Nada que procesar.")
        return 0

    seg_bands, sig_bands = cargar_bandas(layout)
    ids = {r.grid_id for r in to_process}
    groups = iterar_filas_plan(plan, gpkg_seleccion=args.gpkg_seleccion)
    groups = [gdf[gdf["grid_id"].isin(ids)] for gdf in groups]
    groups = [g for g in groups if not g.empty]

    out.mkdir(parents=True, exist_ok=True)
    print(f"Segmentando {sum(len(g) for g in groups)} rectángulo(s)…")

    results = []
    errors = []
    skipped = res["n_already_processed"] if skip_existing else 0
    for gdf in groups:
        for _, row in gdf.iterrows():
            gid = row["grid_id"]
            try:
                print(
                    f"  → {gid} (tile {row['_tile']}, utm_epsg={utm_epsg_desde_fila(row)})…",
                    flush=True,
                )
                # Auto-adjust layout from concrete mosaic filename if needed
                mosaic_path = masked_mosaic_path(mroot, str(row["_tile"]), year)
                layout_i = resolve_band_layout(
                    band_layout=args.band_layout,
                    mosaic_kind=mosaic_kind,
                    mosaic_path=mosaic_path,
                )
                if layout_i != layout:
                    seg_i, sig_i = cargar_bandas(layout_i)
                else:
                    seg_i, sig_i = seg_bands, sig_bands
                rect_result = procesar_rectangulo(
                    row,
                    mroot,
                    year,
                    out,
                    seg_i,
                    sig_i,
                    buffer_px=args.buffer_px,
                    caracterizar=not args.no_characterize,
                    ruta_ecorregiones=args.ecorregiones,
                    generar_features_parquet=do_parquet,
                )
                print(
                    f"     OK: {rect_result['n_segments']} segmentos · "
                    f"ocean_frac={rect_result.get('ocean_masked_frac')} · "
                    f"utm={rect_result.get('utm_epsg')}",
                    flush=True,
                )
                results.append(rect_result)
            except Exception as exc:
                print(f"     ERROR: {exc}", flush=True)
                errors.append({"grid_id": gid, "error": str(exc)})

    run_summary = {
        "rev_year": args.rev_year,
        "year": year,
        "mosaic_kind": mosaic_kind,
        "band_layout": layout,
        "features_parquet": do_parquet,
        "n_ok": len(results),
        "n_error": len(errors),
        "n_skipped_existing": skipped,
        "mosaic_root": str(mroot),
        "output_dir": str(out),
        "gpkg_seleccion": str(args.gpkg_seleccion),
        "plan_path": str(plan_path),
        "require_mosaic": args.require_mosaic,
        "skip_existing": skip_existing,
        "results": results,
        "errors": errors,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    run_path = out / f"run_summary_rev{args.rev_year}.json"
    run_path.write_text(json.dumps(run_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"\nResumen: {len(results)} OK · {len(errors)} errores · "
        f"{skipped} omitidos → {run_path}"
    )
    return 1 if errors else 0


# Aliases ingleses (compatibilidad de imports internos)
load_bands = cargar_bandas
_mosaic_or_raise = _mosaico_o_error
_relabel_connected_components = _reetiquetar_componentes_conexas
_finalize_rectangle_crop = _finalizar_recorte_rectangulo
_prepare_slic_image = _preparar_imagen_slic
run_slic = ejecutar_slic
process_rectangle = procesar_rectangulo
parse_args = parsear_args


if __name__ == "__main__":
    raise SystemExit(main())
