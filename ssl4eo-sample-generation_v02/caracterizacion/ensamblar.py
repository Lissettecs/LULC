"""Procesamiento de un tile y consolidación nacional (grilla UTM)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from caracterizacion.composicion import composicion_por_rectangulo, pctp_por_periodo
from caracterizacion.distorsion import factor_area_utm
from caracterizacion.espacial import metricas_espaciales
from caracterizacion.grilla import cargar_tiles_mgrs
from caracterizacion.grilla_utm import construir_grilla_utm_tile
from caracterizacion.leer_ventana import leer_stack_tile_optimizado
from caracterizacion.temporal import agregar_mascara_bloques, agregar_moda_bloques, metricas_temporales
from config import params_caracterizacion as P
from config.diccionarios import BBOX_CLASE, CLASS_NAMES
from utilidades import agregar_auditoria, unidad_completa


def procesar_tile(
    tile_name: str,
    tile_geom,
    run_dir: Path,
    logger: logging.Logger,
    rect_sides: list[int] | None = None,
) -> list[Path]:
    """Caracteriza un tile MGRS con grilla UTM; escribe parquet por tamaño."""
    rect_sides = rect_sides or P.RECT_SIDES
    huso = int(tile_name[:2])
    crs_utm = f"EPSG:{P.UTM_EPSG[huso]}"
    factor = max(1, int(round(P.STATS_SCALE / P.PIXEL_M)))
    salidas: list[Path] = []

    for side in rect_sides:
        out_path = run_dir / "por_tile" / f"{tile_name}_{side}x{side}.parquet"
        aud_path = run_dir / "auditoria_caracterizacion.csv"
        clave = f"{tile_name}_{side}x{side}"
        if unidad_completa(out_path, aud_path, clave):
            logger.info("Tile %s %dx%d ya completado — omitido", tile_name, side, side)
            if out_path.is_file():
                salidas.append(out_path)
            continue

        t0 = time.perf_counter()
        celdas = construir_grilla_utm_tile(tile_geom, tile_name, side)
        logger.info("%s %dx%d: %d celdas UTM candidatas", tile_name, side, side, len(celdas))
        if not celdas:
            _registrar_vacio(run_dir, tile_name, side, clave, crs_utm, 0, t0, logger)
            continue

        datos = leer_stack_tile_optimizado(celdas, crs_utm)
        filas: list[dict] = []
        for celda in celdas:
            stack, eco = datos[celda.grid_id]
            n_px = celda.width_px
            mascara = np.ones((n_px, n_px), dtype=bool)
            comp = composicion_por_rectangulo(stack, mascara)
            if not comp or comp.get("n_valid", 0) <= 0:
                continue
            pctp = pctp_por_periodo(stack, mascara, P.PERIODOS, P.START_YEAR)
            esp = metricas_espaciales(eco, stack, mascara)
            if not esp or "lulc_mode_id" not in esp:
                continue

            stats_30 = stack
            moda_30 = np.apply_along_axis(
                lambda row: np.bincount(row.astype(np.int64), minlength=P.MAX_CLASS_ID).argmax(),
                0,
                stats_30,
            )
            masc_valida = (moda_30 != P.CLASE_NODATA_RASTER) & (moda_30 != P.CLASE_NO_OBSERVADO)
            stats_agg = np.stack([agregar_moda_bloques(stats_30[i], factor) for i in range(stats_30.shape[0])])
            masc_stats = agregar_mascara_bloques(masc_valida, factor)
            h_s, w_s = stats_agg.shape[1], stats_agg.shape[2]
            if masc_stats.shape != (h_s, w_s):
                masc_stats = np.ones((h_s, w_s), dtype=bool)
            temp = metricas_temporales(
                stats_agg,
                masc_stats,
                P.START_YEAR,
                P.END_YEAR,
                P.UMBRAL_ANIO_ESTABLE,
                P.PERIODOS,
            )

            fa, flag_dist = factor_area_utm(celda.geometry, celda.utm_zone)
            fila = {
                **{k: v for k, v in celda.__dict__.items() if k != "geometry"},
                **comp,
                **pctp,
                **esp,
                **temp,
                "factor_area_utm": round(fa, 6),
                "flag_distorsion_borde": bool(flag_dist),
                "geometry": celda.geometry.wkt,
            }
            _bbox_campos(fila, celda.geometry, crs_utm)
            _validar_fila(fila, logger)
            filas.append(fila)

        if not filas:
            logger.warning("%s %dx%d: 0 filas tras caracterización", tile_name, side, side)
            _registrar_vacio(run_dir, tile_name, side, clave, crs_utm, len(celdas), t0, logger)
            continue

        out_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(filas).to_parquet(out_path, index=False)
        salidas.append(out_path)
        agregar_auditoria(
            run_dir,
            {
                "unidad": clave,
                "tile": tile_name,
                "rect_side": side,
                "n_rectangulos": len(filas),
                "n_celdas_utm": len(celdas),
                "tiempo_s": round(time.perf_counter() - t0, 1),
                "crs_utm": crs_utm,
                "estado": "ok",
            },
            "auditoria_caracterizacion.csv",
        )
        logger.info(
            "Tile %s %dx%d: %d rects → %s (%.1fs)",
            tile_name,
            side,
            side,
            len(filas),
            out_path.name,
            time.perf_counter() - t0,
        )
    return salidas


def _validar_fila(fila: dict, logger: logging.Logger) -> None:
    pct_cols = [k for k in fila if k.startswith("pct_") and k[4:].isdigit()]
    if "pct_0" in fila or "pct_27" in fila:
        raise ValueError(f"pct_0/pct_27 en {fila.get('grid_id')}")
    total = sum(float(fila.get(k, 0)) for k in pct_cols)
    if pct_cols and not (99.9 <= total <= 100.1):
        raise ValueError(f"Suma pct={total:.2f} en {fila.get('grid_id')}")
    epsg_raw = fila.get("utm_epsg", 0) or 0
    if isinstance(epsg_raw, str):
        epsg_raw = epsg_raw.upper().replace("EPSG:", "").strip()
    try:
        epsg = int(float(epsg_raw)) if epsg_raw not in ("", None) else 0
    except (TypeError, ValueError):
        epsg = 0
    huso = int(fila.get("utm_zone", 0) or 0)
    esperado = P.UTM_EPSG.get(huso, 0)
    if esperado and epsg and epsg != esperado:
        raise ValueError(f"CRS fila {fila.get('grid_id')}: utm_epsg={epsg} ≠ EPSG:{esperado}")


def _bbox_campos(fila: dict, geom, crs_utm: str) -> None:
    from shapely.geometry import box

    for cid, bbox in BBOX_CLASE.items():
        epsg_dest = int(fila.get("utm_zone", bbox["epsg"]))
        if epsg_dest == 18:
            epsg_dest = 32718
        elif epsg_dest == 19:
            epsg_dest = 32719
        gdf = gpd.GeoDataFrame([1], geometry=[geom], crs=crs_utm).to_crs(epsg_dest)
        bb = (
            gpd.GeoDataFrame(
                [1],
                geometry=[box(bbox["xmin"], bbox["ymin"], bbox["xmax"], bbox["ymax"])],
                crs=f"EPSG:{bbox['epsg']}",
            )
            .to_crs(epsg_dest)
            .geometry.iloc[0]
        )
        inter = gdf.geometry.iloc[0].intersects(bb)
        fila[f"en_bbox_{cid}"] = bool(inter)
        fila[f"pct_{cid}_en_bbox"] = fila.get(f"pct_{cid}", 0.0) if inter else 0.0
        fila[f"pct_{cid}_fuera_bbox"] = 0.0 if inter else fila.get(f"pct_{cid}", 0.0)


def _registrar_vacio(
    run_dir: Path,
    tile_name: str,
    side: int,
    clave: str,
    crs_utm: str,
    n_celdas: int,
    t0: float,
    logger: logging.Logger,
) -> None:
    """Marca un tile/tamaño procesado sin rectángulos válidos (océano, solo nodata, etc.)."""
    agregar_auditoria(
        run_dir,
        {
            "unidad": clave,
            "tile": tile_name,
            "rect_side": side,
            "n_rectangulos": 0,
            "n_celdas_utm": n_celdas,
            "tiempo_s": round(time.perf_counter() - t0, 1),
            "crs_utm": crs_utm,
            "estado": "vacio",
        },
        "auditoria_caracterizacion.csv",
    )
    logger.info("Tile %s %dx%d: registrado vacío (0 rects)", tile_name, side, side)


def _unidades_auditoria(run_dir: Path) -> dict[str, str]:
    path = run_dir / "auditoria_caracterizacion.csv"
    if not path.is_file():
        return {}
    aud = pd.read_csv(path)
    if "unidad" not in aud.columns:
        return {}
    estados = aud.get("estado", pd.Series("ok", index=aud.index)).astype(str)
    return dict(zip(aud["unidad"].astype(str), estados))


def _tiles_incompletos(run_dir: Path, esperados: set[str]) -> list[str]:
    """Tiles sin parquet ni registro de auditoría (ok/vacio) en todos los tamaños."""
    unidades = _unidades_auditoria(run_dir)
    incompletos: list[str] = []
    for tile in sorted(esperados):
        for side in P.RECT_SIDES:
            clave = f"{tile}_{side}x{side}"
            pq = run_dir / "por_tile" / f"{clave}.parquet"
            if pq.is_file():
                continue
            if unidades.get(clave) in ("ok", "vacio"):
                continue
            incompletos.append(tile)
            break
    return incompletos


def consolidar_grillas(run_dir: Path, logger: logging.Logger) -> list[Path]:
    """Une parciales por huso y tamaño en GeoPackage (CRS nativo por huso)."""
    por_tile = run_dir / "por_tile"
    if not por_tile.is_dir():
        raise FileNotFoundError(f"No existe {por_tile}")

    esperados = _tiles_esperados(run_dir)
    archivos = list(por_tile.glob("*.parquet"))
    incompletos = _tiles_incompletos(run_dir, esperados)
    if incompletos:
        raise FileNotFoundError(
            f"Tiles sin procesar ({len(incompletos)}): {incompletos[:20]}…"
        )
    vacios = [
        t
        for t in sorted(esperados)
        if t not in {p.stem.rsplit("_", 1)[0] for p in archivos}
    ]
    if vacios:
        logger.info(
            "Tiles vacíos (sin parquet, auditoría vacio): %d — %s",
            len(vacios),
            ", ".join(vacios[:10]) + ("…" if len(vacios) > 10 else ""),
        )

    out_dir = run_dir / "consolidado"
    out_dir.mkdir(parents=True, exist_ok=True)
    salidas: list[Path] = []

    for huso in P.HUSOS:
        epsg = P.UTM_EPSG[huso]
        tiles_huso = set(_tiles_de_huso(huso))
        for side in P.RECT_SIDES:
            partes = []
            for p in sorted(archivos):
                if not p.name.endswith(f"_{side}x{side}.parquet"):
                    continue
                tile = p.name.rsplit("_", 1)[0]
                if tile not in tiles_huso:
                    continue
                df = pd.read_parquet(p)
                if not df.empty:
                    partes.append(df)
            if not partes:
                logger.warning("Sin datos huso %s %dx%d", huso, side, side)
                continue
            df = pd.concat(partes, ignore_index=True)
            gdf = gpd.GeoDataFrame(
                df.drop(columns=["geometry"], errors="ignore"),
                geometry=gpd.GeoSeries.from_wkt(df["geometry"]),
                crs=f"EPSG:{epsg}",
            )
            if gdf.crs.to_epsg() != epsg:
                raise RuntimeError(f"CRS consolidado huso {huso} es {gdf.crs}, esperado {epsg}")
            out = out_dir / f"grilla_utm{huso}_{side}x{side}.gpkg"
            gdf.to_file(out, driver="GPKG")
            verif = gpd.read_file(out, rows=1)
            if verif.crs is None or verif.crs.to_epsg() != epsg:
                raise RuntimeError(f"CRS escrito en {out.name} incorrecto: {verif.crs}")
            logger.info("Consolidado: %s (%d filas, EPSG:%d)", out.name, len(gdf), epsg)
            salidas.append(out)
    return salidas


def _tiles_esperados(run_dir: Path) -> set[str]:
    lista = run_dir / "tiles.txt"
    if lista.is_file():
        return {ln.strip() for ln in lista.read_text().splitlines() if ln.strip()}
    gdf = cargar_tiles_mgrs(P.HUSOS)
    return set(gdf["tile_name"])


def _tiles_de_huso(huso: int) -> list[str]:
    gdf = cargar_tiles_mgrs([huso])
    return gdf["tile_name"].tolist()
