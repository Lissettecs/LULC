"""Tests de aceptación sobre salidas de caracterización y selección."""

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
from config.diccionarios import CLASES_MASCARA, CLASES_TRANSVERSALES
from seleccion.balanceo import ids_cluster_espacial, verificar_split_clusters
from seleccion.presencia_rect import ha_clase_series, piso_presencia_ha

DATA_ROOT = Path("/home/lserey/mapbiomas_land/prod/samples_v02")
CARACT_TAG = os.environ.get("CARACT_RUN_TAG", "")
SEL_TAG = os.environ.get("SEL_RUN_TAG", "")
GRID_TAG = os.environ.get("CARACT_RUN_TAG", "") or os.environ.get("GRID_RUN_TAG", "")


def _caract_dir() -> Path:
    if not CARACT_TAG:
        pytest.skip("Defina CARACT_RUN_TAG para tests de caracterización")
    return DATA_ROOT / "01_caracterizacion" / CARACT_TAG


def _sel_dir() -> Path:
    if not SEL_TAG:
        pytest.skip("Defina SEL_RUN_TAG para tests de selección")
    return DATA_ROOT / "02_seleccion" / SEL_TAG


def _pct_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("pct_") and c[4:].isdigit()]


def _cargar_seleccion() -> pd.DataFrame:
    csv = _sel_dir() / "seleccion_nacional.csv"
    if not csv.is_file():
        pytest.skip("Sin seleccion_nacional.csv")
    return pd.read_csv(csv)


def _rect_side_series(df: pd.DataFrame) -> pd.Series:
    if "rect_side" in df.columns:
        return pd.to_numeric(df["rect_side"], errors="coerce").fillna(0).astype(int)
    if "grid_mode" in df.columns:
        return df["grid_mode"].map({"mixto": 3, "homogeneo": 2}).fillna(0).astype(int)
    return pd.Series(0, index=df.index, dtype=int)


