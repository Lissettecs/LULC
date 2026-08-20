"""Tablas resumen para visualización de selección."""

from __future__ import annotations

import pandas as pd

from config.diccionarios import CLASS_NAMES, CLASES_PROTEGIDAS, ECO_NAMES

MAINLAND_ECO_IDS = frozenset(range(1, 16))

CALIDAD_METRICS = [
    "valid_area_pct",
    "eco_dom_pct",
    "lulc_mode_pct",
    "transition_pct",
    "shannon_idx",
    "conf_risk_pct",
    "max_stab_run",
]


def ecorregion_label(eco_id, eco_name: str | None = None) -> str:
    eid = int(eco_id) if pd.notna(eco_id) else -1
    if eco_name and str(eco_name).strip() not in ("", "nan", "sin_nombre"):
        name = str(eco_name)
        if name.startswith("E") and "_" in name:
            return name.split("_")[0]
        return name
    base = ECO_NAMES.get(eid, f"E{eid}")
    return base.split("_")[0] if "_" in base else base


def preparar_dataframe(gdf) -> pd.DataFrame:
    df = pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))
    if "eco_dom_id" in df.columns:
        df = df[df["eco_dom_id"].astype(int).isin(MAINLAND_ECO_IDS)].copy()
        df["ecorregion"] = df.apply(
            lambda r: ecorregion_label(r.get("eco_dom_id"), r.get("eco_dom_name")),
            axis=1,
        )
    df["tipo_muestra"] = df.get("sample_type", "").astype(str)
    df["clase_modal"] = df.get("lulc_mode_name", "").astype(str)
    if "utm_zone" in df.columns:
        df["utm"] = "UTM" + pd.to_numeric(df["utm_zone"], errors="coerce").fillna(0).astype(int).astype(str)
    else:
        df["utm"] = "TOTAL"
    return df


def resumen_general(df: pd.DataFrame, utm: str = "TOTAL") -> pd.DataFrame:
    data = df.copy()
    if utm != "TOTAL" and "utm" in data.columns:
        data = data[data["utm"] == utm]
    n_crit = 0
    for cid in CLASES_PROTEGIDAS:
        col = f"pct_{cid}"
        if col in data.columns:
            n_crit += int((pd.to_numeric(data[col], errors="coerce").fillna(0) >= 5).sum())
    return pd.DataFrame(
        [{
            "utm": utm,
            "n_muestras": len(data),
            "n_ecorregiones": data["ecorregion"].nunique() if "ecorregion" in data.columns else 0,
            "n_clases_modales": data["clase_modal"].nunique() if "clase_modal" in data.columns else 0,
            "n_clases_protegidas": n_crit,
            "n_homogeneo": int((data.get("grid_mode", "") == "homogeneo").sum()),
            "n_mixto": int((data.get("grid_mode", "") == "mixto").sum()),
            "n_train": int((data.get("split", "") == "train").sum()),
            "n_val": int((data.get("split", "") == "val").sum()),
            "n_test": int((data.get("split", "") == "test").sum()),
        }]
    )


def por_tipo(df: pd.DataFrame, utm: str = "TOTAL") -> pd.DataFrame:
    data = df.copy()
    if utm != "TOTAL" and "utm" in data.columns:
        data = data[data["utm"] == utm]
    grp = data.groupby(["tipo_muestra", "dim_temporal", "dim_espacial"], dropna=False).size().reset_index(name="n_muestras")
    return grp.sort_values("n_muestras", ascending=False)


def split_por_tipo(df: pd.DataFrame, utm: str = "TOTAL") -> pd.DataFrame:
    data = df.copy()
    if utm != "TOTAL" and "utm" in data.columns:
        data = data[data["utm"] == utm]
    if "split" not in data.columns:
        return pd.DataFrame()
    return (
        data.groupby(["tipo_muestra", "split"], dropna=False)
        .size()
        .reset_index(name="n_muestras")
    )


def grid_mode_por_tipo(df: pd.DataFrame, utm: str = "TOTAL") -> pd.DataFrame:
    data = df.copy()
    if utm != "TOTAL" and "utm" in data.columns:
        data = data[data["utm"] == utm]
    if "grid_mode" not in data.columns:
        return pd.DataFrame()
    return (
        data.groupby(["tipo_muestra", "grid_mode"], dropna=False)
        .size()
        .reset_index(name="n_muestras")
    )


def calidad_por_tipo(df: pd.DataFrame, utm: str = "TOTAL") -> pd.DataFrame:
    data = df.copy()
    if utm != "TOTAL" and "utm" in data.columns:
        data = data[data["utm"] == utm]
    metrics = [c for c in CALIDAD_METRICS if c in data.columns]
    if not metrics:
        return pd.DataFrame()
    return data.groupby("tipo_muestra")[metrics].mean().round(2).reset_index()


def pivot_eco_clase(df: pd.DataFrame) -> pd.DataFrame:
    if "ecorregion" not in df.columns:
        return pd.DataFrame()
    p = pd.crosstab(df["ecorregion"], df["clase_modal"])
    order = sorted(p.index, key=lambda x: int(str(x).replace("E", "") or 0))
    return p.reindex(order)


def pivot_eco_tipo(df: pd.DataFrame) -> pd.DataFrame:
    if "ecorregion" not in df.columns:
        return pd.DataFrame()
    p = pd.crosstab(df["ecorregion"], df["tipo_muestra"])
    order = sorted(p.index, key=lambda x: int(str(x).replace("E", "") or 0))
    return p.reindex(order)


def pivot_clase_tipo(df: pd.DataFrame) -> pd.DataFrame:
    return pd.crosstab(df["clase_modal"], df["tipo_muestra"])


def clases_protegidas_resumen(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cid in CLASES_PROTEGIDAS:
        col = f"pct_{cid}"
        if col not in df.columns:
            continue
        pct = pd.to_numeric(df[col], errors="coerce").fillna(0)
        mask = pct >= 5.0
        rows.append({
            "clase_id": cid,
            "clase": CLASS_NAMES.get(cid, str(cid)),
            "n_muestras": int(mask.sum()),
        })
    rows.append({
        "clase_id": "",
        "clase": "TOTAL (cualquier protegida)",
        "n_muestras": int(sum(r["n_muestras"] for r in rows)),
    })
    return pd.DataFrame(rows)


def clases_protegidas_detalle(df: pd.DataFrame) -> pd.DataFrame:
    masks = []
    for cid in CLASES_PROTEGIDAS:
        col = f"pct_{cid}"
        if col in df.columns:
            masks.append(pd.to_numeric(df[col], errors="coerce").fillna(0) >= 5.0)
    if not masks:
        return pd.DataFrame()
    any_prot = masks[0]
    for m in masks[1:]:
        any_prot = any_prot | m
    cols = [
        c for c in (
            "grid_id", "utm", "ecorregion", "clase_modal", "tipo_muestra",
            "grid_mode", "split", "modo_tratamiento", "clase_objetivo_nombre",
            "pool_origen", "review_tier", "valid_area_pct", "transition_pct",
        )
        if c in df.columns
    ]
    for cid in CLASES_PROTEGIDAS:
        c = f"pct_{cid}"
        if c in df.columns:
            cols.append(c)
    return df.loc[any_prot, cols].copy()
