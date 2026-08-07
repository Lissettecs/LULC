"""Auditoría de selección por ecorregión y nacional."""

from __future__ import annotations

import math

import geopandas as gpd
import pandas as pd

from config import params_seleccion as P
from config.diccionarios import CLASS_NAMES, CLASES_MODELO_GENERAL
from seleccion.presencia_rect import ha_clase_series, presencia_clase_por_ha


def auditoria_ecorregion(
    eco_id: int,
    presupuesto_eco: pd.DataFrame,
    seleccion: pd.DataFrame,
    pools_log: pd.DataFrame,
    deficits: list[dict],
) -> pd.DataFrame:
    filas = []
    for _, row in presupuesto_eco.iterrows():
        cid = int(row["clase_id"])
        modo = row["modo"]
        cuota = float(row["cuota_segmentos"])
        sel = seleccion[
            (seleccion.get("clase_objetivo", -9999) == cid)
            | (
                (seleccion.get("lulc_mode_id", -9999) == cid)
                & seleccion.get("modo_tratamiento", "").isin(["estandar", "techo", ""])
            )
        ]
        n_sel = len(sel)
        filas.append(
            {
                "ecorregion_id": eco_id,
                "clase_id": cid,
                "modo": modo,
                "cuota_segmentos": cuota,
                "n_seleccionados": n_sel,
                "deficit": max(0, int(round(cuota / 50)) - n_sel) if modo in ("refuerzo", "censo") else 0,
            }
        )
    return pd.DataFrame(filas)


def consolidar_deficits(deficits: list[dict]) -> pd.DataFrame:
    if not deficits:
        return pd.DataFrame(columns=["ecorregion_id", "clase_id", "modo", "cuota_rectangulos", "n_seleccionados"])
    return pd.DataFrame(deficits)


def _cuota_rectangulos(modo: str, cuota_segmentos: float) -> int:
    if modo in ("refuerzo", "censo"):
        return max(1, int(round(cuota_segmentos / 50)))
    return 0


def _cobertura_objetivo_modo(modo: str) -> float:
    if modo == "censo":
        return float(P.COBERTURA_OBJETIVO_CENSO)
    if modo == "refuerzo":
        return float(P.COBERTURA_OBJETIVO_RARAS)
    return float("nan")