class TestSeleccion:
    def test_universo_solo_modelo_general(self):
        path = _sel_dir() / "universo_por_ecorregion.csv"
        if not path.is_file():
            pytest.skip("Sin universo_por_ecorregion.csv")
        df = pd.read_csv(path)
        invalidas = set(CLASES_TRANSVERSALES) | set(CLASES_MASCARA) | {0, 27}
        bad = df[df["clase_id"].isin(invalidas)]
        assert bad.empty, f"Clases inválidas en universo: {bad['clase_id'].unique()}"

    def test_sin_clase_0_en_seleccion(self):
        df = _cargar_seleccion()
        if "clase_objetivo" in df.columns:
            assert not (df["clase_objetivo"] == 0).any()

    def test_crs_husos_seleccion(self):
        sel_dir = _sel_dir()
        for huso, epsg in ((18, 32718), (19, 32719)):
            gpkg = sel_dir / f"seleccion_nacional_utm{huso}.gpkg"
            if not gpkg.is_file():
                continue
            g = gpd.read_file(gpkg)
            assert g.crs.to_epsg() == epsg, f"Huso {huso}: CRS {g.crs} != EPSG:{epsg}"

    def test_sin_fuga_espacial(self):
        """0 fugas espaciales dentro de cada ecorregión (mismo rect_side)."""
        df = _cargar_seleccion()
        if "split" not in df.columns:
            pytest.skip("Sin split")
        if "eco_dom_id" in df.columns:
            for eco_id, grp in df.groupby("eco_dom_id"):
                stats = verificar_split_clusters(grp, "split")
                assert stats["leak_pairs"] == 0, f"E{eco_id}: fugas={stats['leak_pairs']}"
        else:
            stats = verificar_split_clusters(df, "split")
            assert stats["leak_pairs"] == 0

    def test_split_minimos_por_ecorregion(self):
        df = _cargar_seleccion()
        if "split_inviable" not in df.columns:
            pytest.skip("Sin split_inviable")
        for eco_id, grp in df.groupby("eco_dom_id"):
            if grp["split_inviable"].any():
                continue
            clusters = ids_cluster_espacial(grp)
            tmp = grp.copy()
            tmp["_c"] = clusters
            n_val = tmp.loc[tmp["split"] == "val", "_c"].nunique()
            n_test = tmp.loc[tmp["split"] == "test", "_c"].nunique()
            assert n_val >= 2, f"E{eco_id}: val clusters={n_val}"
            assert n_test >= 2, f"E{eco_id}: test clusters={n_test}"

    def test_trazabilidad(self):
        df = _cargar_seleccion()
        for col in ("pool_origen", "modo_tratamiento", "clase_objetivo"):
            assert col in df.columns
            assert df[col].notna().all()

    def test_motivo_cierre_pools(self):
        sel_dir = _sel_dir()
        pools_files = list((sel_dir / "por_ecorregion").glob("**/pools_E*.csv"))
        if not pools_files:
            pytest.skip("Sin pools_E**.csv")
        for p in pools_files:
            df = pd.read_csv(p)
            assert "motivo_cierre" in df.columns
            assert df["motivo_cierre"].astype(str).str.len().gt(0).all()

    # ── Tests 12–24 (corrección B) ──

    def test_12_train_minimo(self):
        """Ninguna ecorregión sin split_inviable bajo SPLIT_MIN_PCT_TRAIN."""
        df = _cargar_seleccion()
        if "split" not in df.columns:
            pytest.skip("Sin split")
        for eco_id, grp in df.groupby("eco_dom_id"):
            if "split_inviable" in grp.columns and grp["split_inviable"].any():
                continue
            pct = (grp["split"] == "train").mean()
            assert pct >= P.SPLIT_MIN_PCT_TRAIN - 1e-9, (
                f"E{eco_id}: pct_train={pct:.2%} < {P.SPLIT_MIN_PCT_TRAIN:.0%}"
            )

    def test_13_sin_train_vacio(self):
        """Ninguna ecorregión con 0 rectángulos de train."""
        df = _cargar_seleccion()
        if "split" not in df.columns:
            pytest.skip("Sin split")
        for eco_id, grp in df.groupby("eco_dom_id"):
            n_train = int((grp["split"] == "train").sum())
            assert n_train > 0, f"E{eco_id}: train vacío"

    def test_14_techo_split(self):
        """Ninguna partición supera objetivo + SPLIT_MARGEN_TECHO."""
        df = _cargar_seleccion()
        if "split" not in df.columns:
            pytest.skip("Sin split")
        for eco_id, grp in df.groupby("eco_dom_id"):
            if "split_inviable" in grp.columns and grp["split_inviable"].any():
                continue
            n = len(grp)
            for split_name, frac in P.SPLIT_PROPORCIONES.items():
                if split_name == "train":
                    continue
                pct = (grp["split"] == split_name).sum() / max(n, 1)
                techo = frac + P.SPLIT_MARGEN_TECHO
                assert pct <= techo + 1e-6, (
                    f"E{eco_id}: {split_name}={pct:.2%} > techo {techo:.2%}"
                )

    def test_15_tope_relleno(self):
        """pool_origen==relleno no supera TOPE_RELLENO_PCT del total."""
        df = _cargar_seleccion()
        if "pool_origen" not in df.columns:
            pytest.skip("Sin pool_origen")
        n_rel = int((df["pool_origen"] == "relleno").sum())
        pct = n_rel / max(len(df), 1)
        assert pct <= P.TOPE_RELLENO_PCT + 1e-6, (
            f"Relleno={pct:.1%} > TOPE_RELLENO_PCT={P.TOPE_RELLENO_PCT:.0%}"
        )

    def test_16_mix_tamanos(self):
        """Proporción 2x2/3x3 no se desvía >15 pp del universo candidato."""
        df = _cargar_seleccion()
        side = _rect_side_series(df)
        if (side == 0).all():
            pytest.skip("Sin rect_side/grid_mode en selección")
        n2 = int((side == 2).sum())
        n3 = int((side == 3).sum())
        tot = n2 + n3
        if tot == 0:
            pytest.skip("Sin tamaños 2/3")
        pct3_sel = n3 / tot

        # Universo desde consolidado si hay tag
        tag = GRID_TAG or CARACT_TAG
        if not tag:
            pytest.skip("Sin CARACT_RUN_TAG/GRID_RUN_TAG para universo")
        cons = DATA_ROOT / "01_caracterizacion" / tag / "consolidado"
        n2u = n3u = 0
        for huso in (18, 19):
            for side_n, acc in ((2, "n2"), (3, "n3")):
                p = cons / f"grilla_utm{huso}_{side_n}x{side_n}.gpkg"
                if not p.is_file():
                    continue
                # Solo contar filas (rápido vía gpkg sqlite sería ideal; aquí geopandas)
                g = gpd.read_file(p, columns=["grid_id"] if False else None)
                if side_n == 2:
                    n2u += len(g)
                else:
                    n3u += len(g)
        if n2u + n3u == 0:
            pytest.skip("Sin consolidado de universo")
        pct3_uni = n3u / (n2u + n3u)
        assert abs(pct3_sel - pct3_uni) <= 0.15, (
            f"Mix 3x3 sel={pct3_sel:.1%} vs uni={pct3_uni:.1%} (Δ>15 pp)"
        )

    def test_17_piso_presencia(self):
        """Ningún rectángulo censo/refuerzo con ha_clase bajo el piso."""
        df = _cargar_seleccion()
        if "modo_tratamiento" not in df.columns or "clase_objetivo" not in df.columns:
            pytest.skip("Sin columnas de modo/clase")
        sub = df[df["modo_tratamiento"].isin(["censo", "refuerzo"])]
        if sub.empty:
            pytest.skip("Sin censo/refuerzo")
        # Asegurar area_valida_ha derivable
        if "area_valida_ha" not in sub.columns and "area_km2" in sub.columns:
            sub = sub.copy()
            sub["area_valida_ha"] = (
                pd.to_numeric(sub["area_km2"], errors="coerce").fillna(0)
                * pd.to_numeric(sub.get("valid_area_pct", 100), errors="coerce").fillna(100)
            )
        for _, row in sub.iterrows():
            cid = int(row["clase_objetivo"])
            piso = piso_presencia_ha(cid)
            try:
                ha = float(ha_clase_series(pd.DataFrame([row]), cid).iloc[0])
            except ValueError:
                pytest.skip("Sin ha_/pct+area_valida_ha en selección")
            assert ha >= piso - 1e-6, (
                f"grid {row.get('grid_id')}: ha_{cid}={ha:.1f} < piso {piso}"
            )

    def test_18_cobertura_raras(self):
        """Toda celda refuerzo tiene pct_clase_cubierto reportado."""
        path = _sel_dir() / "auditoria_cobertura_celdas.csv"
        if not path.is_file():
            pytest.skip("Sin auditoria_cobertura_celdas.csv")
        df = pd.read_csv(path)
        ref = df[df["modo"] == "refuerzo"]
        if ref.empty:
            pytest.skip("Sin celdas refuerzo")
        assert "pct_clase_cubierto" in ref.columns
        assert ref["pct_clase_cubierto"].notna().all()

    def test_19_suma_composicion(self):
        """sum(pct_id) entre 99.9 y 100.1 en caracterización."""
        car_dir = _caract_dir() / "por_tile"
        files = list(car_dir.glob("*.parquet"))[:20]
        if not files:
            pytest.skip("Sin parquet")
        for f in files:
            df = pd.read_parquet(f)
            cols = _pct_cols(df)
            if not cols:
                continue
            s = df[cols].sum(axis=1)
            bad = ((s < 99.9) | (s > 100.1)).sum()
            assert bad == 0, f"{f.name}: {bad} filas con suma fuera de rango"

    def test_20_desglose_pools(self):
        """Todo pool con conteo de fallas por condición individual."""
        pools_files = list((_sel_dir() / "por_ecorregion").glob("**/pools_E*.csv"))
        if not pools_files:
            pytest.skip("Sin pools")
        required = {"n_falla_valid_area", "n_falla_eco_dom", "n_falla_noobs"}
        for p in pools_files:
            df = pd.read_csv(p)
            missing = required - set(df.columns)
            assert not missing, f"{p.name}: faltan {missing}"

    def test_21_solape_geometrico(self):
        """union.area ≈ sum(area) con tolerancia 0.1 %."""
        sel_dir = _sel_dir()
        partes = []
        for huso in (18, 19):
            gpkg = sel_dir / f"seleccion_nacional_utm{huso}.gpkg"
            if gpkg.is_file():
                partes.append(gpd.read_file(gpkg).to_crs(32719))
        if not partes:
            pytest.skip("Sin gpkg de selección")
        g = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs="EPSG:32719")
        suma = float(g.geometry.area.sum())
        try:
            union = float(g.geometry.union_all().area)
        except AttributeError:
            from shapely.ops import unary_union

            union = float(unary_union(g.geometry.values).area)
        rel = abs(suma - union) / max(suma, 1e-9)
        assert rel <= 0.001, f"diff_rel={rel:.4%} suma={suma} union={union}"

    def test_22_pares_intersectan(self):
        """0 pares con área de intersección real (contactos de borde no cuentan)."""
        solape = _sel_dir() / "auditoria_solape.csv"
        if solape.is_file():
            df = pd.read_csv(solape)
            assert int(df.iloc[0]["n_pares_intersectan"]) == 0
            return
        # Fallback geométrico: solo área > 1 m²
        sel_dir = _sel_dir()
        partes = []
        for huso in (18, 19):
            gpkg = sel_dir / f"seleccion_nacional_utm{huso}.gpkg"
            if gpkg.is_file():
                partes.append(gpd.read_file(gpkg).to_crs(32719))
        if not partes:
            pytest.skip("Sin gpkg")
        g = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs="EPSG:32719")
        pares = gpd.sjoin(
            g[["grid_id", "geometry"]],
            g[["grid_id", "geometry"]],
            predicate="intersects",
        )
        pares = pares[pares["grid_id_left"].astype(str) != pares["grid_id_right"].astype(str)]
        g_idx = g.set_index(g["grid_id"].astype(str), drop=False)
        vistos: set[tuple[str, str]] = set()
        n_area = 0
        for _, row in pares.iterrows():
            a, b = str(row["grid_id_left"]), str(row["grid_id_right"])
            key = (a, b) if a < b else (b, a)
            if key in vistos:
                continue
            vistos.add(key)
            if g_idx.loc[a].geometry.intersection(g_idx.loc[b].geometry).area > 1.0:
                n_area += 1
        assert n_area == 0, f"Pares con solape de área: {n_area}"

    def test_23_orden_por_tamano(self):
        """Proporción 3x3 seleccionados >= proporción universo − 0.05 (pragmático)."""
        df = _cargar_seleccion()
        side = _rect_side_series(df)
        if (side == 0).all():
            pytest.skip("Sin rect_side")
        tot = int((side.isin([2, 3])).sum())
        if tot == 0:
            pytest.skip("Sin tamaños")
        pct3_sel = int((side == 3).sum()) / tot
        tag = GRID_TAG or CARACT_TAG
        if not tag:
            pytest.skip("Sin tag de caracterización para universo")
        cons = DATA_ROOT / "01_caracterizacion" / tag / "consolidado"
        n2u = n3u = 0
        for huso in (18, 19):
            for side_n in (2, 3):
                p = cons / f"grilla_utm{huso}_{side_n}x{side_n}.gpkg"
                if not p.is_file():
                    continue
                n = len(gpd.read_file(p, rows=None))
                if side_n == 2:
                    n2u += n
                else:
                    n3u += n
        if n2u + n3u == 0:
            pytest.skip("Sin universo")
        pct3_uni = n3u / (n2u + n3u)
        assert pct3_sel >= pct3_uni - 0.05, (
            f"3x3 sel={pct3_sel:.1%} < uni−5pp ({pct3_uni - 0.05:.1%})"
        )

    def test_24_reporte_superficie(self):
        """Informe/auditoría trae suma de áreas, unión y conteo de pares."""
        solape = _sel_dir() / "auditoria_solape.csv"
        if solape.is_file():
            df = pd.read_csv(solape)
            for col in ("suma_km2", "union_km2", "n_pares_intersectan"):
                assert col in df.columns
            return
        informe = _sel_dir() / "informe_seleccion.md"
        if not informe.is_file():
            pytest.skip("Sin auditoria_solape.csv ni informe_seleccion.md")
        text = informe.read_text(encoding="utf-8").lower()
        assert "suma" in text or "unión" in text or "union" in text
        assert "par" in text


