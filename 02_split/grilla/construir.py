"""Construcción de la grilla de celdas sobre las cartas CIM 1:250.000.

Todo ocurre en EPSG:4326. La celda son celda_px x celda_px píxeles de la grilla
nativa del ráster de landcover.

Cada carta se subdivide de forma independiente, arrancando en su esquina
noroeste y avanzando hacia el este y hacia el sur. Ninguna celda cruza a la
carta vecina: la última columna al este y la última fila al sur se descartan si
no caben completas.
"""

from __future__ import annotations

import math

import geopandas as gpd
import pandas as pd
import rasterio
from shapely.geometry import box

import geodesia
from config import params_grilla as P

TOL = 1e-9  # tolerancia en grados para comparaciones de coma flotante


def malla_referencia() -> dict:
    """Resolución, origen y extensión del ráster que define la grilla de píxeles."""
    ruta = P.LULC_DIR / P.LULC_PATRON.format(year=P.LULC_ANIO_REF)
    if not ruta.is_file():
        raise FileNotFoundError(f"Ráster de referencia no encontrado: {ruta}")
    with rasterio.open(ruta) as src:
        if src.crs is None or src.crs.to_epsg() != 4326:
            raise ValueError(f"El ráster de referencia debe estar en EPSG:4326, está en {src.crs}")
        res_x, res_y = src.res
        if abs(res_x - res_y) > 1e-12:
            raise ValueError(f"Píxel no cuadrado en {ruta}: {src.res}")
        return {
            "ruta": str(ruta),
            "res": float(res_x),
            "lon_origen": float(src.bounds.left),
            "lat_origen": float(src.bounds.top),
            "bounds": tuple(float(v) for v in src.bounds),
            "width": int(src.width),
            "height": int(src.height),
        }


def lado_deg(celda_px: int, ref: dict) -> float:
    return celda_px * ref["res"]


def zona_cim(nombre: str) -> int:
    """Segundo campo del nombre de la carta (p.ej. SI-18-Z-B -> 18), informativo."""
    partes = str(nombre).split("-")
    if len(partes) < 2 or not partes[1].isdigit():
        raise ValueError(f"Nombre de carta CIM no reconocido: {nombre!r}")
    return int(partes[1])


def cargar_cartas_cim(solo_con_datos: bool | None = None) -> gpd.GeoDataFrame:
    """Cartas CIM en EPSG:4326."""
    if not P.CIM_VECTOR.is_file():
        raise FileNotFoundError(f"Vector CIM no encontrado: {P.CIM_VECTOR}")
    gdf = gpd.read_file(P.CIM_VECTOR)
    if P.CIM_CAMPO_NOMBRE not in gdf.columns:
        raise ValueError(
            f"Campo {P.CIM_CAMPO_NOMBRE!r} ausente en {P.CIM_VECTOR}. "
            f"Columnas: {list(gdf.columns)}"
        )
    gdf = gdf.rename(columns={P.CIM_CAMPO_NOMBRE: "cim_name"})[["cim_name", "geometry"]]
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    gdf["cim_zona"] = gdf["cim_name"].map(zona_cim)

    solo = P.SOLO_CARTAS_CON_DATOS if solo_con_datos is None else solo_con_datos
    if solo:
        ext = box(*malla_referencia()["bounds"])
        gdf = gdf[gdf.geometry.intersects(ext)]
    return gdf.sort_values("cim_name").reset_index(drop=True)


def ancla_carta(carta_geom, ref: dict) -> tuple[int, int]:
    """Índices de píxel de la esquina noroeste desde donde arranca la carta.

    Con snap se corre al primer borde de píxel que queda DENTRO de la carta, para
    que ninguna celda se salga por el norte ni por el oeste.
    """
    res = ref["res"]
    lon_w, _, _, lat_n = carta_geom.bounds
    col = (lon_w - ref["lon_origen"]) / res
    fil = (ref["lat_origen"] - lat_n) / res
    if P.SNAP_A_PIXEL:
        return math.ceil(col - TOL), math.ceil(fil - TOL)
    return round(col), round(fil)


def celda_geom(px_col: int, px_row: int, celda_px: int, ref: dict):
    """Geometría de la celda que arranca en el píxel (px_col, px_row)."""
    res = ref["res"]
    olon, olat = ref["lon_origen"], ref["lat_origen"]
    return box(
        olon + px_col * res,
        olat - (px_row + celda_px) * res,
        olon + (px_col + celda_px) * res,
        olat - px_row * res,
    )


