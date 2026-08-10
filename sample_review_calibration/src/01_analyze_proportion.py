#!/usr/bin/env python3
"""Fase 1 — Análisis de pureza y propuesta de cuotas (NO selecciona muestra).

La referencia del test será la clase confirmada por la supervisora, no la etiqueta C2.
Esta fase solo describe segmentos 100% puros y propone cuotas editables.
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════
# PARÁMETROS
# ═══════════════════════════════════════════════════════════════
RUTA_ENTRADA = (
    "/home/lserey/mapbiomas_land/prod/04_labeling_cim/2015/consolidado/"
    "labeled_segments_rev2015.gpkg"
)
DIR_RESULTADOS = "/home/lserey/mapbiomas_land/prod/sample_review_calibration"

PUREZA_MIN = 100.0          # con tolerancia pequeña por float
N_TOTAL_OBJETIVO = 360      # capacidad de UNA jornada de un revisor
MIN_POR_CLASE = 15          # piso duro (capa inferior antes del ±delta)
ESTRATEGIA_CUOTA = "cobertura_pm5"  # "igual"|"proporcional"|"raiz"|"piso_igual"|"cobertura_pm5"
CUOTA_DELTA = 5             # amplitud ± respecto al centro N/n_clases (cobertura_pm5)

TOL_PUREZA = 1e-6           # tolerancia al filtrar pureza == PUREZA_MIN

# Clases fuera del universo de calibración
CLASES_EXCLUIDAS = {
    33,  # Rio_lago_oceano / agua
    34,  # Glaciar
}

# Área mínima por etiqueta: percentil dentro de puros de esa clase
AREA_MIN_REGLA = "p40"      # "p40" | "median" | "mean"
AREA_MIN_PERCENTIL = 0.40   # usado si AREA_MIN_REGLA == "p40"

# Margen interior al rectángulo CIM (borde)
PIXEL_M = 30.0
BORDE_MIN_PX = 20
BORDE_MIN_M = BORDE_MIN_PX * PIXEL_M  # 600 m

# Estratificación geográfica
ESTRATIFICACION_ECO = "par_igual"  # repartir cuota de cada clase ~igual entre ecorregiones

RUTA_GRILLA_CIM_2X2 = (
    "/home/lserey/mapbiomas_land/prod/samples_cim/00_grilla/grilla_cim_2x2.gpkg"
)
RUTA_GRILLA_CIM_3X3 = (
    "/home/lserey/mapbiomas_land/prod/samples_cim/00_grilla/grilla_cim_3x3.gpkg"
)
# ═══════════════════════════════════════════════════════════════

from datetime import datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS, Transformer
from shapely.ops import transform as shp_transform

# ---------------------------------------------------------------------------
# Utilidades reutilizables (importadas por 02 y 03)
# ---------------------------------------------------------------------------

CANDIDATOS_CLASE = [
    "mode_class",
    "clase_moda",  # legacy ES
    "class_code",
    "class_id",
    "c2_class",
    "landcover_class",
    "codigo_clase",
    "class",
]
# Evitar confundir segunda clase del ranking con la moda C2
EXCLUIR_CLASE = {"clase_2", "clase_3", "class_2", "class_3"}

CANDIDATOS_NOMBRE = [
    "mode_class_name",
    "clase_moda_nombre",  # legacy ES
    "class_name",
    "nombre_clase",
    "c2_class_name",
    "landcover_name",
]
EXCLUIR_NOMBRE = {"clase_2_nombre", "clase_3_nombre", "class_2_name", "class_3_name"}

CANDIDATOS_PROPORTION = [
    "proportion",
    "pureza",  # legacy ES
    "purity",  # legacy EN
    "pureza_c2",
    "proportion_pct",
    "proportion_pct",
    "frac_moda",
]
EXCLUIR_PROPORTION = {
    "proportion_2",
    "proportion_3",
    "pureza_2",
    "pureza_3",
    "purity_2",
    "purity_3",
    "nodata_frac",
}


def crear_dir_run(base: str | Path) -> Path:
    """Crea un directorio de corrida no destructivo <YYYYMMDD_HHMMSS>/."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run = Path(base) / ts
    run.mkdir(parents=True, exist_ok=False)
    return run


def _buscar_columna(
    columnas: list[str],
    candidatos: list[str],
    excluir: set[str] | None = None,
) -> str | None:
    excluir = excluir or set()
    lower_map = {c.lower(): c for c in columnas if c.lower() not in excluir}
    for cand in candidatos:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def _candidatos_por_substring(
    columnas: list[str],
    needles: list[str],
    excluir: set[str] | None = None,
) -> list[str]:
    excluir = {e.lower() for e in (excluir or set())}
    out = []
    for c in columnas:
        cl = c.lower()
        if cl in excluir or c == "geometry":
            continue
        if any(n in cl for n in needles):
            out.append(c)
    return out