class TestCaracterizacion:
    def test_composicion_suma_100(self):
        car_dir = _caract_dir() / "por_tile"
        files = list(car_dir.glob("*.parquet"))[:20]
        if not files:
            pytest.skip("Sin parquet")
        for f in files:
            df = pd.read_parquet(f)
            cols = _pct_cols(df)
            if not cols:
                continue
            s = df[cols].sum(axis=1)
            bad = ((s < 99.9) | (s > 100.1)).sum()
            assert bad == 0, f"{f.name}: {bad} filas con suma fuera de rango"

    def test_sin_pct_0(self):
        car_dir = _caract_dir() / "por_tile"
        f = next(car_dir.glob("*.parquet"), None)
        if f is None:
            pytest.skip("Sin parquet")
        cols = pd.read_parquet(f).columns
        assert "pct_0" not in cols
        assert "pctp_0" not in cols

    def test_crs_consolidado(self):
        cons = _caract_dir() / "consolidado"
        for huso, epsg in ((18, 32718), (19, 32719)):
            gpkg = cons / f"grilla_utm{huso}_2x2.gpkg"
            if not gpkg.is_file():
                pytest.skip(f"Falta {gpkg.name}")
            g = gpd.read_file(gpkg, rows=1)
            assert g.crs.to_epsg() == epsg