def _dims_km(lat_norte: float, celda_px: int, ref: dict) -> tuple[float, float, float]:
    """Ancho y alto en km medidos por el centro de la celda, y área exacta en km2."""
    ancho, alto = geodesia.ancho_alto_m(lat_norte, ref["res"], celda_px)
    area = geodesia.area_celda_m2(lat_norte, ref["res"], celda_px)
    return ancho / 1000, alto / 1000, area / 1e6


def construir_celdas_carta(
    carta_geom, cim_name: str, cim_zona: int, celda_px: int, ref: dict
) -> list[dict]:
    """Celdas de una carta: desde su esquina noroeste, sin salirse de la carta."""
    lado = lado_deg(celda_px, ref)
    col0, fil0 = ancla_carta(carta_geom, ref)
    _, lat_s, lon_e, _ = carta_geom.bounds
    lon_ancla = ref["lon_origen"] + col0 * ref["res"]
    lat_ancla = ref["lat_origen"] - fil0 * ref["res"]

    n_cols = int(math.floor((lon_e - lon_ancla) / lado + TOL))
    n_filas = int(math.floor((lat_ancla - lat_s) / lado + TOL))

    filas: list[dict] = []
    for ri in range(max(0, n_filas)):
        for ci in range(max(0, n_cols)):
            px_col = col0 + ci * celda_px
            px_row = fil0 + ri * celda_px
            celda = celda_geom(px_col, px_row, celda_px, ref)

            # Garantía dura: la celda no puede asomarse a la carta vecina
            if celda.intersection(carta_geom).area / celda.area < 1 - 1e-9:
                continue

            b = celda.bounds
            ancho_km, alto_km, area_km2 = _dims_km(b[3], celda_px, ref)
            filas.append(
                {
                    "grid_id": f"{cim_name}_{P.etiqueta(celda_px)}_c{ci:03d}_r{ri:03d}",
                    "cim_name": cim_name,
                    "cim_zona": cim_zona,
                    "celda_px": celda_px,
                    "n_chips": celda_px // P.CHIP_PX,
                    "lado_deg": lado,
                    # Ventana exacta en píxeles del ráster de referencia
                    "px_col_off": px_col,
                    "px_row_off": px_row,
                    "col_idx": ci,
                    "row_idx": ri,
                    "lon_min": b[0],
                    "lat_min": b[1],
                    "lon_max": b[2],
                    "lat_max": b[3],
                    "lon_centro": (b[0] + b[2]) / 2,
                    "lat_centro": (b[1] + b[3]) / 2,
                    "ancho_km": round(ancho_km, 4),
                    "alto_km": round(alto_km, 4),
                    "razon_ancho_alto": round(ancho_km / alto_km, 4),
                    "area_km2": round(area_km2, 4),
                    "area_ha": round(area_km2 * 100, 2),
                    "geometry": celda,
                }
            )
    return filas


def construir_grilla(celda_px: int) -> tuple[gpd.GeoDataFrame, dict]:
    """Grilla completa de un tamaño de celda, en EPSG:4326."""
    ref = malla_referencia()
    cartas = cargar_cartas_cim()

    filas: list[dict] = []
    for row in cartas.itertuples():
        filas += construir_celdas_carta(
            row.geometry, row.cim_name, int(row.cim_zona), celda_px, ref
        )
    if not filas:
        raise RuntimeError(f"No se generaron celdas para celda_px={celda_px}")

    df = pd.DataFrame(filas)
    gdf = gpd.GeoDataFrame(
        df.drop(columns=["geometry"]), geometry=df["geometry"], crs="EPSG:4326"
    )
    return gdf.sort_values(["cim_name", "row_idx", "col_idx"]).reset_index(drop=True), ref


def cargar_grilla(celda_px: int, cim_name: str | None = None) -> gpd.GeoDataFrame:
    """Lee la grilla ya generada desde su GeoPackage."""
    ruta = P.gpkg(celda_px)
    if not ruta.is_file():
        raise FileNotFoundError(
            f"Grilla no encontrada: {ruta}. Ejecute scripts/01_generar_grilla.py"
        )
    gdf = gpd.read_file(ruta, layer=P.capa(celda_px))
    if cim_name is not None:
        gdf = gdf[gdf["cim_name"] == cim_name].reset_index(drop=True)
    return gdf
