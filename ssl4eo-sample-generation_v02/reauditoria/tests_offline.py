"""Evaluación offline de tests de aceptación sobre salidas ya generadas (C)."""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from config import params_seleccion as P
from config.diccionarios import CLASES_MASCARA, CLASES_TRANSVERSALES
from seleccion.balanceo import ids_cluster_espacial, verificar_split_clusters
from seleccion.presencia_rect import ha_clase_series, piso_presencia_ha

logger = logging.getLogger("reauditoria")

AREA_NOMINAL = {2: 250.9056, 3: 564.5376}


def _resultado(test_id: str, descripcion: str, criterio: str, valor, pasa: bool | None, detalle: str = "") -> dict:
    if pasa is None:
        res = "NO_EVALUABLE"
    else:
        res = "PASA" if pasa else "FALLA"
    return {
        "test_id": test_id,
        "descripcion": descripcion,
        "criterio": criterio,
        "valor_obtenido": valor if not isinstance(valor, float) else round(valor, 6),
        "resultado": res,
        "detalle": detalle,
    }


def evaluar_tests(
    sel_dir: Path,
    caract_dir: Path,
    aud_corregida: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Ejecuta los criterios de aceptación sobre archivos existentes."""
    filas: list[dict] = []
    csv = sel_dir / "seleccion_nacional.csv"
    if not csv.is_file():
        return pd.DataFrame(
            [_resultado("ALL", "Carga selección", "seleccion_nacional.csv existe", None, None, "archivo ausente")]
        )
    df = pd.read_csv(csv)

    # 1 Universo solo modelo general
    uni = sel_dir / "universo_por_ecorregion.csv"
    if uni.is_file():
        u = pd.read_csv(uni)
        invalidas = set(CLASES_TRANSVERSALES) | set(CLASES_MASCARA) | {0, 27}
        bad = u[u["clase_id"].isin(invalidas)]
        filas.append(
            _resultado(
                "1",
                "Universo solo modelo general",
                "ninguna clase transversal/máscara/0/27",
                int(len(bad)),
                bad.empty,
                f"clases={sorted(bad['clase_id'].unique().tolist())}" if not bad.empty else "",
            )
        )
    else:
        filas.append(_resultado("1", "Universo solo modelo general", "archivo universo", None, None, "ausente"))

    # 2 Sin clase 0
    if "clase_objetivo" in df.columns:
        n0 = int((df["clase_objetivo"] == 0).sum())
        filas.append(_resultado("2", "Sin clase 0 en selección", "clase_objetivo≠0", n0, n0 == 0))
    else:
        filas.append(_resultado("2", "Sin clase 0", "columna clase_objetivo", None, None, "sin columna"))

    # 4-5 CRS
    for huso, epsg in ((18, 32718), (19, 32719)):
        gpkg = sel_dir / f"seleccion_nacional_utm{huso}.gpkg"
        if not gpkg.is_file():
            filas.append(_resultado(f"CRS{huso}", f"CRS huso {huso}", f"EPSG:{epsg}", None, None, "sin gpkg"))
            continue
        g = gpd.read_file(gpkg, rows=1)
        got = g.crs.to_epsg() if g.crs else None
        filas.append(
            _resultado(f"CRS{huso}", f"CRS huso {huso}", f"EPSG:{epsg}", got, got == epsg)
        )

    # 7 Fuga espacial por eco
    if "split" in df.columns and "eco_dom_id" in df.columns:
        leaks = []
        for eco_id, grp in df.groupby("eco_dom_id"):
            n = verificar_split_clusters(grp, "split")["leak_pairs"]
            if n:
                leaks.append(f"E{int(eco_id)}:{n}")
        filas.append(
            _resultado(
                "7",
                "Sin fuga espacial por ecorregión",
                "leak_pairs==0 en cada eco",
                len(leaks),
                len(leaks) == 0,
                "; ".join(leaks),
            )
        )

    # 8 Split mínimos (excl. inviable)
    if "split_inviable" in df.columns:
        fallos = []
        for eco_id, grp in df.groupby("eco_dom_id"):
            if grp["split_inviable"].any():
                continue
            tmp = grp.copy()
            tmp["_c"] = ids_cluster_espacial(tmp)
            n_val = tmp.loc[tmp["split"] == "val", "_c"].nunique()
            n_test = tmp.loc[tmp["split"] == "test", "_c"].nunique()
            if n_val < 2 or n_test < 2:
                fallos.append(f"E{int(eco_id)} val={n_val} test={n_test}")
        filas.append(
            _resultado(
                "8",
                "Split mínimos por ecorregión (sin inviable)",
                "≥2 clusters val y test",
                len(fallos),
                len(fallos) == 0,
                "; ".join(fallos),
            )
        )

    # 12 Train mínimo
    if "split" in df.columns:
        bajos = []
        for eco_id, grp in df.groupby("eco_dom_id"):
            if "split_inviable" in grp.columns and grp["split_inviable"].any():
                continue
            pct = (grp["split"] == "train").mean()
            if pct < P.SPLIT_MIN_PCT_TRAIN:
                bajos.append(f"E{int(eco_id)}:{pct:.1%}")
        filas.append(
            _resultado(
                "12",
                "Train mínimo SPLIT_MIN_PCT_TRAIN",
                f"pct_train≥{P.SPLIT_MIN_PCT_TRAIN:.0%} (sin inviable)",
                len(bajos),
                len(bajos) == 0,
                "; ".join(bajos),
            )
        )

    # 13 Sin train vacío
    vacios = []
    if "split" in df.columns:
        for eco_id, grp in df.groupby("eco_dom_id"):
            if int((grp["split"] == "train").sum()) == 0:
                vacios.append(f"E{int(eco_id)}")
    filas.append(
        _resultado("13", "Sin train vacío", "n_train>0 en toda eco", len(vacios), len(vacios) == 0, "; ".join(vacios))
    )

    # 15 Tope relleno
    if "pool_origen" in df.columns:
        pct_rel = float((df["pool_origen"] == "relleno").mean())
        filas.append(
            _resultado(
                "15",
                "Tope de relleno",
                f"relleno≤{P.TOPE_RELLENO_PCT:.0%}",
                round(pct_rel, 4),
                pct_rel <= P.TOPE_RELLENO_PCT + 1e-6,
                f"relleno={pct_rel:.1%}",
            )
        )

    # 16 Mix de tamaños — criterio ORIGINAL del prompt: |sel−uni|≤15 pp
    side = pd.to_numeric(df.get("rect_side", 0), errors="coerce").fillna(0).astype(int)
    if (side == 0).all() and "grid_mode" in df.columns:
        side = df["grid_mode"].map({"homogeneo": 2, "mixto": 3}).fillna(0).astype(int)
    n2, n3 = int((side == 2).sum()), int((side == 3).sum())
    tot = n2 + n3
    if tot > 0:
        pct3_sel = n3 / tot
        n2u = n3u = 0
        for huso in P.HUSOS:
            for sn in (2, 3):
                p = caract_dir / "consolidado" / f"grilla_utm{huso}_{sn}x{sn}.gpkg"
                if p.is_file():
                    n = len(gpd.read_file(p))
                    if sn == 2:
                        n2u += n
                    else:
                        n3u += n
        if n2u + n3u > 0:
            pct3_uni = n3u / (n2u + n3u)
            delta = abs(pct3_sel - pct3_uni)
            filas.append(
                _resultado(
                    "16",
                    "Mix de tamaños vs universo",
                    "|pct_3x3_sel − pct_3x3_uni| ≤ 15 pp",
                    round(delta, 4),
                    delta <= 0.15,
                    f"sel_3x3={pct3_sel:.1%} uni_3x3={pct3_uni:.1%} Δ={delta:.1%} · n2={n2} n3={n3}",
                )
            )
        else:
            filas.append(_resultado("16", "Mix de tamaños", "universo consolidado", None, None, "sin consolidado"))
    else:
        filas.append(_resultado("16", "Mix de tamaños", "rect_side presente", None, None, "sin tamaños"))

    # 17 Piso presencia
    if {"modo_tratamiento", "clase_objetivo"}.issubset(df.columns):
        sub = df[df["modo_tratamiento"].isin(["censo", "refuerzo"])]
        bajo = 0
        for _, r in sub.iterrows():
            cid = int(r["clase_objetivo"])
            try:
                ha = float(ha_clase_series(pd.DataFrame([r]), cid).iloc[0])
            except Exception:
                ha = 0.0
            if ha < piso_presencia_ha(cid) - 1e-6:
                bajo += 1
        filas.append(
            _resultado(
                "17",
                "Piso de presencia en censo/refuerzo",
                f"ha_clase≥{P.PISO_PRESENCIA_HA} ha",
                bajo,
                bajo == 0,
            )
        )

    # 18 Cobertura de raras reportada
    if aud_corregida is not None and not aud_corregida.empty:
        raras = aud_corregida[aud_corregida["modo"].isin(["censo", "refuerzo"])]
        sin_pct = int(raras["pct_cubierto_alcanzable"].isna().sum()) if "pct_cubierto_alcanzable" in raras else len(raras)
        filas.append(
            _resultado(
                "18",
                "Cobertura de raras reportada",
                "toda celda censo/refuerzo con pct_cubierto_alcanzable",
                sin_pct,
                sin_pct == 0,
            )
        )
        # A.1: ninguna > 100 %
        sobre = raras[pd.to_numeric(raras["pct_cubierto_alcanzable"], errors="coerce").fillna(0) > 1.0001]
        # also all cells
        sobre_all = aud_corregida[
            pd.to_numeric(aud_corregida["pct_cubierto_alcanzable"], errors="coerce").fillna(0) > 1.0001
        ]
        filas.append(
            _resultado(
                "A1",
                "pct_cubierto_alcanzable ≤ 100 %",
                "ninguna celda > 1.0",
                int(len(sobre_all)),
                sobre_all.empty,
                sobre_all[["eco_id", "class_id", "pct_cubierto_alcanzable"]].to_string(index=False)
                if not sobre_all.empty
                else "",
            )
        )

    # 21-22 Solape
    sol = sel_dir / "auditoria_solape.csv"
    if sol.is_file():
        s = pd.read_csv(sol).iloc[0]
        n_pares = int(s.get("n_pares_intersectan", -1))
        diff = float(s.get("diff_rel", 1))
        filas.append(
            _resultado(
                "21",
                "Solape geométrico (suma≈unión)",
                "diff_rel≤0.1 %",
                diff,
                diff <= 0.001,
                f"suma={s.get('suma_km2')} unión={s.get('union_km2')}",
            )
        )
        filas.append(
            _resultado(
                "22",
                "Pares con área de intersección",
                "n_pares_intersectan==0",
                n_pares,
                n_pares == 0,
            )
        )

    # 24 Reporte de superficie
    tiene = sol.is_file() or (sel_dir / "informe_seleccion.md").is_file()
    filas.append(
        _resultado(
            "24",
            "Reporte de superficie en salidas",
            "auditoria_solape o informe con suma/unión/pares",
            int(tiene),
            tiene,
        )
    )

    return pd.DataFrame(filas)
