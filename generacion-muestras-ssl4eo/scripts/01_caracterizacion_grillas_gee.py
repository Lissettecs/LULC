#!/usr/bin/env python3
"""
Caracterizacion de grilla SSL4EO-L / Landsat — v3.1 (Python / Earth Engine)

Puerto del script GEE en caracterizacion_grillas_gee.txt para ejecutar desde
la linea de comandos con la API de Python de Earth Engine.

Requisitos:
  pip install earthengine-api pip-system-certs

  pip-system-certs hace que Python use los certificados de Windows (necesario
  en redes corporativas con inspeccion SSL; evita CERTIFICATE_VERIFY_FAILED).

Autenticacion (primera vez o si el token expiro):
  python caracterizacion_grillas_gee.py --authenticate

Proyecto GCP (por defecto mapbiomas-chile, donde estan los assets):
  python caracterizacion_grillas_gee.py --project mapbiomas-chile ...

Ejemplos scale300 (4 corridas):
  python caracterizacion_grillas_gee.py --utm 18 --rect-side 2 --stats-scale 300
  python caracterizacion_grillas_gee.py --utm 18 --rect-side 3 --stats-scale 300
  python caracterizacion_grillas_gee.py --utm 19 --rect-side 2 --stats-scale 300
  python caracterizacion_grillas_gee.py --utm 19 --rect-side 3 --stats-scale 300

  python caracterizacion_grillas_gee.py --utm 18 --rect-side 2 --stats-scale 300 --wait

Todas las combinaciones scale300 (+ esperar y descargar desde Drive):
  python scripts/01_caracterizacion_grillas_gee.py --run-scale300-all --wait --download

Solo descargar desde Drive (export ya hecho):
  python scripts/02_descargar_grillas_drive.py --scale300-all
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

# Usar almacen de certificados de Windows (redes corporativas / proxy SSL).
try:
    import pip_system_certs.wrapt_requests  # noqa: F401
except ImportError:
    pass

import ee

from taxonomia_clases import (
    NIVEL1_CODE_DICT,
    NIVEL1_NAMES_DICT,
    NIVEL2_CODE_DICT,
    NIVEL2_NAMES_DICT,
    NIVEL3_CODE_DICT,
    NIVEL3_NAMES_DICT,
)

# ---------------------------------------------------------------------------
# Assets y constantes (igual que el script GEE)
# ---------------------------------------------------------------------------

MB_ASSET = (
    "projects/mapbiomas-chile/assets/LULC/COLLECTION-02/CLASSIFICATIONS/"
    "classification-final/clasificacion-final-4"
)
ECO_ASSET = (
    "projects/mapbiomas-chile/assets/LULC/COLLECTION-03/ANCILLARY_DATA/"
    "ECORREGIONES_RASTER/ecorregiones_col3_30m"
)
MGRS_ASSET = (
    "projects/mapbiomas-chile/assets/LULC/COLLECTION-03/ANCILLARY_DATA/"
    "Tiles_Chile_Sentinel"
)
MGRS_NAME_FIELD = "Name"

PERIODS = [
    {"name": "P1", "label": "1999-2005", "start": 1999, "end": 2005,
     "sensor": "Landsat_5_7", "nYears": 7},
    {"name": "P2", "label": "2006-2012", "start": 2006, "end": 2012,
     "sensor": "Landsat_5_7", "nYears": 7},
    {"name": "P3", "label": "2013-2018", "start": 2013, "end": 2018,
     "sensor": "Landsat_8", "nYears": 6},
    {"name": "P4", "label": "2019-2024", "start": 2019, "end": 2024,
     "sensor": "Landsat_8_9", "nYears": 6},
]

GENERAL_INPUT_IDS = [
    1, 3, 59, 60, 67, 10, 12, 63, 66,
    11, 73, 74, 14, 15, 18, 19, 36, 9, 79, 80,
    22, 23, 61, 29, 25, 24, 30, 75, 26, 33, 34, 35, 27,
]
GENERAL_OUTPUT_IDS = [
    1, 3, 59, 60, 67, 10, 12, 63, 66,
    10, 10, 10, 14, 15, 14, 14, 14, 14, 14, 14,
    22, 23, 61, 29, 25, 22, 22, 22, 26, 33, 26, 26, 27,
]

CRITICAL_CLASS_IDS = [23, 61, 33, 67]
CRITICAL_CLASS_VALUES = [1, 1, 1, 1]
NORTH_FOREST_LAT = -33.2
NORTH_FOREST_ID = 3
ACHAPARRADO_ID = 67

TRANSVERSAL_CLASS_IDS = [11, 73, 74, 18, 19, 36, 9, 79, 80, 24, 30, 75, 34]
TRANSVERSAL_CLASS_VALUES = [1] * len(TRANSVERSAL_CLASS_IDS)

ECO_NAMES_DICT = {
    "1": "E1_Puna_seca_andina", "2": "E2_Desierto_Atacama",
    "3": "E3_Matorral_norte_1", "4": "E4_Estepa_andina",
    "5": "E5_Matorral_norte_2", "6": "E6_Andes_norte",
    "7": "E7_Andes_central", "8": "E8_Matorral_sur",
    "9": "E9_Costa_Norte", "10": "E10_Andes_Sur",
    "11": "E11_Costa_Sur_1", "12": "E12_Costa_Sur_2",
    "13": "E13_Andes_Sur_Costa", "14": "E14_Estepa_patagonica",
    "15": "E15_Bosque_subpolar", "16": "E16_Isla_de_Pascua",
    "17": "E17_Juan_Fernandez",
}

CLASS_NAMES_DICT = {
    "1": "Formacion_boscosa", "3": "Otra_Formacion_boscosa",
    "59": "Bosque_primario", "60": "Bosque_secundario",
    "67": "Bosque_achaparrado", "10": "Form_natural_no_boscosa",
    "12": "Pastizal", "63": "Estepa",
    "66": "Matorral", "14": "Agropecuaria_silvicultura",
    "15": "Pastura", "22": "Area_sin_vegetacion",
    "23": "Arena_playa_duna", "61": "Salar",
    "29": "Afloramiento_rocoso", "25": "Otra_sin_vegetacion",
    "26": "Cuerpo_de_agua", "33": "Rio_lago_oceano",
    "27": "No_observado",
}

CONFUSION_PAIRS_DICT = {
    "1": [10, 66],
    "3": [66, 60, 67, 10], "59": [66, 60, 3],
    "60": [66, 3, 67, 10], "67": [66, 60, 12, 10],
    "10": [66, 12, 63, 3], "12": [63, 15, 66, 10],
    "63": [12, 15, 66, 10], "66": [3, 60, 12, 63, 10],
    "14": [15, 12, 63], "15": [12, 63, 14],
    "22": [29, 25, 23, 61], "23": [61, 29, 25],
    "61": [23, 25, 29], "29": [23, 25, 61, 22],
    "25": [29, 23, 61, 22], "26": [33],
    "33": [26], "27": [],
}


def _ee_dict_of_lists(py_dict: dict) -> ee.Dictionary:
    return ee.Dictionary({k: ee.List(v) for k, v in py_dict.items()})

UTM_EPSG = {12: "EPSG:32712", 17: "EPSG:32717", 18: "EPSG:32718", 19: "EPSG:32719"}

# Proyecto GCP con Earth Engine habilitado y acceso a assets MapBiomas Chile.
DEFAULT_EE_PROJECT = "mapbiomas-chile"


# ---------------------------------------------------------------------------
# Funciones auxiliares EE
# ---------------------------------------------------------------------------

def safe_pct(num, den):
    num = ee.Number(num)
    den = ee.Number(den)
    return ee.Number(ee.Algorithms.If(den.gt(0), num.divide(den).multiply(100), 0))


def get_number(dct, key):
    dct = ee.Dictionary(dct)
    return ee.Number(ee.Algorithms.If(dct.get(key), dct.get(key), 0))


def get_groups(dct):
    dct = ee.Dictionary(dct)
    return ee.List(ee.Algorithms.If(dct.get("groups"), dct.get("groups"), ee.List([])))


def dominant_from_groups(groups, group_name, total_area):
    groups = ee.List(groups)
    empty = ee.Dictionary().set(group_name, -9999).set("sum", 0)
    sort_keys = groups.map(
        lambda g: ee.Number(ee.Dictionary(g).get("sum")).multiply(-1)
    )
    top = ee.Dictionary(
        ee.Algorithms.If(groups.size().gt(0), groups.sort(sort_keys).get(0), empty)
    )
    return ee.Dictionary({
        "id": ee.Number(top.get(group_name)),
        "pct": safe_pct(ee.Number(top.get("sum")), total_area),
    })


def get_stable_val(dct, y):
    dct = ee.Dictionary(dct)
    key = ee.String("sy_").cat(ee.Number(y).format("%.0f"))
    return ee.Number(ee.Algorithms.If(
        dct.contains(key),
        ee.Algorithms.If(ee.Algorithms.IsEqual(dct.get(key), None), 0, dct.get(key)),
        0,
    ))


def get_stable_val_by_key(dct, key):
    dct = ee.Dictionary(dct)
    key = ee.String(key)
    return ee.Number(ee.Algorithms.If(
        dct.contains(key),
        ee.Algorithms.If(ee.Algorithms.IsEqual(dct.get(key), None), 0, dct.get(key)),
        0,
    ))


def get_period_stable_stats(p_dict, p_def, threshold):
    p_num = p_def["name"][1:]
    sent = -9999

    def year_stable(y):
        y = ee.Number(y)
        key = ee.String("p").cat(p_num).cat("y_").cat(y.format("%.0f"))
        val = get_stable_val_by_key(p_dict, key)
        return ee.Algorithms.If(val.gte(threshold), y, ee.Number(sent))

    st_list = (
        ee.List.sequence(p_def["start"], p_def["end"])
        .map(year_stable)
        .removeAll(ee.List([sent]))
    )
    return ee.Dictionary({
        "n_stable": st_list.size(),
        "stab_pct": safe_pct(st_list.size(), p_def["nYears"]),
        "yrs_str": ee.String(ee.Algorithms.If(
            st_list.size().gt(0),
            st_list.map(lambda y: ee.Number(y).format("%.0f")).join(","),
            "",
        )),
    })


def reduce_hist(image, geom, scale, valid_area_img):
    return valid_area_img.addBands(image).reduceRegion(
        reducer=ee.Reducer.sum().group(groupField=1, groupName="lulc_id"),
        geometry=geom,
        scale=scale,
        maxPixels=1e9,
        bestEffort=True,
        tileScale=8,
    )


# ---------------------------------------------------------------------------
# Construccion del pipeline EE
# ---------------------------------------------------------------------------

def build_grid_collection(
    *,
    dataset_name: str,
    rect_chips_side: int,
    chip_pixels: int,
    pixel_size: int,
    target_utm_zone: int,
    stats_scale: int,
    start_year: int,
    end_year: int,
    stable_year_pix_threshold: float,
    min_valid_area_pct: float,
    min_mgrs_dom_pct: float,
    use_tile_list: bool,
    target_mgrs_list: list[str],
    input_grid: ee.FeatureCollection | None = None,
    export_name_override: str | None = None,
    class_level: str = "n3",
):
    class_level = (class_level or "n3").lower()
    use_n3 = class_level == "n3"

    eco_names = ee.Dictionary(ECO_NAMES_DICT)
    class_names = ee.Dictionary(
        NIVEL3_NAMES_DICT if use_n3 else CLASS_NAMES_DICT
    )
    n1_codes = ee.Dictionary(NIVEL1_CODE_DICT) if use_n3 else None
    n2_codes = ee.Dictionary(NIVEL2_CODE_DICT) if use_n3 else None
    n3_codes = ee.Dictionary(NIVEL3_CODE_DICT) if use_n3 else None
    n1_names = ee.Dictionary(NIVEL1_NAMES_DICT) if use_n3 else None
    n2_names = ee.Dictionary(NIVEL2_NAMES_DICT) if use_n3 else None
    confusion_pairs = _ee_dict_of_lists(CONFUSION_PAIRS_DICT)

    chip_size_m = chip_pixels * pixel_size
    rect_size_m = chip_size_m * rect_chips_side
    n_chips_base = rect_chips_side * rect_chips_side
    rect_area_m2 = rect_size_m * rect_size_m
    min_rect_area_frac = 0.99
    target_epsg = UTM_EPSG[target_utm_zone]
    grid_mode = "homogeneo" if rect_chips_side <= 2 else "mixto"

    n_years = end_year - start_year + 1
    n_transitions = end_year - start_year

    mb = ee.Image(MB_ASSET)
    eco = ee.Image(ECO_ASSET).select(0).rename("eco_id").toInt16()

    mgrs_raw = ee.FeatureCollection(MGRS_ASSET).filter(
        ee.Filter.notNull([MGRS_NAME_FIELD])
    )

    def set_mgrs_props(f):
        name = ee.String(f.get(MGRS_NAME_FIELD))
        return f.set({
            "mgrs_name": name,
            "utm_zone": ee.Number.parse(name.slice(0, 2)),
        })

    mgrs = mgrs_raw.map(set_mgrs_props)
    mgrs_zone = mgrs.filter(ee.Filter.eq("utm_zone", target_utm_zone))
    if use_tile_list:
        mgrs_zone = mgrs_zone.filter(ee.Filter.inList("mgrs_name", target_mgrs_list))

    years = ee.List.sequence(start_year, end_year).map(
        lambda y: ee.Number(y).toInt()
    )

    def build_yearly_img(y):
        y = ee.Number(y).toInt()
        return (
            mb.select(ee.String("classification_").cat(y.format("%.0f")))
            .rename("classification")
            .toInt16()
            .set("year", y)
        )

    yearly_ic = ee.ImageCollection.fromImages(years.map(build_yearly_img))

    def remap_general(img):
        return (
            img.remap(GENERAL_INPUT_IDS, GENERAL_OUTPUT_IDS, 27)
            .rename("classification")
            .toInt16()
            .copyProperties(img, ["year"])
        )

    yearly_general_ic = yearly_ic.map(remap_general)
    stats_yearly_ic = yearly_ic if use_n3 else yearly_general_ic

    lulc_mode = stats_yearly_ic.reduce(ee.Reducer.mode()).rename("lulc_mode").toInt16()
    lulc_last = ee.Image(
        stats_yearly_ic.filter(ee.Filter.eq("year", end_year)).first()
    ).rename("lulc_last")

    def transition_year(y):
        y = ee.Number(y)
        cur = ee.Image(stats_yearly_ic.filter(ee.Filter.eq("year", y)).first())
        prev = ee.Image(
            stats_yearly_ic.filter(ee.Filter.eq("year", y.subtract(1))).first()
        )
        return cur.neq(prev).rename("transition")

    transition_rate = (
        ee.ImageCollection.fromImages(
            ee.List.sequence(start_year + 1, end_year).map(transition_year)
        )
        .sum()
        .divide(n_transitions)
        .rename("transition_rate")
    )

    stable_mode_rate = (
        stats_yearly_ic.map(lambda img: img.eq(lulc_mode).rename("stable_mode"))
        .sum()
        .divide(n_years)
        .rename("stable_mode_rate")
    )

    stable_bands = []
    for sy in range(start_year, end_year + 1):
        sy_ee = ee.Number(sy).toInt()
        stable_bands.append(
            ee.Image(stats_yearly_ic.filter(ee.Filter.eq("year", sy_ee)).first())
            .eq(lulc_mode)
            .rename(f"sy_{sy}")
        )
    stable_by_year_img = ee.Image.cat(stable_bands)

    period_mode_imgs = {}
    period_stable_imgs = {}
    for p in PERIODS:
        p_mode = (
            stats_yearly_ic.filter(
                ee.Filter.rangeContains("year", p["start"], p["end"])
            )
            .reduce(ee.Reducer.mode())
            .rename(f"mode_{p['name']}")
            .toInt16()
        )
        period_mode_imgs[p["name"]] = p_mode

        p_bands = []
        p_num = p["name"][1:]
        for py in range(p["start"], p["end"] + 1):
            py_ee = ee.Number(py).toInt()
            p_bands.append(
                ee.Image(stats_yearly_ic.filter(ee.Filter.eq("year", py_ee)).first())
                .eq(p_mode)
                .rename(f"p{p_num}y_{py}")
            )
        period_stable_imgs[p["name"]] = ee.Image.cat(p_bands)

    period_stable_all_img = ee.Image.cat([
        period_stable_imgs["P1"],
        period_stable_imgs["P2"],
        period_stable_imgs["P3"],
        period_stable_imgs["P4"],
    ])

    lat_img = ee.Image.pixelLonLat().select("latitude")
    north_mask = lat_img.gte(NORTH_FOREST_LAT)

    def critical_any_img(img):
        crit = img.remap(CRITICAL_CLASS_IDS, CRITICAL_CLASS_VALUES, 0)
        nfor = img.eq(NORTH_FOREST_ID).And(north_mask)
        return crit.Or(nfor).rename("critical_any")

    crit_source_ic = yearly_ic if use_n3 else yearly_general_ic
    critical_any = crit_source_ic.map(critical_any_img).max().rename("critical_any")

    north_forest_any = (
        crit_source_ic.map(
            lambda img: img.eq(NORTH_FOREST_ID).And(north_mask).rename("north_forest_any")
        )
        .max()
        .rename("north_forest_any")
    )

    achaparrado_any = (
        crit_source_ic.map(
            lambda img: img.eq(ACHAPARRADO_ID).rename("achap_any")
        )
        .max()
        .rename("achap_any")
    )

    transversal_any = (
        yearly_ic.map(
            lambda img: img.remap(
                TRANSVERSAL_CLASS_IDS, TRANSVERSAL_CLASS_VALUES, 0
            ).rename("transversal_any")
        )
        .max()
        .rename("transversal_any")
    )

    valid_mask = eco.mask().And(lulc_mode.mask())
    valid_area_img = ee.Image.pixelArea().rename("area").updateMask(valid_mask)

    metrics_img = ee.Image.cat([
        transition_rate.multiply(100).rename("tr_pct"),
        stable_mode_rate.multiply(100).rename("stab_pct"),
        critical_any.multiply(100).rename("crit_pct"),
        north_forest_any.multiply(100).rename("nfor_pct"),
        achaparrado_any.multiply(100).rename("achap_pct"),
        transversal_any.multiply(100).rename("tran_pct"),
        lulc_mode.eq(27).multiply(100).rename("noobs_pct"),
    ]).updateMask(valid_mask)

    export_proj = ee.Projection(target_epsg)

    def build_tile_grid(tile_feature):
        tile_feature = ee.Feature(tile_feature)
        tile_name = ee.String(tile_feature.get("mgrs_name"))

        tile_geom_utm = tile_feature.geometry().transform(export_proj, 1)
        bounds_utm = tile_geom_utm.bounds(1, export_proj)

        coords = ee.List(bounds_utm.coordinates().get(0))
        all_x = coords.map(lambda pt: ee.Number(ee.List(pt).get(0)))
        all_y = coords.map(lambda pt: ee.Number(ee.List(pt).get(1)))

        min_x = ee.Number(all_x.reduce(ee.Reducer.min()))
        max_x = ee.Number(all_x.reduce(ee.Reducer.max()))
        min_y = ee.Number(all_y.reduce(ee.Reducer.min()))
        max_y = ee.Number(all_y.reduce(ee.Reducer.max()))

        n_cols = max_x.subtract(min_x).divide(rect_size_m).floor().toInt()
        n_rows = max_y.subtract(min_y).divide(rect_size_m).floor().toInt()

        col_list = ee.List.sequence(0, n_cols.subtract(1))
        row_list = ee.List.sequence(0, n_rows.subtract(1))

        def build_rect(r):
            r = ee.Number(r).toInt()

            def build_col(c):
                c = ee.Number(c).toInt()
                x0 = min_x.add(c.multiply(rect_size_m))
                x1 = x0.add(rect_size_m)
                y1 = max_y.subtract(r.multiply(rect_size_m))
                y0 = y1.subtract(rect_size_m)

                rect_geom = ee.Geometry.Rectangle(
                    [x0, y0, x1, y1], export_proj, False
                )
                rect_area = rect_geom.area(1)
                rect_frac = rect_area.divide(rect_area_m2)

                rect_id = (
                    tile_name.cat("_").cat(grid_mode)
                    .cat("_").cat(ee.Number(rect_chips_side).format("%.0f"))
                    .cat("x").cat(ee.Number(rect_chips_side).format("%.0f"))
                    .cat("_C").cat(c.format("%03d"))
                    .cat("_R").cat(r.format("%03d"))
                )

                return ee.Feature(rect_geom).set({
                    "rect_id": rect_id,
                    "col_idx": c,
                    "row_idx": r,
                    "mgrs_src": tile_name,
                    "dataset": dataset_name,
                    "grid_mode": grid_mode,
                    "rect_side": rect_chips_side,
                    "rect_m": rect_size_m,
                    "rect_area": rect_area,
                    "rect_frac": rect_frac,
                    "chip_px": chip_pixels,
                    "chip_m": chip_size_m,
                    "n_chips_b": n_chips_base,
                    "utm_zone": target_utm_zone,
                    "utm_epsg": target_epsg,
                    "align": "upper_left",
                })

            return col_list.map(build_col)

        tile_grid = (
            ee.FeatureCollection(row_list.map(build_rect).flatten())
            .filterBounds(tile_geom_utm)
            .filter(ee.Filter.gte("rect_frac", min_rect_area_frac))
        )
        return tile_grid

    if input_grid is not None:
        raw_grid = input_grid
    else:
        raw_grid = ee.FeatureCollection(
            mgrs_zone.toList(mgrs_zone.size()).map(build_tile_grid)
        ).flatten()

    def add_grid_stats(feature):
        geom = feature.geometry()
        total_area = ee.Number(geom.area(1))

        valid_area_dict = valid_area_img.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=stats_scale,
            maxPixels=1e9,
            bestEffort=True,
            tileScale=8,
        )
        valid_area = get_number(valid_area_dict, "area")
        valid_pct = safe_pct(valid_area, total_area)

        eco_hist_dict = valid_area_img.addBands(eco).reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName="eco_id"),
            geometry=geom,
            scale=stats_scale,
            maxPixels=1e9,
            bestEffort=True,
            tileScale=8,
        )
        eco_groups = get_groups(eco_hist_dict)
        eco_dom = dominant_from_groups(eco_groups, "eco_id", valid_area)
        eco_dom_id = ee.Number(eco_dom.get("id"))
        eco_dom_nm = eco_names.get(eco_dom_id.format(), "sin_nombre")

        mode_hist_dict = reduce_hist(lulc_mode, geom, stats_scale, valid_area_img)
        mode_groups = get_groups(mode_hist_dict)
        mode_dom = dominant_from_groups(mode_groups, "lulc_id", valid_area)
        mode_dom_id = ee.Number(mode_dom.get("id"))
        mode_dom_nm = class_names.get(mode_dom_id.format(), "sin_nombre")

        last_hist_dict = reduce_hist(lulc_last, geom, stats_scale, valid_area_img)
        last_groups = get_groups(last_hist_dict)
        last_dom = dominant_from_groups(last_groups, "lulc_id", valid_area)
        last_dom_id = ee.Number(last_dom.get("id"))
        last_dom_nm = class_names.get(last_dom_id.format(), "sin_nombre")

        metrics = metrics_img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=stats_scale,
            maxPixels=1e9,
            bestEffort=True,
            tileScale=8,
        )
        tr_pct = get_number(metrics, "tr_pct")
        stab_pct = get_number(metrics, "stab_pct")
        crit_pct = get_number(metrics, "crit_pct")
        nfor_pct = get_number(metrics, "nfor_pct")
        achap_pct = get_number(metrics, "achap_pct")
        tran_pct = get_number(metrics, "tran_pct")
        noos_pct = get_number(metrics, "noobs_pct")
        n_mode = mode_groups.size()

        intersecting = (
            mgrs_zone.filterBounds(geom)
            .map(lambda t: t.set(
                "inter_area", t.geometry().intersection(geom, 1).area(1)
            ))
            .filter(ee.Filter.gt("inter_area", 0))
        )
        n_mgrs = intersecting.size()
        top_tile = ee.Feature(ee.Algorithms.If(
            n_mgrs.gt(0),
            intersecting.sort("inter_area", False).first(),
            ee.Feature(None, {}),
        ))
        mgrs_nm = ee.Algorithms.If(n_mgrs.gt(0), top_tile.get("mgrs_name"), "sin_tile")
        mgrs_pct = safe_pct(
            ee.Number(ee.Algorithms.If(n_mgrs.gt(0), top_tile.get("inter_area"), 0)),
            total_area,
        )

        stable_by_year_dict = stable_by_year_img.updateMask(valid_mask).reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=stats_scale,
            maxPixels=1e9,
            bestEffort=True,
            tileScale=8,
        )

        sent = -9999

        def year_in_stable_list(y):
            y = ee.Number(y)
            val = get_stable_val(stable_by_year_dict, y)
            return ee.Algorithms.If(val.gte(stable_year_pix_threshold), y, ee.Number(sent))

        stable_yrs_list = years.map(year_in_stable_list).removeAll(ee.List([sent]))
        stable_yrs_str = ee.String(ee.Algorithms.If(
            stable_yrs_list.size().gt(0),
            stable_yrs_list.map(lambda y: ee.Number(y).format("%.0f")).join(","),
            "",
        ))
        n_stable_yrs = stable_yrs_list.size()
        stable_yr_pct = safe_pct(n_stable_yrs, n_years)

        init_run = ee.Dictionary({
            "cur_run": 0, "max_run": 0,
            "cur_start": start_year, "max_start": start_year,
        })

        def iterate_run(y, state):
            state = ee.Dictionary(state)
            y = ee.Number(y)
            is_stable = get_stable_val(stable_by_year_dict, y).gte(stable_year_pix_threshold)
            cur_run = ee.Number(state.get("cur_run"))
            max_run = ee.Number(state.get("max_run"))
            cur_start = ee.Number(state.get("cur_start"))
            max_start = ee.Number(state.get("max_start"))
            new_cur_run = ee.Number(ee.Algorithms.If(is_stable, cur_run.add(1), 0))
            new_cur_st = ee.Number(ee.Algorithms.If(
                is_stable,
                ee.Algorithms.If(cur_run.eq(0), y, cur_start),
                y,
            ))
            new_max_run = ee.Number(ee.Algorithms.If(new_cur_run.gt(max_run), new_cur_run, max_run))
            new_max_st = ee.Number(ee.Algorithms.If(new_cur_run.gt(max_run), new_cur_st, max_start))
            return ee.Dictionary({
                "cur_run": new_cur_run,
                "max_run": new_max_run,
                "cur_start": new_cur_st,
                "max_start": new_max_st,
            })

        final_run = ee.Dictionary(years.iterate(iterate_run, init_run))
        max_stab_run = ee.Number(final_run.get("max_run"))
        stab_run_start = ee.Number(final_run.get("max_start"))
        stab_run_end = ee.Number(ee.Algorithms.If(
            max_stab_run.gt(0), stab_run_start.add(max_stab_run).subtract(1), sent
        ))

        def shannon_step(g, acc):
            p = ee.Number(ee.Dictionary(g).get("sum")).divide(
                ee.Number(ee.Algorithms.If(valid_area.gt(0), valid_area, 1))
            )
            return ee.Number(acc).add(
                ee.Number(ee.Algorithms.If(p.gt(0), p.multiply(p.log()).multiply(-1), 0))
            )

        shannon_idx = ee.Number(mode_groups.iterate(shannon_step, ee.Number(0)))

        confusable_ids = ee.List(ee.Algorithms.If(
            confusion_pairs.contains(mode_dom_id.format()),
            confusion_pairs.get(mode_dom_id.format()),
            ee.List([]),
        ))

        def conf_step(g, acc):
            g = ee.Dictionary(g)
            class_id = ee.Number(g.get("lulc_id"))
            return ee.Number(ee.Algorithms.If(
                confusable_ids.contains(class_id),
                ee.Number(acc).add(ee.Number(g.get("sum"))),
                acc,
            ))

        conf_area = ee.Number(mode_groups.iterate(conf_step, ee.Number(0)))
        conf_risk_pct = safe_pct(conf_area, valid_area)

        period_stable_dict = period_stable_all_img.updateMask(valid_mask).reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=stats_scale,
            maxPixels=1e9,
            bestEffort=True,
            tileScale=8,
        )

        def get_period_mode_and_stab(p_name, p_def):
            hist = reduce_hist(period_mode_imgs[p_name], geom, stats_scale, valid_area_img)
            groups = get_groups(hist)
            dom = dominant_from_groups(groups, "lulc_id", valid_area)
            dom_id = ee.Number(dom.get("id"))
            stab = get_period_stable_stats(period_stable_dict, p_def, stable_year_pix_threshold)
            return {
                "id": dom_id,
                "name": class_names.get(dom_id.format(), "sin_nombre"),
                "pct": ee.Number(dom.get("pct")),
                "nStab": stab.get("n_stable"),
                "stabPct": stab.get("stab_pct"),
                "yrsStr": stab.get("yrs_str"),
            }

        p1 = get_period_mode_and_stab("P1", PERIODS[0])
        p2 = get_period_mode_and_stab("P2", PERIODS[1])
        p3 = get_period_mode_and_stab("P3", PERIODS[2])
        p4 = get_period_mode_and_stab("P4", PERIODS[3])

        priority_score = (
            valid_pct.divide(100).multiply(2.0)
            .add(crit_pct.divide(100).multiply(4.0))
            .add(nfor_pct.divide(100).multiply(3.0))
            .add(achap_pct.divide(100).multiply(3.0))
            .add(ee.Number(n_mode).min(19).divide(19).multiply(2.0))
            .add(shannon_idx.divide(math.log(19)).multiply(1.5))
            .add(tr_pct.divide(100).multiply(1.5))
            .add(noos_pct.multiply(-0.05))
        )

        p3_n_stab = ee.Number(p3["nStab"])
        p4_n_stab = ee.Number(p4["nStab"])

        dim_temporal = ee.String(ee.Algorithms.If(
            tr_pct.gte(15),
            "transicion",
            ee.Algorithms.If(
                max_stab_run.lt(5)
                .And(p3_n_stab.gte(3).Or(p4_n_stab.gte(3)))
                .Or(tran_pct.gt(0)),
                "anual",
                "estable",
            ),
        ))

        mode_pct_num = ee.Number(mode_dom.get("pct"))
        dim_espacial = ee.String(ee.Algorithms.If(
            mode_pct_num.gte(85).And(shannon_idx.lte(0.3)),
            "homogenea",
            ee.Algorithms.If(
                ee.Number(n_mode).lte(4).And(mode_pct_num.gte(45)),
                "simple_media",
                "compleja",
            ),
        ))
        sample_type = dim_temporal.cat("_").cat(dim_espacial)

        rect_id_base = ee.String(ee.Algorithms.If(
            feature.get("rect_id"),
            feature.get("rect_id"),
            ee.String(feature.id()),
        ))

        mode_cid = mode_dom_id.format()
        last_cid = last_dom_id.format()

        if use_n3:
            cls_lvl = "n3"
            n1_cd = n1_codes.get(mode_cid, "")
            n2_cd = n2_codes.get(mode_cid, "")
            n3_cd = n3_codes.get(mode_cid, "")
            n1_nm = n1_names.get(mode_cid, "")
            n2_nm = n2_names.get(mode_cid, "")
            ln1_cd = n1_codes.get(last_cid, "")
            ln2_cd = n2_codes.get(last_cid, "")
            ln3_cd = n3_codes.get(last_cid, "")
        else:
            cls_lvl = "general"
            n1_cd = n2_cd = n3_cd = n1_nm = n2_nm = ""
            ln1_cd = ln2_cd = ln3_cd = ""

        return feature.set({
            "grid_id": rect_id_base,
            "rect_id": rect_id_base,
            "col_idx": feature.get("col_idx"),
            "row_idx": feature.get("row_idx"),
            "mgrs_src": feature.get("mgrs_src"),
            "dataset": dataset_name,
            "grid_mode": grid_mode,
            "rect_side": rect_chips_side,
            "rect_m": rect_size_m,
            "rect_area": feature.get("rect_area"),
            "rect_frac": feature.get("rect_frac"),
            "chip_px": chip_pixels,
            "chip_m": chip_size_m,
            "n_chips_b": n_chips_base,
            "area_km2": total_area.divide(1e6),
            "val_pct": valid_pct,
            "mgrs_dom": mgrs_nm,
            "mgrs_pct": mgrs_pct,
            "n_mgrs": n_mgrs,
            "eco_id": eco_dom_id,
            "eco_name": eco_dom_nm,
            "eco_pct": eco_dom.get("pct"),
            "mode_id": mode_dom_id,
            "mode_name": mode_dom_nm,
            "mode_pct": mode_dom.get("pct"),
            "n_mode": n_mode,
            "last_id": last_dom_id,
            "last_name": last_dom_nm,
            "last_pct": last_dom.get("pct"),
            "tr_pct": tr_pct,
            "stab_pct": stab_pct,
            "noobs_pct": noos_pct,
            "crit_pct": crit_pct,
            "nfor_pct": nfor_pct,
            "achap_pct": achap_pct,
            "tran_pct": tran_pct,
            "shannon": shannon_idx,
            "conf_risk": conf_risk_pct,
            "stab_yrs": stable_yrs_str,
            "n_stab_yrs": n_stable_yrs,
            "stb_yr_pct": stable_yr_pct,
            "mx_stb_run": max_stab_run,
            "run_start": stab_run_start,
            "run_end": stab_run_end,
            "md_id_P1": p1["id"], "md_nm_P1": p1["name"],
            "md_pct_P1": p1["pct"], "n_stb_P1": p1["nStab"],
            "stb_p_P1": p1["stabPct"], "stb_yrs_P1": p1["yrsStr"],
            "md_id_P2": p2["id"], "md_nm_P2": p2["name"],
            "md_pct_P2": p2["pct"], "n_stb_P2": p2["nStab"],
            "stb_p_P2": p2["stabPct"], "stb_yrs_P2": p2["yrsStr"],
            "md_id_P3": p3["id"], "md_nm_P3": p3["name"],
            "md_pct_P3": p3["pct"], "n_stb_P3": p3["nStab"],
            "stb_p_P3": p3["stabPct"], "stb_yrs_P3": p3["yrsStr"],
            "md_id_P4": p4["id"], "md_nm_P4": p4["name"],
            "md_pct_P4": p4["pct"], "n_stb_P4": p4["nStab"],
            "stb_p_P4": p4["stabPct"], "stb_yrs_P4": p4["yrsStr"],
            "dim_temp": dim_temporal,
            "dim_spat": dim_espacial,
            "samp_type": sample_type,
            "prio_sc": priority_score,
            "utm_zone": target_utm_zone,
            "utm_epsg": target_epsg,
            "cls_lvl": cls_lvl,
            "n1_cd": n1_cd,
            "n2_cd": n2_cd,
            "n3_cd": n3_cd,
            "n1_nm": n1_nm,
            "n2_nm": n2_nm,
            "ln1_cd": ln1_cd,
            "ln2_cd": ln2_cd,
            "ln3_cd": ln3_cd,
        })

    grid_stats = (
        raw_grid.map(add_grid_stats)
        .filter(ee.Filter.gte("val_pct", min_valid_area_pct))
        .filter(ee.Filter.gte("mgrs_pct", min_mgrs_dom_pct))
    )

    def export_feature(f):
        f = ee.Feature(f)
        return ee.Feature(
            f.geometry().transform(export_proj, 1),
            f.toDictionary(f.propertyNames()),
        )

    grid_export = grid_stats.map(export_feature)

    level_tag = "_n3" if use_n3 else "_general"
    if export_name_override:
        export_name = export_name_override
    elif input_grid is not None:
        export_name = (
            f"grilla_ssl4eo_{dataset_name}_chips_"
            f"{rect_chips_side}x{rect_chips_side}_from_seleccion_"
            f"UTM{target_utm_zone}_scale{stats_scale}{level_tag}"
        )
    else:
        export_name = (
            f"grilla_ssl4eo_{dataset_name}_{grid_mode}_"
            f"{rect_chips_side}x{rect_chips_side}_UTM{target_utm_zone}_scale{stats_scale}{level_tag}"
        )

    meta = {
        "dataset_name": dataset_name,
        "grid_mode": grid_mode,
        "class_level": class_level,
        "rect_chips_side": rect_chips_side,
        "target_utm_zone": target_utm_zone,
        "stats_scale": stats_scale,
        "target_epsg": target_epsg,
        "export_name": export_name,
        "mgrs_zone": mgrs_zone,
        "raw_grid": raw_grid,
        "grid_stats": grid_stats,
        "grid_export": grid_export,
    }
    return meta


# ---------------------------------------------------------------------------
# Exportacion y CLI
# ---------------------------------------------------------------------------

def _ssl_help() -> str:
    return (
        "\nError SSL (CERTIFICATE_VERIFY_FAILED):\n"
        "  pip install pip-system-certs\n"
        "  Luego vuelve a ejecutar el script.\n"
        "  Si persiste, pide el certificado raiz de tu red a TI."
    )


def _auth_help() -> str:
    return (
        "\nCredenciales Earth Engine no validas o expiradas:\n"
        "  python caracterizacion_grillas_gee.py --authenticate\n"
        "  Se abrira el navegador para autorizar la cuenta."
    )


def _project_help(project: str) -> str:
    return (
        f"\nProyecto GCP '{project}' sin acceso a Earth Engine.\n"
        f"  Usa el proyecto del equipo MapBiomas:\n"
        f"    python caracterizacion_grillas_gee.py --project {DEFAULT_EE_PROJECT} ...\n"
        "  Si tu cuenta no tiene acceso, solicitalo al administrador EE de MapBiomas.\n"
        "  Registro EE: https://developers.google.com/earth-engine/guides/access"
    )


def init_earth_engine(project: str | None = None, *, force_auth: bool = False) -> None:
    project = project or DEFAULT_EE_PROJECT
    print(f"Earth Engine project: {project}")

    if force_auth:
        print("Autorizando Earth Engine en el navegador...")
        ee.Authenticate()
        ee.Initialize(project=project)
        print(f"Autenticacion OK (proyecto: {project}).")
        return

    try:
        ee.Initialize(project=project)
    except ee.EEException as exc:
        msg = str(exc).lower()
        if "authorize" in msg or "authenticate" in msg:
            raise SystemExit(str(exc) + _auth_help()) from exc
        if "not signed up" in msg or "not registered" in msg:
            raise SystemExit(str(exc) + _project_help(project)) from exc
        raise
    except Exception as exc:
        err = str(exc).lower()
        if "ssl" in err or "certificate" in err:
            raise SystemExit(str(exc) + _ssl_help()) from exc
        if "invalid_grant" in err or "revoked" in err:
            raise SystemExit(str(exc) + _auth_help()) from exc
        raise


def wait_for_task(task, poll_seconds: int = 30) -> None:
    status = task.status()
    state = status["state"]
    while state in ("READY", "RUNNING"):
        print(f"  Tarea {task.id}: {state} ...")
        time.sleep(poll_seconds)
        status = task.status()
        state = status["state"]
    if state != "COMPLETED":
        raise RuntimeError(f"Tarea fallida: {status}")
    print(f"  Tarea {task.id}: COMPLETED")


def start_export(
    grid_export: ee.FeatureCollection,
    export_name: str,
    *,
    folder: str,
    export_format: str,
    asset_id: str | None,
) -> ee.batch.Task:
    if export_format == "drive":
        task = ee.batch.Export.table.toDrive(
            collection=grid_export,
            description=export_name,
            folder=folder,
            fileNamePrefix=export_name,
            fileFormat="SHP",
        )
    elif export_format == "asset":
        if not asset_id:
            raise ValueError("--asset-id es obligatorio con --export asset")
        task = ee.batch.Export.table.toAsset(
            collection=grid_export,
            description=export_name,
            assetId=asset_id,
        )
    else:
        raise ValueError(f"Formato de exportacion no soportado: {export_format}")
    task.start()
    return task


def print_run_summary(
    meta: dict,
    *,
    skip_counts: bool = False,
    local_n_features: int | None = None,
) -> None:
    print("\n====== PARAMETROS v3.1 ======")
    print(f"  Dataset:      {meta['dataset_name']}")
    print(f"  Clase nivel:  {meta.get('class_level', 'n3')}")
    print(f"  Modo grilla:  {meta['grid_mode']}")
    print(f"  Rectangulo:   {meta['rect_chips_side']}x{meta['rect_chips_side']}")
    print(f"  STATS_SCALE:  {meta['stats_scale']} m")
    print(f"  CRS:          {meta['target_epsg']}")
    print(f"  Export name:  {meta['export_name']}")

    if skip_counts:
        if local_n_features is not None:
            print(f"  Features:     {local_n_features} (local, sin getInfo EE)")
        print("  Conteos EE:   omitidos (el export corre en batch en servidores GEE)")
        return

    try:
        tiles = meta["mgrs_zone"].aggregate_array("mgrs_name").getInfo()
        print(f"  Tiles MGRS:   {tiles}")
    except Exception as exc:
        print(f"  Tiles MGRS:   (no disponible: {exc})")

    try:
        n_raw = meta["raw_grid"].size().getInfo()
        n_ok = meta["grid_stats"].size().getInfo()
        print(f"  Rect raw:     {n_raw}")
        print(f"  Rect filtrados:{n_ok}")
        sample = meta["grid_stats"].limit(3).getInfo()
        if sample.get("features"):
            ids = [f["properties"].get("grid_id") for f in sample["features"]]
            print(f"  Muestra IDs:  {ids}")
    except Exception as exc:
        print(f"  Conteos:      (requiere cuota EE: {exc})")


def run_job(args: argparse.Namespace) -> ee.batch.Task | None:
    meta = build_grid_collection(
        dataset_name=args.dataset,
        rect_chips_side=args.rect_side,
        chip_pixels=args.chip_pixels,
        pixel_size=args.pixel_size,
        target_utm_zone=args.utm,
        stats_scale=args.stats_scale,
        start_year=args.start_year,
        end_year=args.end_year,
        stable_year_pix_threshold=args.stable_threshold,
        min_valid_area_pct=args.min_valid_pct,
        min_mgrs_dom_pct=args.min_mgrs_pct,
        use_tile_list=args.use_tile_list,
        target_mgrs_list=args.tiles,
        class_level=args.class_level,
    )
    print_run_summary(meta)

    if args.dry_run:
        print("\n[DRY-RUN] No se lanzo exportacion.")
        return None, meta

    task = start_export(
        meta["grid_export"],
        meta["export_name"],
        folder=args.drive_folder,
        export_format=args.export,
        asset_id=args.asset_id,
    )
    print(f"\nExportacion iniciada: {meta['export_name']}")
    print(f"  Task ID:  {task.id}")
    print(f"  Destino:  {args.export} / {args.drive_folder}")
    if args.wait:
        wait_for_task(task)
    else:
        print("  Usa --wait para esperar a que termine.")
        print("  Monitoreo: earthengine task list")
    return task, meta


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Caracteriza grillas SSL4EO-L en Earth Engine (Python API)."
    )
    parser.add_argument("--project", type=str, default=DEFAULT_EE_PROJECT,
                        help=f"Proyecto GCP con EE habilitado (defecto: {DEFAULT_EE_PROJECT})")
    parser.add_argument("--dataset", type=str, default="muestras")
    parser.add_argument("--utm", type=int, choices=[12, 17, 18, 19], default=19)
    parser.add_argument("--rect-side", type=int, choices=[1, 2, 3, 4, 5], default=3,
                        help="2=homogeneo, 3=mixto")
    parser.add_argument("--chip-pixels", type=int, default=264)
    parser.add_argument("--pixel-size", type=int, default=30)
    parser.add_argument("--stats-scale", type=int, default=300)
    parser.add_argument(
        "--class-level", choices=["n3", "general"], default="n3",
        help="n3=IDs nativos C2 (nivel 3); general=remapeo agregado (defecto: n3).",
    )
    parser.add_argument("--start-year", type=int, default=1999)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--stable-threshold", type=float, default=0.75)
    parser.add_argument("--min-valid-pct", type=float, default=20)
    parser.add_argument("--min-mgrs-pct", type=float, default=60)
    parser.add_argument("--use-tile-list", action="store_true")
    parser.add_argument("--tiles", nargs="*", default=["19JBG", "19JCG", "19JDG"])
    parser.add_argument("--export", choices=["drive", "asset"], default="drive")
    parser.add_argument("--drive-folder", type=str, default="GEE_exports")
    parser.add_argument("--asset-id", type=str, default=None)
    parser.add_argument("--authenticate", action="store_true",
                        help="Abre el flujo OAuth de Earth Engine y sale")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo imprime parametros y conteos, sin exportar")
    parser.add_argument("--wait", action="store_true",
                        help="Espera a que termine la tarea de exportacion")
    parser.add_argument("--run-scale300-all", action="store_true",
                        help="Lanza las 4 corridas scale300 (UTM18/19 x homo/mixto)")
    parser.add_argument("--download", action="store_true",
                        help="Tras --wait, descarga ZIP desde Drive a archivos_intermedios/gee_caracterizacion/")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    init_earth_engine(args.project, force_auth=args.authenticate)
    if args.authenticate:
        return 0

    from importlib.machinery import SourceFileLoader
    from rutas_proyecto import GEE_CARACTERIZACION_DIR

    script_dir = Path(__file__).resolve().parent
    gee_out = GEE_CARACTERIZACION_DIR
    gee_out.mkdir(parents=True, exist_ok=True)
    _dl_mod = SourceFileLoader(
        "descargar_grillas_drive",
        str(script_dir / "02_descargar_grillas_drive.py"),
    ).load_module()
    download_grillas = _dl_mod.download_grillas

    if args.run_scale300_all:
        jobs = [
            {"utm": 18, "rect_side": 2, "stats_scale": 300},
            {"utm": 18, "rect_side": 3, "stats_scale": 300},
            {"utm": 19, "rect_side": 2, "stats_scale": 300},
            {"utm": 19, "rect_side": 3, "stats_scale": 300},
        ]
        tasks = []
        for job in jobs:
            job_args = argparse.Namespace(**vars(args))
            job_args.run_scale300_all = False
            job_args.utm = job["utm"]
            job_args.rect_side = job["rect_side"]
            job_args.stats_scale = job["stats_scale"]
            print("\n" + "=" * 60)
            print(f"JOB UTM{job['utm']} rect={job['rect_side']} scale={job['stats_scale']}")
            print("=" * 60)
            result = run_job(job_args)
            if result and result[0]:
                tasks.append(result[0])
        if args.wait and tasks:
            print("\nEsperando todas las tareas...")
            for task in tasks:
                wait_for_task(task)
        print(f"\nListo. Tareas lanzadas: {len(tasks)}")
        if args.download:
            print("\nDescargando desde Google Drive...")
            download_grillas(
                drive_folder=args.drive_folder,
                output_dir=gee_out,
                overwrite=True,
            )
        else:
            print("Descarga manual: python scripts/02_descargar_grillas_drive.py --scale300-all")
            print("  o agrega --download junto con --wait")
        return 0

    result = run_job(args)
    if result and args.download and args.wait:
        _, meta = result
        print("\nDescargando desde Google Drive...")
        download_grillas(
            drive_folder=args.drive_folder,
            output_dir=gee_out,
            prefixes=[meta["export_name"]],
            overwrite=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
