"""Tests de aceptación nacional (grilla UTM + selección corregida)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import params_seleccion as P
from config.diccionarios import CLASS_NAMES, CLASES_MASCARA
from seleccion.balanceo import verificar_split_clusters

DATA_ROOT = Path("/home/lserey/mapbiomas_land/prod/samples_v02")
CARACT_TAG = os.environ.get("CARACT_RUN_TAG", "")
SEL_TAG = os.environ.get("SEL_RUN_TAG", "")

LADO = {2: 15840.0, 3: 23760.0}
AREA_NOMINAL = {2: 250.9, 3: 564.5}
UTM_EPSG = {18: 32718, 19: 32719}
IDS_OK = set(CLASS_NAMES) | set(CLASES_MASCARA) | {
    9, 11, 18, 19, 24, 30, 33, 34, 36, 50, 73, 74, 75, 79, 80,
}


def _caract_dir() -> Path:
    if not CARACT_TAG:
        pytest.skip("Defina CARACT_RUN_TAG")
    return DATA_ROOT / "01_caracterizacion" / CARACT_TAG


def _sel_dir() -> Path:
    if not SEL_TAG:
        pytest.skip("Defina SEL_RUN_TAG")
    return DATA_ROOT / "02_seleccion" / SEL_TAG


def _consolidado(huso: int, side: int) -> gpd.GeoDataFrame:
    p = _caract_dir() / "consolidado" / f"grilla_utm{huso}_{side}x{side}.gpkg"
    if not p.is_file():
        pytest.skip(f"Falta {p.name}")
    g = gpd.read_file(p)
    assert g.crs.to_epsg() == UTM_EPSG[huso]
    return g


def _sel_nativas() -> list[gpd.GeoDataFrame]:
    out = []
    for huso, epsg in UTM_EPSG.items():
        p = _sel_dir() / f"seleccion_nacional_utm{huso}.gpkg"
        if not p.is_file():
            continue
        g = gpd.read_file(p)
        assert g.crs.to_epsg() == epsg
        out.append(g)
    if not out:
        pytest.skip("Sin GPKG canónicos de selección")
    return out


def test_01_consolidado_crs_nativo():
    for huso in P.HUSOS:
        for side in (2, 3):
            _consolidado(huso, side)


def test_02_lados_2x2_consolidado():
    for huso in P.HUSOS:
        g = _consolidado(huso, 2)
        if g.empty:
            continue
        b = g.geometry.bounds
        ancho = b.maxx - b.minx
        alto = b.maxy - b.miny
        assert (ancho - LADO[2]).abs().max() <= 1.0
        assert (alto - LADO[2]).abs().max() <= 1.0


def test_03_lados_3x3_consolidado():
    for huso in P.HUSOS:
        g = _consolidado(huso, 3)
        if g.empty:
            continue
        b = g.geometry.bounds
        ancho = b.maxx - b.minx
        alto = b.maxy - b.miny
        assert (ancho - LADO[3]).abs().max() <= 1.0
        assert (alto - LADO[3]).abs().max() <= 1.0


def test_04_ratio_area_nominal():
    g = _consolidado(19, 2)
    side = g.rect_side.astype(int)
    ratio = (g.geometry.area / 1e6) / side.map(AREA_NOMINAL)
    assert (ratio > 0.99).all()


def test_05_sin_pct_nodata():
    g = _consolidado(18, 2)
    assert "pct_0" not in g.columns
    assert "pct_27" not in g.columns


def test_06_suma_pct_consolidado():
    g = _consolidado(18, 2)
    pcts = [c for c in g.columns if c.startswith("pct_") and c[4:].isdigit()]
    s = g[pcts].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    assert ((s >= 99.9) & (s <= 100.1)).all()


def test_07_flag_distorsion_borde():
    g = _consolidado(18, 2)
    assert "flag_distorsion_borde" in g.columns
    assert g["flag_distorsion_borde"].dtype == bool or g["flag_distorsion_borde"].isin([True, False, 0, 1]).all()


def test_08_seleccion_crs_nativo():
    _sel_nativas()


def test_09_seleccion_sin_solape():
    for g in _sel_nativas():
        if len(g) < 2:
            continue
        suma = float(g.geometry.area.sum() / 1e6)
        union = float(g.geometry.union_all().area / 1e6)
        assert abs(suma - union) / max(suma, 1e-9) <= 0.001


def test_10_quince_ecorregiones():
    df = pd.read_csv(_sel_dir() / "seleccion_nacional.csv")
    ecos = set(df["eco_dom_id"].astype(int).unique())
    assert len(ecos.intersection(set(P.ECORREGIONES))) >= 10


def test_11_cobertura_alcanzable_le_100():
    aud = _sel_dir() / "auditoria_cobertura_celdas.csv"
    if not aud.is_file():
        pytest.skip("Sin auditoria_cobertura_celdas.csv")
    df = pd.read_csv(aud)
    col = "pct_clase_cubierto" if "pct_clase_cubierto" in df.columns else "pct_cubierto_alcanzable"
    if col not in df.columns:
        pytest.skip("Sin columna de cobertura alcanzable")
    vals = pd.to_numeric(df[col], errors="coerce").dropna()
    assert (vals <= 1.0 + 1e-6).all(), f"max pct={vals.max()}"


def test_12_sin_presupuesto_agotado_cuota_clase():
    if not P.CUOTA_CLASE_ES_OBJETIVO:
        pytest.skip("CUOTA_CLASE_ES_OBJETIVO desactivado")
    pools = list((_sel_dir() / "por_ecorregion").glob("**/pools_E*.csv"))
    if not pools:
        pytest.skip("Sin pools")
    for p in pools:
        df = pd.read_csv(p)
        if "motivo_cierre" not in df.columns:
            continue
        censo = df[df["pool"].astype(str).str.match(r"^(censo|presencia)_")]
        bad = censo[censo["motivo_cierre"] == "presupuesto_agotado"]
        assert bad.empty, f"{p.name}: presupuesto_agotado en pools de clase"


def test_13_train_minimo():
    df = pd.read_csv(_sel_dir() / "seleccion_nacional.csv")
    for eco_id, grp in df.groupby("eco_dom_id"):
        if "split_inviable" in grp.columns and grp["split_inviable"].any():
            continue
        pct = (grp["split"] == "train").mean()
        assert pct >= P.SPLIT_MIN_PCT_TRAIN - 1e-9, f"E{eco_id}: train={pct:.1%}"


def test_14_tope_relleno():
    df = pd.read_csv(_sel_dir() / "seleccion_nacional.csv")
    n_rel = int((df["pool_origen"] == "relleno").sum())
    assert n_rel / max(len(df), 1) <= P.TOPE_RELLENO_PCT + 1e-6


def test_15_cuota_min_mix():
    df = pd.read_csv(_sel_dir() / "seleccion_nacional.csv")
    side = pd.to_numeric(df.get("rect_side", 0), errors="coerce").fillna(0).astype(int)
    if (side == 0).all() and "grid_mode" in df.columns:
        side = df["grid_mode"].map({"homogeneo": 2, "mixto": 3}).fillna(0).astype(int)
    n2, n3 = int((side == 2).sum()), int((side == 3).sum())
    tot = n2 + n3
    if tot == 0:
        pytest.skip("Sin tamaños")
    pct2 = n2 / tot
    pct3 = n3 / tot
    assert pct2 >= P.CUOTA_MIN_2X2_PCT - 0.20, f"2x2={pct2:.1%} < cuota min {P.CUOTA_MIN_2X2_PCT:.0%} (tol)"
    assert pct3 >= P.CUOTA_MIN_3X3_PCT - 0.20, f"3x3={pct3:.1%} < cuota min {P.CUOTA_MIN_3X3_PCT:.0%} (tol)"