def auditoria_cobertura_celdas(
    seleccion: pd.DataFrame,
    matriz: pd.DataFrame,
    presupuesto: pd.DataFrame,
    candidatos_2x2: gpd.GeoDataFrame | None = None,
    seleccion_gdf: gpd.GeoDataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Cobertura de celdas clase×ecorregión.

    Si se provee `candidatos_2x2`, usa numerador/denominador desde la grilla 2×2
    (cobertura alcanzable ≤ 100 %). Si no, cae al método legacy (ha seleccionada / matriz).
    """
    if candidatos_2x2 is not None and not candidatos_2x2.empty:
        from reauditoria.cobertura import auditoria_cobertura_corregida

        if seleccion_gdf is None and not seleccion.empty and "geometry" in seleccion.columns:
            seleccion_gdf = gpd.GeoDataFrame(seleccion, geometry="geometry", crs="EPSG:32719")
        aud, _ratio = auditoria_cobertura_corregida(
            seleccion,
            candidatos_2x2,
            matriz,
            presupuesto,
            seleccion_gdf=seleccion_gdf,
        )
        if aud.empty:
            return aud, pd.DataFrame()
        filas = []
        for _, row in aud.iterrows():
            pct = row.get("pct_cubierto_alcanzable")
            filas.append(
                {
                    "eco_id": int(row["eco_id"]),
                    "class_id": int(row["class_id"]),
                    "clase": row.get("class_name", row.get("clase", "")),
                    "modo": row.get("modo", ""),
                    "presencia": row.get("presencia", ""),
                    "area_clase_eco_ha": row.get("ha_matriz_presencia", row.get("area_clase_eco_ha", 0)),
                    "area_clase_seleccionada_ha": row.get("ha_seleccionada", 0),
                    "ha_candidatos_2x2": row.get("ha_candidatos_2x2"),
                    "ha_capturada_2x2": row.get("ha_capturada_2x2"),
                    "pct_clase_cubierto": pct,
                    "pct_cubierto_absoluto": row.get("pct_cubierto_absoluto"),
                    "cobertura_objetivo": row.get("objetivo"),
                    "cumple_objetivo": row.get("cumple_objetivo"),
                    "cuota_rects": None,
                    "n_rects_con_clase": row.get("n_rects_con_clase", 0),
                    "estado": row.get("estado", ""),
                    "cobertura": row.get("estado", ""),
                }
            )
        return pd.DataFrame(filas), pd.DataFrame()

    filas: list[dict] = []
    filas_marg: list[dict] = []

    sub = matriz[
        matriz["clase_id"].isin(CLASES_MODELO_GENERAL)
        & (matriz["area_ha"] > 0)
        & (matriz["presencia"].astype(str).str.lower().isin(["presente", "marginal", "confirmada"]))
    ]

    for _, row in sub.iterrows():
        eco_id = int(row["ecorregion_id"])
        cid = int(row["clase_id"])
        area_eco = float(row["area_ha"])
        presencia = str(row.get("presencia", ""))
        # Marginal: flag explícito O área eco entre piso y UMBRAL_PRESENCIA_HA
        solo_marginal = (
            str(presencia).lower() == "marginal"
            or (float(getattr(P, "PISO_PRESENCIA_HA", 50)) <= area_eco < float(getattr(P, "UMBRAL_PRESENCIA_HA", 500)))
        )

        pres = presupuesto[(presupuesto["ecorregion_id"] == eco_id) & (presupuesto["clase_id"] == cid)]
        modo = str(pres.iloc[0]["modo"]) if not pres.empty else "estandar"
        cuota_seg = float(pres.iloc[0]["cuota_segmentos"]) if not pres.empty else 0.0
        cuota_rects = _cuota_rectangulos(modo, cuota_seg)
        cob_obj = _cobertura_objetivo_modo(modo)

        if seleccion.empty:
            n_rects = 0
            area_sel = 0.0
        else:
            eco_sel = seleccion[seleccion["eco_dom_id"].astype(int) == eco_id]
            if eco_sel.empty:
                n_rects = 0
                area_sel = 0.0
            else:
                try:
                    mask = presencia_clase_por_ha(eco_sel, cid)
                except ValueError:
                    mask = pd.Series(False, index=eco_sel.index)
                n_rects = int(mask.sum())
                if n_rects > 0:
                    try:
                        area_sel = float(ha_clase_series(eco_sel.loc[mask], cid).sum())
                    except ValueError:
                        area_sel = 0.0
                else:
                    area_sel = 0.0

        pct_cubierto = (area_sel / area_eco) if area_eco > 0 else 0.0
        if modo in ("censo", "refuerzo") and not math.isnan(cob_obj):
            cumple = pct_cubierto >= cob_obj - 1e-9
        else:
            cumple = n_rects > 0

        if n_rects == 0:
            estado = "vacia"
        elif modo in ("censo", "refuerzo") and not cumple:
            estado = "parcial"
        else:
            estado = "cubierta"

        registro = {
            "eco_id": eco_id,
            "class_id": cid,
            "clase": CLASS_NAMES.get(cid, str(cid)),
            "modo": modo,
            "presencia": presencia,
            "area_clase_eco_ha": round(area_eco, 2),
            "area_clase_seleccionada_ha": round(area_sel, 2),
            "pct_clase_cubierto": round(pct_cubierto, 4),
            "cobertura_objetivo": cob_obj if not math.isnan(cob_obj) else None,
            "cumple_objetivo": cumple if modo in ("censo", "refuerzo") else None,
            "cuota_rects": cuota_rects,
            "n_rects_con_clase": n_rects,
            "estado": estado,
            "cobertura": estado,
        }

        if solo_marginal:
            # No cuentan como déficit en la auditoría principal
            filas_marg.append(registro)
        else:
            filas.append(registro)

    return pd.DataFrame(filas), pd.DataFrame(filas_marg)


def auditoria_nacional(
    seleccion: pd.DataFrame,
    matriz: pd.DataFrame | None = None,
    presupuesto: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if seleccion.empty and matriz is None:
        return pd.DataFrame()

    rows = []
    if not seleccion.empty:
        for eco_id, grp in seleccion.groupby("eco_dom_id"):
            rows.append(
                {
                    "ecorregion_id": int(eco_id),
                    "n_rectangulos": len(grp),
                    "n_train": int((grp["split"] == "train").sum()),
                    "n_val": int((grp["split"] == "val").sum()),
                    "n_test": int((grp["split"] == "test").sum()),
                    "split_inviable": bool(grp.get("split_inviable", False).any()),
                }
            )
    resumen = pd.DataFrame(rows)

    if matriz is not None and presupuesto is not None:
        celdas, _marg = auditoria_cobertura_celdas(seleccion, matriz, presupuesto)
        if not celdas.empty:
            n_vacias = int((celdas["estado"] == "vacia").sum())
            n_parciales = int((celdas["estado"] == "parcial").sum())
            extra = pd.DataFrame(
                [
                    {
                        "ecorregion_id": -1,
                        "n_rectangulos": len(seleccion),
                        "n_celdas_vacias": n_vacias,
                        "n_celdas_parciales": n_parciales,
                        "n_celdas_total": len(celdas),
                    }
                ]
            )
            resumen = pd.concat([resumen, extra], ignore_index=True)
    return resumen