def detectar_columnas(gdf: gpd.GeoDataFrame) -> dict[str, Any]:
    """Autodetección robusta de columnas clave.

    Imprime lo detectado y el motivo. Si falta algo crítico, aborta.
    """
    cols = list(gdf.columns)
    info: dict[str, Any] = {"geometry": gdf.geometry.name}

    # --- clase C2 (código entero) ---
    col_clase = _buscar_columna(cols, CANDIDATOS_CLASE, EXCLUIR_CLASE)
    razon_clase = None
    if col_clase is not None:
        razon_clase = f"coincide con candidato conocido '{col_clase}'"
    else:
        soft = _candidatos_por_substring(
            cols, ["clase", "class", "codigo", "code"], EXCLUIR_CLASE
        )
        # Preferir numéricos
        soft_num = [
            c
            for c in soft
            if pd.api.types.is_numeric_dtype(gdf[c]) and c.lower() not in EXCLUIR_CLASE
        ]
        if len(soft_num) == 1:
            col_clase = soft_num[0]
            razon_clase = f"única columna numérica con substring de clase: '{col_clase}'"
        else:
            print("ERROR: no se detectó con confianza la columna de CÓDIGO de clase C2.")
            print(f"  Candidatos explorados: {CANDIDATOS_CLASE}")
            print(f"  Coincidencias parciales: {soft_num or soft}")
            print(f"  Columnas disponibles: {cols}")
            raise SystemExit(1)

    # --- nombre de clase ---
    col_nombre = _buscar_columna(cols, CANDIDATOS_NOMBRE, EXCLUIR_NOMBRE)
    razon_nombre = (
        f"coincide con candidato conocido '{col_nombre}'"
        if col_nombre
        else "no hay columna de nombre; se usará el código como nombre"
    )

    # --- proportion ---
    col_proportion = _buscar_columna(cols, CANDIDATOS_PROPORTION, EXCLUIR_PROPORTION)
    razon_proportion = None
    if col_proportion is not None:
        razon_proportion = f"coincide con candidato conocido '{col_proportion}'"
    else:
        soft = _candidatos_por_substring(cols, ["proportion", "pureza", "purity"], EXCLUIR_PROPORTION)
        soft_num = [c for c in soft if pd.api.types.is_numeric_dtype(gdf[c])]
        if len(soft_num) == 1:
            col_proportion = soft_num[0]
            razon_proportion = f"única columna numérica de proportion: '{col_proportion}'"
        else:
            print("ERROR: no se detectó con confianza la columna de PROPORTION.")
            print(f"  Candidatos explorados: {CANDIDATOS_PROPORTION}")
            print(f"  Coincidencias parciales: {soft_num or soft}")
            print(f"  Columnas disponibles: {cols}")
            raise SystemExit(1)

    serie_p = pd.to_numeric(gdf[col_proportion], errors="coerce")
    pmax = float(serie_p.max(skipna=True))
    if pmax <= 1.0 + 1e-9:
        proportion_encoding = "fraction"
        razon_enc = f"máximo observado={pmax:.6g} ≤ 1.0 → fracción 0–1"
    elif pmax <= 100.0 + 1e-6:
        proportion_encoding = "percent"
        razon_enc = f"máximo observado={pmax:.6g} llega a ~100 → porcentaje"
    else:
        print(
            f"ERROR: proportion con máximo={pmax:.6g} no parece fracción ni porcentaje (0–100)."
        )
        raise SystemExit(1)

    # --- claves opcionales ---
    claves = {}
    for key, cands in {
        "segment_uid": ["segment_uid", "uid"],
        "segment_id": ["segment_id", "seg_id"],
        "grid_id": ["grid_id", "rect_id"],
        "rev_year": ["rev_year", "year", "anio"],
        "utm_zone": ["utm_zone", "zone"],
        "utm_epsg": ["utm_epsg"],
    }.items():
        found = _buscar_columna(cols, cands)
        if found:
            claves[key] = found

    info.update(
        {
            "class_code": col_clase,
            "class_name": col_nombre,
            "proportion": col_proportion,
            "proportion_encoding": proportion_encoding,
            "keys": claves,
            "reasons": {
                "class_code": razon_clase,
                "class_name": razon_nombre,
                "proportion": razon_proportion,
                "proportion_encoding": razon_enc,
            },
        }
    )

    print("=== Detección de columnas ===")
    print(f"  geometría     : {info['geometry']}")
    print(f"  class_code    : {col_clase}  ({razon_clase})")
    print(f"  class_name    : {col_nombre or '(usar código)'}  ({razon_nombre})")
    print(f"  proportion   : {col_proportion}  ({razon_proportion})")
    print(f"  encoding      : {proportion_encoding}  ({razon_enc})")
    print(f"  claves        : {claves}")
    return info


def normalizar_proportion_pct(serie: pd.Series, encoding: str) -> pd.Series:
    """Normaliza proportion a porcentaje 0–100."""
    s = pd.to_numeric(serie, errors="coerce")
    if encoding == "fraction":
        return s * 100.0
    return s


def cargar_gpkg(ruta: str | Path) -> gpd.GeoDataFrame:
    """Lee el GPKG canónico (EPSG:4326) sin reproyectar."""
    print(f"Leyendo: {ruta}")
    gdf = gpd.read_file(ruta)
    print(f"  n features : {len(gdf)}")
    print(f"  CRS        : {gdf.crs}")
    print("  columnas (dtype):")
    for c in gdf.columns:
        print(f"    - {c}: {gdf[c].dtype}")
    print("  muestra (5 filas, sin geometría):")
    cols_show = [c for c in gdf.columns if c != gdf.geometry.name]
    print(gdf[cols_show].head(5).to_string())
    return gdf


def enriquecer_canonicos(gdf: gpd.GeoDataFrame, det: dict[str, Any]) -> gpd.GeoDataFrame:
    """Añade class_code, class_name, proportion_pct y claves canónicas."""
    out = gdf.copy()
    out["class_code"] = pd.to_numeric(out[det["class_code"]], errors="coerce").astype(
        "Int64"
    )
    if det["class_name"]:
        out["class_name"] = out[det["class_name"]].astype(str)
    else:
        out["class_name"] = out["class_code"].astype(str)
    out["proportion_pct"] = normalizar_proportion_pct(out[det["proportion"]], det["proportion_encoding"])
    for canon, orig in det["keys"].items():
        if canon not in out.columns:
            out[canon] = out[orig]
    return out


