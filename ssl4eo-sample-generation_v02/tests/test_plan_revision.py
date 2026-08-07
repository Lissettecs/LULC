"""Tests del plan de años de revisión."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

from config import params_plan_revision as P
from plan_revision.derivar import asignar_rev_years, enriquecer_dataframe
from plan_revision.exportar import ejecutar_plan_revision
from plan_revision.reporte import expandir_pares
from plan_revision.validar import validar_plan

SEL_DIR = Path(P.SEL_ROOT) / P.SEL_RUN_TAG


@pytest.fixture(scope="module")
def seleccion_df() -> pd.DataFrame:
    if not SEL_DIR.is_dir():
        pytest.skip(f"Sin corrida {SEL_DIR}")
    csv = SEL_DIR / "seleccion_nacional.csv"
    if csv.is_file():
        return pd.read_csv(csv)
    frames = []
    for h in (18, 19):
        p = SEL_DIR / f"seleccion_nacional_utm{h}.gpkg"
        if p.is_file():
            frames.append(gpd.read_file(p).drop(columns="geometry"))
    if not frames:
        pytest.skip("Sin datos de selección")
    return pd.concat(frames, ignore_index=True)


def test_todos_tienen_rev_year1(seleccion_df: pd.DataFrame):
    out = enriquecer_dataframe(seleccion_df)
    assert len(out) == 341
    assert (out["rev_year1"] != P.SENTINEL).all()


def test_validacion_ok(seleccion_df: pd.DataFrame):
    out = enriquecer_dataframe(seleccion_df)
    res = validar_plan(out)
    assert res.ok, res.errores[:5]


def test_anuales_copan_ref_year(seleccion_df: pd.DataFrame):
    out = enriquecer_dataframe(seleccion_df)
    anuales = out[out["sample_type"].isin(P.TIPOS_ANUAL)]
    for _, row in anuales.iterrows():
        assert int(row["rev_year1"]) == int(row["ref_year"])
        assert row["rev_role1"] == "anual"
        assert row["rev_metodo"] == "ref_year_directo"


def test_transiciones_tres_anios_o_fallback(seleccion_df: pd.DataFrame):
    out = enriquecer_dataframe(seleccion_df)
    trans = out[out["sample_type"].isin(P.TIPOS_TRANSICION)]
    for _, row in trans.iterrows():
        if row["rev_metodo"] == "transicion_fallback_sin_cambio_periodo":
            assert row["rev_n_years"] == 1
        else:
            assert row["rev_n_years"] == 3
            assert row["rev_role1"] == "durante_cambio"


def test_expandido_cuenta_pares(seleccion_df: pd.DataFrame):
    out = enriquecer_dataframe(seleccion_df)
    exp = expandir_pares(out)
    assert len(exp) == out["rev_n_years"].sum()
    assert exp["rev_year"].between(P.ANIO_MIN, P.ANIO_MAX).all()


def test_ejecutar_escribe_salidas(tmp_path: Path):
    if not SEL_DIR.is_dir():
        pytest.skip(f"Sin corrida {SEL_DIR}")
    dest = ejecutar_plan_revision(SEL_DIR, out_dir=tmp_path / "plan_test")
    assert (dest / "seleccion_con_rev_years.csv").is_file()
    assert (dest / "seleccion_con_rev_years_utm18.gpkg").is_file()
    assert (dest / "seleccion_con_rev_years_utm19.gpkg").is_file()
    assert (dest / "plan_revision_expandido.csv").is_file()
    assert (dest / "reporte_plan_revision.md").is_file()
    assert (dest / "summary.json").is_file()
    # originales intactos
    assert not (SEL_DIR / "seleccion_con_rev_years.csv").exists()


def test_reglas_unitarias():
    row = pd.Series({
        "sample_type": "anual_homogenea",
        "ref_year": 2009,
    })
    rev = asignar_rev_years(row)
    assert rev["rev_year1"] == 2009
    assert rev["rev_role1"] == "anual"

    row_e = pd.Series({
        "sample_type": "estable_homogenea",
        "stab_run_start": 1999,
        "stab_run_end": 2024,
    })
    rev_e = asignar_rev_years(row_e)
    assert rev_e["rev_role1"] == "ancla"
    assert rev_e["rev_n_years"] == 2
    assert rev_e["rev_role2"] == "control_sensor"
