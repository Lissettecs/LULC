"""Balanceo espacial y relleno — adaptado de v1."""

from __future__ import annotations

import numpy as np
import pandas as pd

from seleccion.tracker import deduplicar_espacial

OTRA_SIN_VEG_ID = 25
ARID_ECO_IDS = {1, 2, 3, 4, 5}
DESERT_ECOS_BLOCK_OTRA = {1, 2, 3}
MAINLAND_ECO_IDS = frozenset(range(1, 16))


def alternar_mgrs(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    if df.empty or "mgrs_dom" not in df.columns:
        return df.sort_values(score_col, ascending=False)
    work = df.sort_values(score_col, ascending=False).copy()
    work["_mgrs_rank"] = work.groupby("mgrs_dom", sort=False).cumcount()
    return work.sort_values(["_mgrs_rank", score_col], ascending=[True, False]).drop(
        columns="_mgrs_rank"
    )


def mascara_transicion_arida(df: pd.DataFrame, *, min_tr: float, min_pure: float) -> pd.Series:
    eco = pd.to_numeric(df.get("eco_dom_id", -9999), errors="coerce").fillna(-9999).astype(int)
    tr = pd.to_numeric(df.get("transition_pct", 0), errors="coerce").fillna(0)
    purity = df[["lulc_mode_pct", "lulc_last_pct"]].max(axis=1)
    mode = pd.to_numeric(df.get("lulc_mode_id", -9999), errors="coerce").fillna(-9999).astype(int)
    last = pd.to_numeric(df.get("lulc_last_id", -9999), errors="coerce").fillna(-9999).astype(int)
    arid = eco.isin(ARID_ECO_IDS)
    standard = (tr >= min_tr) & (purity >= min_pure)
    relaxed = arid & (
        (tr >= max(3.0, min_tr - 2.0))
        | ((mode != last) & (mode > 0) & (last > 0) & (tr >= 3.0))
    )
    return standard | relaxed


def bloquear_otra_desierto(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    eco = pd.to_numeric(df.get("eco_dom_id", -9999), errors="coerce").fillna(-9999).astype(int)
    mode = pd.to_numeric(df.get("lulc_mode_id", -9999), errors="coerce").fillna(-9999).astype(int)
    block = eco.isin(DESERT_ECOS_BLOCK_OTRA) & (mode == OTRA_SIN_VEG_ID)
    return df[~block].copy()


def ids_cluster_espacial(df: pd.DataFrame) -> pd.Series:
    """Clusters 8-conectados por mgrs + rect_side (2x2 y 3x3 no se mezclan)."""
    if df.empty:
        return pd.Series(dtype=int)
    mgrs = df.get("mgrs_dom", pd.Series("", index=df.index)).astype(str)
    col = pd.to_numeric(df.get("col_idx", -9999), errors="coerce").fillna(-9999).astype(int)
    row = pd.to_numeric(df.get("row_idx", -9999), errors="coerce").fillna(-9999).astype(int)
    side = pd.to_numeric(df.get("rect_side", 0), errors="coerce").fillna(0).astype(int)
    if (side == 0).all() and "grid_mode" in df.columns:
        side = df["grid_mode"].map({"homogeneo": 2, "mixto": 3}).fillna(0).astype(int)
    n = len(df)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    index_map: dict[tuple[str, int, int, int], int] = {}
    for i in range(n):
        c, r = int(col.iloc[i]), int(row.iloc[i])
        if c < 0 or r < 0:
            continue
        index_map[(str(mgrs.iloc[i]), int(side.iloc[i]), c, r)] = i

    for i in range(n):
        m = str(mgrs.iloc[i])
        sd = int(side.iloc[i])
        c, r = int(col.iloc[i]), int(row.iloc[i])
        if c < 0 or r < 0:
            continue
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if dc == 0 and dr == 0:
                    continue
                j = index_map.get((m, sd, c + dc, r + dr))
                if j is not None:
                    union(i, j)

    root_to_label: dict[int, int] = {}
    labels: list[int] = []
    next_label = 0
    for i in range(n):
        root = find(i)
        if root not in root_to_label:
            root_to_label[root] = next_label
            next_label += 1
        labels.append(root_to_label[root])
    return pd.Series(labels, index=df.index)


def _asignar_split_unidades(
    unidades: list,
    rng: np.random.Generator,
    *,
    train_frac: float,
    val_frac: float,
    test_frac: float,
) -> dict:
    rng.shuffle(unidades)
    n = len(unidades)
    if n == 1:
        return {unidades[0]: "train"}
    if n == 2:
        return {unidades[0]: "train", unidades[1]: "val"}
    n_val = max(1, int(round(n * val_frac)))
    n_test = max(1, int(round(n * test_frac)))
    n_train = max(1, n - n_val - n_test)
    while n_train + n_val + n_test > n:
        if n_train > 1:
            n_train -= 1
        elif n_val > 1:
            n_val -= 1
        elif n_test > 1:
            n_test -= 1
        else:
            break
    parts = (["train"] * n_train) + (["val"] * n_val) + (["test"] * n_test)
    while len(parts) < n:
        parts.append("train")
    return dict(zip(unidades, parts[:n]))


def asignar_split_por_cluster(
    df: pd.DataFrame,
    *,
    seed: int,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=str)
    rng = np.random.default_rng(seed)
    work = df.copy()
    work["_cluster_id"] = ids_cluster_espacial(work)
    split_por_cluster: dict[int, str] = {}
    for _, grp in work.groupby(["sample_type", "lulc_mode_id"], dropna=False):
        cids = sorted(grp["_cluster_id"].unique())
        split_por_cluster.update(
            _asignar_split_unidades(cids, rng, train_frac=train_frac, val_frac=val_frac, test_frac=test_frac)
        )
    return work["_cluster_id"].map(split_por_cluster).fillna("train")


def verificar_split_clusters(df: pd.DataFrame, split_col: str = "split") -> dict[str, int]:
    """Cuenta pares vecinos (mismo mgrs, mismo rect_side) con split distinto."""
    if df.empty or split_col not in df.columns:
        return {"neighbor_pairs": 0, "leak_pairs": 0}
    work = df.copy()
    mgrs = work.get("mgrs_dom", pd.Series("", index=work.index)).astype(str)
    col = pd.to_numeric(work.get("col_idx", -9999), errors="coerce").fillna(-9999).astype(int)
    row = pd.to_numeric(work.get("row_idx", -9999), errors="coerce").fillna(-9999).astype(int)
    side = pd.to_numeric(work.get("rect_side", 0), errors="coerce").fillna(0).astype(int)
    split_map: dict[tuple[str, int, int, int], str] = {}
    for idx, r in work.iterrows():
        c, rw = int(col.loc[idx]), int(row.loc[idx])
        if c < 0 or rw < 0:
            continue
        split_map[(str(mgrs.loc[idx]), int(side.loc[idx]), c, rw)] = str(r[split_col])
    leak = pairs = 0
    for key, sp in split_map.items():
        m, sd, c, rw = key
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if dc == 0 and dr == 0:
                    continue
                nk = (m, sd, c + dc, rw + dr)
                if nk in split_map:
                    pairs += 1
                    if split_map[nk] != sp:
                        leak += 1
    return {"neighbor_pairs": pairs, "leak_pairs": leak // 2}


def corregir_fugas_split(df: pd.DataFrame, split_col: str = "split") -> pd.DataFrame:
    """
    Unifica split entre vecinos espaciales dentro de cada ecorregión.
    Preferencia: resolver hacia train para no inventar val/test.
    """
    if df.empty or split_col not in df.columns:
        return df
    out = df.copy()
    eco_col = "eco_dom_id" if "eco_dom_id" in out.columns else None
    if eco_col:
        piezas = [_corregir_fugas_un_grupo(grp, split_col) for _, grp in out.groupby(eco_col, sort=False)]
        return pd.concat(piezas, ignore_index=True) if piezas else out
    return _corregir_fugas_un_grupo(out, split_col)


def _corregir_fugas_un_grupo(df: pd.DataFrame, split_col: str) -> pd.DataFrame:
    out = df.copy()
    for _ in range(64):
        stats = verificar_split_clusters(out, split_col)
        if stats["leak_pairs"] == 0:
            break
        mgrs = out.get("mgrs_dom", pd.Series("", index=out.index)).astype(str)
        col = pd.to_numeric(out.get("col_idx", -9999), errors="coerce").fillna(-9999).astype(int)
        row = pd.to_numeric(out.get("row_idx", -9999), errors="coerce").fillna(-9999).astype(int)
        side = pd.to_numeric(out.get("rect_side", 0), errors="coerce").fillna(0).astype(int)
        if (side == 0).all() and "grid_mode" in out.columns:
            side = out["grid_mode"].map({"homogeneo": 2, "mixto": 3}).fillna(0).astype(int)
        split_map: dict[tuple[str, int, int, int], int] = {}
        for idx in out.index:
            c, rw = int(col.loc[idx]), int(row.loc[idx])
            if c < 0 or rw < 0:
                continue
            split_map[(str(mgrs.loc[idx]), int(side.loc[idx]), c, rw)] = idx
        cambios = 0
        for key, idx in list(split_map.items()):
            m, sd, c, rw = key
            sp = str(out.at[idx, split_col])
            for dc in (-1, 0, 1):
                for dr in (-1, 0, 1):
                    if dc == 0 and dr == 0:
                        continue
                    j = split_map.get((m, sd, c + dc, rw + dr))
                    if j is None:
                        continue
                    sp2 = str(out.at[j, split_col])
                    if sp2 == sp:
                        continue
                    nuevo = "train"
                    if sp != nuevo:
                        out.at[idx, split_col] = nuevo
                        cambios += 1
                    if sp2 != nuevo:
                        out.at[j, split_col] = nuevo
                        cambios += 1
        if cambios == 0:
            break
    return out


def seleccionar_top(
    df: pd.DataFrame,
    group_cols: list[str],
    n: int,
    sample_type: str,
    dim_t: str,
    dim_s: str,
    *,
    score_col: str = "score",
    tier: int = 2,
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = (
        df.sort_values(score_col, ascending=False)
        .groupby(group_cols, group_keys=False)
        .head(n)
        .copy()
    )
    out["sample_type"] = sample_type
    out["dim_temporal"] = dim_t
    out["dim_espacial"] = dim_s
    out["review_tier"] = tier
    return out