def filtrar_puros(
    gdf: gpd.GeoDataFrame,
    pureza_min: float = PUREZA_MIN,
    tol_pureza: float = TOL_PUREZA,
) -> gpd.GeoDataFrame:
    """Filtra a pureza ≈ pureza_min y código de clase válido."""
    mask = gdf["proportion_pct"] >= (pureza_min - tol_pureza)
    mask &= gdf["class_code"].notna() & (gdf["class_code"] != 0)
    puros = gdf.loc[mask].copy()
    print(
        f"Segmentos con pureza ≥ {pureza_min - tol_pureza:.6g}: "
        f"{len(puros)} / {len(gdf)}"
    )
    return puros


def cargar_segmentos_puros(
    ruta: str | Path,
    pureza_min: float = PUREZA_MIN,
    tol_pureza: float = TOL_PUREZA,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Lee el GPKG, detecta columnas, filtra a pureza == pureza_min (tol).

    Devuelve un GeoDataFrame con columnas canónicas en inglés añadidas:
    class_code, class_name, proportion_pct, más claves si existen.
    """
    gdf = cargar_gpkg(ruta)
    det = detectar_columnas(gdf)
    gdf = enriquecer_canonicos(gdf, det)
    puros = filtrar_puros(gdf, pureza_min, tol_pureza)
    return puros, det


def utm_epsg_desde_lonlat(lon: float, lat: float) -> int:
    """EPSG UTM derivado de longitud/latitud del centroide (hemisferio S/N)."""
    zone = int((lon + 180.0) // 6) + 1
    zone = min(max(zone, 1), 60)
    return (32700 if lat < 0 else 32600) + zone


def area_km2_utm(geom) -> float:
    """Área en km² proyectando la geometría de consulta al UTM del centroide."""
    if geom is None or geom.is_empty:
        return float("nan")
    c = geom.centroid
    epsg = utm_epsg_desde_lonlat(c.x, c.y)
    transformer = Transformer.from_crs("EPSG:4326", CRS.from_epsg(epsg), always_xy=True)
    geom_m = shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)
    return float(geom_m.area) / 1e6


def areas_km2_utm_series(geoms: gpd.GeoSeries) -> pd.Series:
    """Áreas en km² agrupando por huso UTM del centroide (copia de consulta).

    No modifica ni re-escribe el GPKG canónico (EPSG:4326).
    """
    import warnings

    if geoms.crs is None:
        geoms = geoms.set_crs("EPSG:4326")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*geographic CRS.*")
        cents = geoms.centroid  # lon/lat WGS84; solo para elegir huso UTM
    lons = cents.x.to_numpy()
    lats = cents.y.to_numpy()
    epsgs = np.array(
        [utm_epsg_desde_lonlat(float(lon), float(lat)) for lon, lat in zip(lons, lats)],
        dtype=int,
    )
    out = np.full(len(geoms), np.nan, dtype=float)
    # Trabajar sobre índice posicional 0..n-1
    gserie = geoms.reset_index(drop=True)
    for epsg in sorted(set(epsgs.tolist())):
        idx = np.where(epsgs == epsg)[0]
        sub = gserie.iloc[idx]
        areas_m2 = sub.to_crs(epsg=int(epsg)).area.to_numpy(dtype=float)
        out[idx] = areas_m2 / 1e6
    return pd.Series(out, index=geoms.index)


def cargar_celdas_cim(
    ruta_2x2: str | Path = RUTA_GRILLA_CIM_2X2,
    ruta_3x3: str | Path = RUTA_GRILLA_CIM_3X3,
) -> gpd.GeoDataFrame:
    """Carga grillas CIM 2x2 y 3x3 y unifica por grid_id."""
    g2 = gpd.read_file(ruta_2x2)[["grid_id", "geometry"]]
    g3 = gpd.read_file(ruta_3x3)[["grid_id", "geometry"]]
    cells = pd.concat([g2, g3], ignore_index=True)
    cells["grid_id"] = cells["grid_id"].astype(str)
    cells = gpd.GeoDataFrame(cells, geometry="geometry", crs=g2.crs)
    return cells.drop_duplicates("grid_id")


def distancias_a_borde_cim_m(
    gdf: gpd.GeoDataFrame,
    cells: gpd.GeoDataFrame | None = None,
) -> pd.Series:
    """Distancia (m) de cada geometría al borde de su celda CIM (grid_id).

    Usa UTM de utm_epsg (o del centroide) sobre copias de consulta.
    """
    import warnings

    if "grid_id" not in gdf.columns:
        raise ValueError("Se requiere columna grid_id para distancia al borde CIM")
    if cells is None:
        cells = cargar_celdas_cim()
    cell_geom = cells.set_index("grid_id")["geometry"]

    out = np.full(len(gdf), np.nan, dtype=float)
    work = gdf.reset_index(drop=True)
    if work.crs is None:
        work = work.set_crs("EPSG:4326")

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*geographic CRS.*")
        for gid, idx in work.groupby(work["grid_id"].astype(str)).groups.items():
            if gid not in cell_geom.index:
                continue
            cell = cell_geom.loc[gid]
            if isinstance(cell, gpd.GeoSeries):
                cell = cell.iloc[0]
            idx = list(idx)
            sub = work.loc[idx]
            if "utm_epsg" in sub.columns and sub["utm_epsg"].notna().all():
                epsg_vals = sub["utm_epsg"].astype(int)
            else:
                cents = sub.geometry.centroid
                epsg_vals = pd.Series(
                    [
                        utm_epsg_desde_lonlat(float(x), float(y))
                        for x, y in zip(cents.x, cents.y)
                    ],
                    index=sub.index,
                )
            for epsg, idx2 in epsg_vals.groupby(epsg_vals).groups.items():
                idx2 = list(idx2)
                seg_m = work.loc[idx2].to_crs(epsg=int(epsg))
                cell_m = (
                    gpd.GeoSeries([cell], crs=cells.crs)
                    .to_crs(epsg=int(epsg))
                    .iloc[0]
                )
                d = seg_m.geometry.distance(cell_m.boundary).to_numpy(dtype=float)
                out[idx2] = d
    return pd.Series(out, index=gdf.index)


def umbral_area_por_clase(
    areas_km2: pd.Series,
    class_codes: pd.Series,
    regla: str = AREA_MIN_REGLA,
    percentil: float = AREA_MIN_PERCENTIL,
) -> pd.Series:
    """Devuelve umbral de área (km²) por código de clase según la regla."""
    regla = regla.lower().strip()
    frames = []
    for code, a in areas_km2.groupby(class_codes):
        a = a.dropna()
        if a.empty:
            thr = np.nan
        elif regla in {"median", "mediana"}:
            thr = float(a.median())
        elif regla in {"mean", "media"}:
            thr = float(a.mean())
        elif regla.startswith("p") or regla == "percentil":
            thr = float(a.quantile(percentil))
        else:
            raise ValueError(f"AREA_MIN_REGLA desconocida: {regla}")
        frames.append({"code": int(code), "area_min_km2": thr})
    return pd.DataFrame(frames).set_index("code")["area_min_km2"]


def filtrar_candidatos_calibracion(
    puros: gpd.GeoDataFrame,
    clases_excluidas: set[int] | None = None,
    area_min_regla: str = AREA_MIN_REGLA,
    area_min_percentil: float = AREA_MIN_PERCENTIL,
    borde_min_m: float = BORDE_MIN_M,
    cells: gpd.GeoDataFrame | None = None,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, dict[str, Any]]:
    """Aplica filtros de calibración sobre segmentos 100% puros.

    Orden:
      1) excluir clases no generales
      2) calcular área UTM y umbral por clase (p40/mediana/media)
      3) área ≥ umbral de su etiqueta
      4) distancia al borde CIM ≥ borde_min_m

    Devuelve (candidatos, tabla_umbrales, resumen).
    """
    clases_excluidas = {int(c) for c in (clases_excluidas or CLASES_EXCLUIDAS)}
    df = puros.copy()
    n0 = len(df)

    mask_cls = ~df["class_code"].astype(int).isin(clases_excluidas)
    df = df.loc[mask_cls].copy()
    n_cls = len(df)
    print(
        f"Tras excluir clases {sorted(clases_excluidas)}: {n_cls} / {n0}"
    )

    print("Calculando áreas UTM por centroide...")
    df["area_km2"] = areas_km2_utm_series(df.geometry)
    df["eq_diam_km"] = df["area_km2"].map(diametro_equivalente_km)

    thr = umbral_area_por_clase(
        df["area_km2"], df["class_code"], area_min_regla, area_min_percentil
    )
    df["area_min_km2"] = df["class_code"].astype(int).map(thr)
    mask_area = df["area_km2"] >= df["area_min_km2"]
    df_area = df.loc[mask_area].copy()
    print(
        f"Tras área ≥ {area_min_regla} por clase: {len(df_area)} / {n_cls}"
    )

    print(
        f"Calculando distancia al borde CIM (mín. {borde_min_m:.0f} m = "
        f"{borde_min_m / PIXEL_M:.0f} px)..."
    )
    if cells is None:
        cells = cargar_celdas_cim()
    df_area["dist_to_cim_edge_m"] = distancias_a_borde_cim_m(df_area, cells)
    mask_edge = df_area["dist_to_cim_edge_m"] >= float(borde_min_m)
    n_sin_celda = int(df_area["dist_to_cim_edge_m"].isna().sum())
    candidatos = df_area.loc[mask_edge].copy()
    print(
        f"Tras margen al borde CIM ≥ {borde_min_m:.0f} m: "
        f"{len(candidatos)} / {len(df_area)} "
        f"(sin celda CIM: {n_sin_celda})"
    )

    umbrales = (
        df.groupby("class_code")
        .agg(
            name=("class_name", lambda s: s.mode().iloc[0] if len(s.mode()) else s.iloc[0]),
            n_after_class_filter=("area_km2", "size"),
            area_min_km2=("area_min_km2", "first"),
            area_median_km2=("area_km2", "median"),
            area_mean_km2=("area_km2", "mean"),
            area_p40_km2=("area_km2", lambda s: float(s.quantile(0.40))),
        )
        .reset_index()
        .rename(columns={"class_code": "code"})
    )
    umbrales["code"] = umbrales["code"].astype(int)
    # Conteos tras cada filtro
    cnt_area = df_area.groupby(df_area["class_code"].astype(int)).size()
    cnt_edge = candidatos.groupby(candidatos["class_code"].astype(int)).size()
    umbrales["n_after_area"] = umbrales["code"].map(cnt_area).fillna(0).astype(int)
    umbrales["n_eligible"] = umbrales["code"].map(cnt_edge).fillna(0).astype(int)

    resumen = {
        "n_puros": n0,
        "n_after_class_filter": n_cls,
        "n_after_area": len(df_area),
        "n_eligible": len(candidatos),
        "n_sin_celda_cim": n_sin_celda,
        "clases_excluidas": sorted(clases_excluidas),
        "area_min_regla": area_min_regla,
        "area_min_percentil": area_min_percentil,
        "borde_min_m": borde_min_m,
        "borde_min_px": borde_min_m / PIXEL_M,
    }
    return candidatos, umbrales, resumen


def diametro_equivalente_km(area_km2: float) -> float:
    """Diámetro equivalente (km) = 2 * sqrt(area / pi)."""
    if area_km2 is None or not np.isfinite(area_km2) or area_km2 < 0:
        return float("nan")
    return 2.0 * float(np.sqrt(area_km2 / np.pi))


def proponer_cuotas_cobertura_pm5(
    disponibles: pd.Series,
    n_total: int,
    min_por_clase: int,
    delta: int = CUOTA_DELTA,
) -> pd.DataFrame:
    """Cuotas diferenciadas según cobertura (available), acotadas a centro ± delta.

    centro ≈ N_TOTAL / n_clases; cada clase queda en
    [max(min_por_clase, centro-delta), centro+delta], capado por available.
    La magnitud relativa sigue la cobertura (available) vía pesos proporcionales.
    """
    codes = list(disponibles.index)
    avail = disponibles.astype(int)
    n_cls = len(codes)
    if n_cls == 0:
        return pd.DataFrame(columns=["code", "available", "proposed_quota", "unmet_min"])

    centro = n_total / n_cls
    lo = max(int(min_por_clase), int(np.floor(centro - delta)))
    hi = int(np.ceil(centro + delta))
    print(
        f"Cuotas cobertura_pm5: centro={centro:.2f}, banda=[{lo}, {hi}] "
        f"(delta=±{delta}, min_por_clase={min_por_clase})"
    )

    # Pesos por cobertura; suavizar con raíz para no polarizar extremo
    weights = np.sqrt(avail.astype(float).clip(lower=1))
    weights = weights / weights.sum()
    raw = weights * n_total

    # Enteros por restos mayores, luego clip a [lo, hi] y available
    base = np.floor(raw).astype(int)
    leftover = int(n_total - int(base.sum()))
    frac_order = (raw - base).sort_values(ascending=False).index.tolist()
    assigned = base.copy()
    for i in range(leftover):
        assigned.loc[frac_order[i % len(frac_order)]] += 1

    assigned = assigned.clip(lower=lo, upper=hi)
    assigned = assigned.clip(upper=avail)

    # Ajustar suma a n_total respetando banda y disponibilidad
    def _adjust(diff: int) -> None:
        nonlocal assigned
        if diff == 0:
            return
        # diff > 0: hay que agregar; diff < 0: quitar
        if diff > 0:
            # Preferir clases de mayor cobertura con room
            order = avail.sort_values(ascending=False).index.tolist()
            while diff > 0:
                progressed = False
                for code in order:
                    if diff <= 0:
                        break
                    if assigned[code] < min(hi, int(avail[code])):
                        assigned[code] += 1
                        diff -= 1
                        progressed = True
                if not progressed:
                    break
        else:
            order = avail.sort_values(ascending=True).index.tolist()
            need = -diff
            while need > 0:
                progressed = False
                for code in order:
                    if need <= 0:
                        break
                    if assigned[code] > lo:
                        assigned[code] -= 1
                        need -= 1
                        progressed = True
                if not progressed:
                    break

    _adjust(int(n_total) - int(assigned.sum()))

    out = pd.DataFrame(
        {
            "code": codes,
            "available": [int(avail[c]) for c in codes],
            "proposed_quota": [int(assigned[c]) for c in codes],
        }
    )
    out["deficit"] = 0
    out["below_min_floor"] = out["available"] < min_por_clase
    out["unmet_min"] = (min_por_clase - out["available"]).clip(lower=0)
    out["below_requested_min"] = out["proposed_quota"] < min_por_clase
    out["quota_lo"] = lo
    out["quota_hi"] = hi
    return out


def planificar_estratos_eco(
    candidatos: gpd.GeoDataFrame,
    quotas: pd.DataFrame,
    modo: str = ESTRATIFICACION_ECO,
) -> pd.DataFrame:
    """Plan clase×ecorregión: reparte la cuota de cada clase de forma pareja entre ecos."""
    modo = modo.lower().strip()
    if modo not in {"par_igual", "even", "igual"}:
        raise ValueError(f"ESTRATIFICACION_ECO no soportada: {modo}")

    rows = []
    for _, qrow in quotas.iterrows():
        code = int(qrow["code"])
        quota = int(qrow["proposed_quota"])
        if quota <= 0:
            continue
        sub = candidatos.loc[candidatos["class_code"].astype(int) == code]
        if sub.empty:
            continue
        eco_counts = (
            sub.groupby(["eco_dom_id", "eco_dom_name"], dropna=False)
            .size()
            .reset_index(name="available")
            .sort_values("available", ascending=True)
        )
        ecos = eco_counts.to_dict("records")
        n_eco = len(ecos)
        if n_eco == 0:
            continue
        base = quota // n_eco
        rem = quota % n_eco
        # Dar el +1 primero a ecorregiones con MÁS disponibilidad (para factibilidad)
        order_rem = sorted(range(n_eco), key=lambda i: -ecos[i]["available"])
        targets = [base] * n_eco
        for j in range(rem):
            targets[order_rem[j % n_eco]] += 1
        # Recapar por available y redistribuir déficit
        assigned = []
        deficit = 0
        for i, eco in enumerate(ecos):
            t = min(targets[i], int(eco["available"]))
            deficit += targets[i] - t
            assigned.append(t)
        if deficit > 0:
            # Rellenar en ecos con room, preferir mayor available
            order_fill = sorted(range(n_eco), key=lambda i: -ecos[i]["available"])
            while deficit > 0:
                progressed = False
                for i in order_fill:
                    if deficit <= 0:
                        break
                    room = int(ecos[i]["available"]) - assigned[i]
                    if room > 0:
                        assigned[i] += 1
                        deficit -= 1
                        progressed = True
                if not progressed:
                    break
        for i, eco in enumerate(ecos):
            rows.append(
                {
                    "code": code,
                    "name": qrow.get("name", str(code)),
                    "eco_dom_id": int(eco["eco_dom_id"])
                    if pd.notna(eco["eco_dom_id"])
                    else -1,
                    "eco_dom_name": str(eco["eco_dom_name"]),
                    "available": int(eco["available"]),
                    "proposed_quota": int(assigned[i]),
                }
            )
    return pd.DataFrame(rows)


def proponer_cuotas(
    disponibles: pd.Series,
    n_total: int,
    min_por_clase: int,
    estrategia: str,
    cuota_delta: int = CUOTA_DELTA,
) -> pd.DataFrame:
    """Asigna cuotas según ESTRATEGIA_CUOTA."""
    estrategia = estrategia.lower().strip()
    if estrategia in {"cobertura_pm5", "cobertura_pm"}:
        return proponer_cuotas_cobertura_pm5(
            disponibles, n_total, min_por_clase, delta=cuota_delta
        )
    if estrategia not in {"igual", "proporcional", "raiz", "piso_igual"}:
        raise ValueError(f"ESTRATEGIA_CUOTA desconocida: {estrategia}")

    codes = disponibles.index.tolist()
    avail = disponibles.astype(int)
    # Piso capado por disponibilidad
    floor = avail.clip(upper=min_por_clase)
    assigned = floor.copy()
    remaining = int(n_total) - int(assigned.sum())

    if remaining < 0:
        # Más piso que presupuesto: repartir N_TOTAL de forma equitativa
        # entre TODAS las clases evaluables (máxima cobertura; ninguna a 0 si cabe).
        n_cls = len(codes)
        print(
            f"ADVERTENCIA: suma de pisos ({int(floor.sum())}) > N_TOTAL ({n_total}); "
            f"se reparte {n_total} de forma equitativa entre {n_cls} clases "
            f"(~{n_total // n_cls} c/u) para cubrir todas."
        )
        # Preferir dar el resto (+1) a las clases MÁS RARAS (menor available)
        order_rare = avail.sort_values(ascending=True).index.tolist()
        base = int(n_total) // n_cls
        extra = int(n_total) % n_cls
        assigned = pd.Series(base, index=codes, dtype=int)
        for i, code in enumerate(order_rare):
            if i >= extra:
                break
            assigned[code] += 1
        # Recapar por disponibilidad (si alguna clase no llega al cupo equitativo)
        assigned = assigned.clip(upper=avail)
        rem = int(n_total) - int(assigned.sum())
        if rem > 0:
            for code in order_rare:
                if rem <= 0:
                    break
                room_i = int(avail[code] - assigned[code])
                if room_i > 0:
                    take = min(room_i, rem)
                    assigned[code] += take
                    rem -= take
        remaining = 0
        # No hay "remaining" que repartir después; salimos del bloque de resto
        out = pd.DataFrame(
            {
                "code": codes,
                "available": [int(avail[c]) for c in codes],
                "proposed_quota": [int(assigned[c]) for c in codes],
            }
        )
        out["deficit"] = 0
        out["below_min_floor"] = out["available"] < min_por_clase
        out["unmet_min"] = (min_por_clase - out["available"]).clip(lower=0)
        # También marcar cuánto falta respecto al piso deseado por presupuesto
        out["below_requested_min"] = out["proposed_quota"] < min_por_clase
        return out

    # Capacidad residual por clase
    room = (avail - assigned).clip(lower=0)
    classes_with_room = room[room > 0].index.tolist()

    if remaining > 0 and classes_with_room:
        if estrategia in {"igual", "piso_igual"}:
            weights = pd.Series(1.0, index=classes_with_room)
        elif estrategia == "proporcional":
            weights = avail.loc[classes_with_room].astype(float)
        else:  # raiz
            weights = np.sqrt(avail.loc[classes_with_room].astype(float))

        weights = weights / weights.sum()
        # Asignación entera con método de restos mayores
        raw = weights * remaining
        base = np.floor(raw).astype(int)
        leftover = int(remaining - base.sum())
        frac_order = (raw - base).sort_values(ascending=False).index.tolist()
        extra = pd.Series(0, index=classes_with_room, dtype=int)
        for i in range(leftover):
            extra.loc[frac_order[i % len(frac_order)]] += 1
        add = base + extra

        # Recapar por room e iterar remanente
        add = add.clip(upper=room.loc[classes_with_room])
        assigned.loc[classes_with_room] = assigned.loc[classes_with_room] + add
        rem2 = remaining - int(add.sum())
        # Distribuir remanente a clases con room residual
        while rem2 > 0:
            room2 = (avail - assigned).clip(lower=0)
            eligible = room2[room2 > 0].index.tolist()
            if not eligible:
                break
            # Priorizar según estrategia
            if estrategia == "proporcional":
                eligible = avail.loc[eligible].sort_values(ascending=False).index.tolist()
            elif estrategia == "raiz":
                eligible = (
                    np.sqrt(avail.loc[eligible].astype(float))
                    .sort_values(ascending=False)
                    .index.tolist()
                )
            else:
                eligible = sorted(eligible, key=lambda c: int(assigned[c]))
            for code in eligible:
                if rem2 <= 0:
                    break
                if assigned[code] < avail[code]:
                    assigned[code] += 1
                    rem2 -= 1

    out = pd.DataFrame(
        {
            "code": codes,
            "available": [int(avail[c]) for c in codes],
            "proposed_quota": [int(assigned[c]) for c in codes],
        }
    )
    out["deficit"] = 0
    out["below_min_floor"] = out["available"] < min_por_clase
    out["unmet_min"] = (min_por_clase - out["available"]).clip(lower=0)
    out["below_requested_min"] = out["proposed_quota"] < min_por_clase
    return out


# ---------------------------------------------------------------------------
# Fase 1 — main
# ---------------------------------------------------------------------------


def _stats_size(areas_km2: pd.Series) -> dict[str, float]:
    a = areas_km2.dropna()
    if a.empty:
        return {
            "area_km2_median": np.nan,
            "area_km2_p10": np.nan,
            "area_km2_p90": np.nan,
            "eq_diam_km_median": np.nan,
            "eq_diam_km_p10": np.nan,
            "eq_diam_km_p90": np.nan,
        }
    diams = a.map(diametro_equivalente_km)
    return {
        "area_km2_median": float(a.median()),
        "area_km2_p10": float(a.quantile(0.10)),
        "area_km2_p90": float(a.quantile(0.90)),
        "eq_diam_km_median": float(diams.median()),
        "eq_diam_km_p10": float(diams.quantile(0.10)),
        "eq_diam_km_p90": float(diams.quantile(0.90)),
    }


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = [
        "| " + " | ".join(str(c) for c in cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                cells.append(f"{v:.6g}" if np.isfinite(v) else "nan")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    print("═" * 60)
    print("FASE 1 — Análisis de pureza (sin selección)")
    print("═" * 60)
    params = {
        "RUTA_ENTRADA": RUTA_ENTRADA,
        "DIR_RESULTADOS": DIR_RESULTADOS,
        "PUREZA_MIN": PUREZA_MIN,
        "N_TOTAL_OBJETIVO": N_TOTAL_OBJETIVO,
        "MIN_POR_CLASE": MIN_POR_CLASE,
        "ESTRATEGIA_CUOTA": ESTRATEGIA_CUOTA,
        "CUOTA_DELTA": CUOTA_DELTA,
        "TOL_PUREZA": TOL_PUREZA,
        "CLASES_EXCLUIDAS": sorted(CLASES_EXCLUIDAS),
        "AREA_MIN_REGLA": AREA_MIN_REGLA,
        "AREA_MIN_PERCENTIL": AREA_MIN_PERCENTIL,
        "BORDE_MIN_PX": BORDE_MIN_PX,
        "BORDE_MIN_M": BORDE_MIN_M,
        "PIXEL_M": PIXEL_M,
        "ESTRATIFICACION_ECO": ESTRATIFICACION_ECO,
    }
    print("Parámetros:")
    for k, v in params.items():
        print(f"  {k} = {v}")

    # Una sola lectura del GPKG canónico
    gdf_all = cargar_gpkg(RUTA_ENTRADA)
    det = detectar_columnas(gdf_all)
    gdf_all = enriquecer_canonicos(gdf_all, det)
    puros = filtrar_puros(gdf_all, PUREZA_MIN, TOL_PUREZA)

    name_map: dict[int, str] = {}
    tmp = (
        gdf_all.dropna(subset=["class_code"])
        .loc[gdf_all["class_code"] != 0, ["class_code", "class_name"]]
        .drop_duplicates("class_code")
    )
    for _, row in tmp.iterrows():
        name_map[int(row["class_code"])] = str(row["class_name"])
    for code, name in (
        puros.groupby("class_code")["class_name"]
        .agg(lambda s: s.mode().iloc[0] if len(s.mode()) else s.iloc[0])
        .items()
    ):
        name_map[int(code)] = str(name)

    counts_pure = puros.groupby(puros["class_code"].astype(int)).size()
    n_puros = int(counts_pure.sum())
    all_unique_codes = sorted(name_map.keys())

    # Filtros de calibración (clases generales + área + margen al borde)
    candidatos, umbrales, resumen = filtrar_candidatos_calibracion(puros)
    counts_elig = candidatos.groupby(candidatos["class_code"].astype(int)).size()

    rows = []
    for code in all_unique_codes:
        n_pure = int(counts_pure.get(code, 0))
        excluded = code in CLASES_EXCLUIDAS
        n_elig = 0 if excluded else int(counts_elig.get(code, 0))
        rows.append(
            {
                "code": code,
                "name": name_map.get(code, str(code)),
                "n_pure": n_pure,
                "pct_of_pure": (100.0 * n_pure / n_puros) if n_puros else 0.0,
                "excluded": excluded,
                "n_eligible": n_elig,
                "evaluable": (not excluded) and n_elig > 0,
            }
        )
    dist = pd.DataFrame(rows).sort_values(
        ["excluded", "n_eligible", "n_pure"], ascending=[True, False, False]
    )

    print("\n=== Distribución (puros → elegibles tras filtros) ===")
    print(dist.to_string(index=False))
    no_eval = dist.loc[~dist["evaluable"], "code"].tolist()
    if no_eval:
        print(f"Clases no evaluables / excluidas: {no_eval}")

    global_stats = _stats_size(candidatos["area_km2"]) if len(candidatos) else _stats_size(pd.Series(dtype=float))
    print("\nTamaño global (candidatos elegibles):")
    for k, v in global_stats.items():
        print(f"  {k}: {v:.6g}" if np.isfinite(v) else f"  {k}: nan")

    size_by_class = umbrales.copy()
    size_df = size_by_class.rename(columns={"n_eligible": "n_eligible_final"})

    # Cuotas solo sobre clases evaluables (elegibles > 0)
    evaluables = dist.loc[dist["evaluable"]].copy()
    dispon = evaluables.set_index("code")["n_eligible"]
    quotas = proponer_cuotas(
        dispon, N_TOTAL_OBJETIVO, MIN_POR_CLASE, ESTRATEGIA_CUOTA, CUOTA_DELTA
    )
    quotas.insert(1, "name", quotas["code"].map(lambda c: name_map.get(int(c), str(c))))
    # Enrich with thresholds
    thr_map = umbrales.set_index("code")["area_min_km2"]
    quotas["area_min_km2"] = quotas["code"].map(thr_map)

    eco_plan = planificar_estratos_eco(candidatos, quotas, ESTRATIFICACION_ECO)
    print("\n=== Plan estratos ecorregión (par_igual, cuota>0) ===")
    if len(eco_plan):
        resumen_eco = (
            eco_plan.groupby("code")
            .agg(
                n_ecos=("eco_dom_id", "nunique"),
                quota_sum=("proposed_quota", "sum"),
                ecos_with_quota=("proposed_quota", lambda s: int((s > 0).sum())),
            )
            .reset_index()
        )
        print(resumen_eco.to_string(index=False))
        print(f"Filas clase×eco con cuota>0: {int((eco_plan['proposed_quota']>0).sum())}")

    deficits = quotas.loc[quotas["unmet_min"] > 0].copy()

    print("\n=== Cuotas propuestas (sobre elegibles) ===")
    print(
        quotas[
            ["code", "name", "available", "proposed_quota", "area_min_km2", "unmet_min"]
        ].to_string(index=False)
    )
    print(
        f"\nSuma proposed_quota = {int(quotas['proposed_quota'].sum())} "
        f"(objetivo {N_TOTAL_OBJETIVO})"
    )
    if not deficits.empty:
        print("ADVERTENCIA — déficits vs MIN_POR_CLASE (disponibilidad insuficiente):")
        print(deficits[["code", "name", "available", "unmet_min"]].to_string(index=False))
    else:
        print("Sin déficits de piso MIN_POR_CLASE.")

    # Escritura
    run_dir = crear_dir_run(DIR_RESULTADOS)
    out_dir = run_dir / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    dist_path = out_dir / "class_proportion_distribution.csv"
    dist.to_csv(dist_path, index=False)

    umbrales_path = out_dir / "class_area_thresholds.csv"
    umbrales.to_csv(umbrales_path, index=False)

    prop = quotas[["code", "name", "available", "proposed_quota"]].copy()
    prop_path = out_dir / "proposed_quotas.csv"
    prop.to_csv(prop_path, index=False)

    eco_path = out_dir / "proposed_eco_strata.csv"
    eco_plan.to_csv(eco_path, index=False)

    report_path = out_dir / "analysis_report.md"
    lines = [
        "# Purity analysis report — Phase 1",
        "",
        "## Framework",
        "",
        "The calibration reference will be the **supervisor-confirmed class**, not the raw C2 label.",
        "This phase only proposes quotas on filtered 100% pure segments; it does not validate C2.",
        "",
        "## Parameters",
        "",
    ]
    for k, v in params.items():
        lines.append(f"- `{k}` = `{v}`")
    lines += [
        "",
        "## Filters applied (in order)",
        "",
        "1. Purity == 100%",
        f"2. Exclude classes: `{sorted(CLASES_EXCLUIDAS)}` (water, glaciers)",
        f"3. Area ≥ `{AREA_MIN_REGLA}` of the class (among pure segments of that class)",
        f"4. Distance to CIM rectangle edge ≥ `{BORDE_MIN_PX}` px ({BORDE_MIN_M:.0f} m)",
        f"5. Quotas by coverage with ±{CUOTA_DELTA} around N/n_classes (`{ESTRATEGIA_CUOTA}`)",
        f"6. Ecoregion stratification within class: `{ESTRATIFICACION_ECO}`",
        "",
        "## Column detection",
        "",
        f"- geometry: `{det['geometry']}`",
        f"- class_code: `{det['class_code']}` — {det['reasons']['class_code']}",
        f"- class_name: `{det['class_name']}` — {det['reasons']['class_name']}",
        f"- proportion: `{det['proportion']}` — {det['reasons']['proportion']}",
        f"- encoding: `{det['proportion_encoding']}` — {det['reasons']['proportion_encoding']}",
        f"- keys: `{det['keys']}`",
        "",
        f"## Counts: pure={resumen['n_puros']} → after class filter="
        f"{resumen['n_after_class_filter']} → after area={resumen['n_after_area']} "
        f"→ **eligible={resumen['n_eligible']}**",
        "",
        "### Distribution",
        "",
        _md_table(dist),
        "",
        "### Area thresholds by class",
        "",
        _md_table(umbrales),
        "",
        "### Global size statistics (eligible candidates)",
        "",
        "| metric | value |",
        "|--------|-------|",
    ]
    for k, v in global_stats.items():
        lines.append(f"| `{k}` | {v:.6g} |" if np.isfinite(v) else f"| `{k}` | nan |")
    lines += [
        "",
        "## Proposed quotas",
        "",
        _md_table(prop),
        "",
        f"**Sum of proposed quotas:** {int(prop['proposed_quota'].sum())} "
        f"(target {N_TOTAL_OBJETIVO})",
        "",
        "## Proposed ecoregion strata (even within class)",
        "",
        (
            _md_table(eco_plan.loc[eco_plan["proposed_quota"] > 0])
            if len(eco_plan)
            else "_none_"
        ),
        "",
    ]
    if not deficits.empty:
        lines += [
            "## Deficit warnings (below MIN_POR_CLASE due to scarcity)",
            "",
            _md_table(deficits[["code", "name", "available", "unmet_min"]]),
            "",
        ]
    else:
        lines += ["## Deficit warnings", "", "None.", ""]
    lines += [
        "## Next step",
        "",
        f"Review and edit `{prop_path.name}`, then run Phase 2 with `QUOTAS_CSV` pointing to the approved file.",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "═" * 60)
    print("RESUMEN FASE 1")
    print(f"  Run dir                         : {run_dir}")
    print(f"  class_proportion_distribution.csv   : {dist_path}")
    print(f"  class_area_thresholds.csv       : {umbrales_path}")
    print(f"  proposed_quotas.csv             : {prop_path}")
    print(f"  proposed_eco_strata.csv         : {eco_path}")
    print(f"  analysis_report.md              : {report_path}")
    print(
        f"  elegibles={resumen['n_eligible']} | "
        f"clases evaluables={int(dist['evaluable'].sum())} | "
        f"no evaluables/excluidas={len(no_eval)}"
    )
    print(f"  suma cuotas propuestas={int(prop['proposed_quota'].sum())}")
    print("\n*** Detenerse aquí: revisar proposed_quotas.csv antes de Fase 2 ***")


if __name__ == "__main__":
    main()
