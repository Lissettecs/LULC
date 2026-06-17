"""
Utilidades de balanceo para seleccion_rectangulos.py (piloto nacional v2).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

OTRA_SIN_VEG_ID = 25
PASTIZAL_MODE_ID = 15
WATER_MODE_ID = 33
ARID_ECO_IDS = {1, 2, 3, 4, 5}
DESERT_ECOS_BLOCK_OTRA = {1, 2, 3}
FRAGILE_ECOS = {3, 6}


def infer_utm_zone(*paths) -> int | None:
    names = " ".join(str(p).upper() for p in paths if p)
    if "UTM18" in names:
        return 18
    if "UTM19" in names:
        return 19
    return None


def modal_cap_for_zone(utm_zone: int | None) -> int:
    if utm_zone == 18:
        return 14
    if utm_zone == 19:
        return 32
    return 22


def is_otra_sin_vegetacion_exempt(row: pd.Series) -> bool:
    rare = str(row.get("target_rare_class", "") or "").strip()
    if rare:
        return True
    eco = int(row.get("eco_dom_id", -9999) or -9999)
    if eco in {7, 8, 9, 12, 15}:
        return True
    mode = int(row.get("lulc_mode_id", -9999) or -9999)
    if mode in (23, 61, 3):
        return True
    nfor = float(row.get("north_forest_pct", 0) or 0)
    if nfor >= 5:
        return True
    return False


def apply_modal_class_cap(
    df: pd.DataFrame,
    class_id: int,
    max_n: int,
    *,
    exempt_fn=None,
) -> pd.DataFrame:
    """Limita rectangulos con clase modal class_id; conserva exentos primero."""
    if df.empty or max_n <= 0:
        return df.iloc[0:0].copy()
    exempt_fn = exempt_fn or (lambda _r: False)
    mode = pd.to_numeric(df.get("lulc_mode_id", -9999), errors="coerce").fillna(-9999).astype(int)
    hit = df[mode == class_id].copy()
    if len(hit) <= max_n:
        return df
    other = df[mode != class_id].copy()
    hit["_exempt"] = hit.apply(exempt_fn, axis=1)
    keep_exempt = hit[hit["_exempt"]].drop(columns="_exempt", errors="ignore")
    rest = hit[~hit["_exempt"]].drop(columns="_exempt", errors="ignore")
    budget = max(0, max_n - len(keep_exempt))
    if budget > 0 and not rest.empty:
        score_cols = [c for c in ("rare_presence_pct", "lulc_mode_pct", "max_stab_run") if c in rest.columns]
        if score_cols:
            rest = rest.sort_values(score_cols, ascending=[False] * len(score_cols))
        keep_rest = rest.head(budget)
    else:
        keep_rest = rest.iloc[0:0]
    kept = pd.concat([other, keep_exempt, keep_rest], ignore_index=True)
    return kept


def arid_transition_mask(
    df: pd.DataFrame,
    *,
    min_tr: float,
    min_pure: float,
) -> pd.Series:
    """Criterio de transicion relajado para ecorregiones aridas E1-E5."""
    eco = pd.to_numeric(df.get("eco_dom_id", -9999), errors="coerce").fillna(-9999).astype(int)
    tr = pd.to_numeric(df.get("transition_pct", 0), errors="coerce").fillna(0)
    purity = df[["lulc_mode_pct", "lulc_last_pct"]].max(axis=1) if "lulc_last_pct" in df.columns else df.get("lulc_mode_pct", 0)
    mode = pd.to_numeric(df.get("lulc_mode_id", -9999), errors="coerce").fillna(-9999).astype(int)
    last = pd.to_numeric(df.get("lulc_last_id", -9999), errors="coerce").fillna(-9999).astype(int)
    arid = eco.isin(ARID_ECO_IDS)
    standard = (tr >= min_tr) & (purity >= min_pure)
    relaxed = arid & (
        (tr >= max(3.0, min_tr - 2.0))
        | ((mode != last) & (mode > 0) & (last > 0) & (tr >= 3.0))
    )
    return standard | relaxed


def block_desert_otra_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """Evita nuevas muestras desierto desnudo salvo exenciones."""
    if df.empty:
        return df
    eco = pd.to_numeric(df.get("eco_dom_id", -9999), errors="coerce").fillna(-9999).astype(int)
    mode = pd.to_numeric(df.get("lulc_mode_id", -9999), errors="coerce").fillna(-9999).astype(int)
    block = eco.isin(DESERT_ECOS_BLOCK_OTRA) & (mode == OTRA_SIN_VEG_ID)
    exempt = df.apply(is_otra_sin_vegetacion_exempt, axis=1)
    return df[~block | exempt].copy()


def block_water_in_fill(df: pd.DataFrame) -> pd.DataFrame:
    """Evita agregar nuevas muestras modales de agua en pasadas de relleno."""
    if df.empty or "lulc_mode_id" not in df.columns:
        return df
    mode = pd.to_numeric(df["lulc_mode_id"], errors="coerce").fillna(-9999).astype(int)
    rare = df.get("target_rare_class", pd.Series("", index=df.index)).astype(str).str.strip()
    keep = (mode != WATER_MODE_ID) | rare.ne("")
    return df[keep].copy()


def prefer_mixto_score(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    """Prioriza rectangulos mixto 3x3 al empatar score (problema homogeneo/mixto)."""
    if df.empty:
        return df
    out = df.copy()
    gm = out.get("grid_mode", pd.Series("mixto", index=out.index)).astype(str)
    out["_mix_bonus"] = (gm == "mixto").astype(float)
    out = out.sort_values(["_mix_bonus", score_col], ascending=[False, False])
    return out.drop(columns="_mix_bonus", errors="ignore")


def cap_sample_type(
    df: pd.DataFrame,
    sample_type: str,
    max_n: int,
    *,
    score_col: str = "sc_t_s",
) -> pd.DataFrame:
    """Conserva las mejores muestras de un tipo; elimina el resto del set."""
    if df.empty or max_n <= 0:
        return df.iloc[0:0].copy()
    hit = df[df.get("sample_type", "").astype(str) == sample_type].copy()
    if len(hit) <= max_n:
        return df
    rare = hit.get("target_rare_class", pd.Series("", index=hit.index)).astype(str).str.strip()
    keep_rare = hit[rare.ne("")]
    rest = hit[rare.eq("")]
    if score_col in rest.columns:
        rest = rest.sort_values(score_col, ascending=False)
    keep_rest = rest.head(max(0, max_n - len(keep_rare)))
    keep = pd.concat([keep_rare, keep_rest], ignore_index=True)
    drop_ids = set(hit["grid_id"]) - set(keep["grid_id"])
    return df[~df["grid_id"].isin(drop_ids)].copy()


def spatial_cluster_ids(df: pd.DataFrame) -> pd.Series:
    """
    Cluster espacial = componente conexo por vecindad en mgrs_src
    (col_idx/row_idx adyacentes ±1).
    """
    if df.empty:
        return pd.Series(dtype=int)

    mgrs = df.get("mgrs_src", df.get("mgrs_dom", pd.Series("", index=df.index))).astype(str)
    col = pd.to_numeric(df.get("col_idx", -9999), errors="coerce").fillna(-9999).astype(int)
    row = pd.to_numeric(df.get("row_idx", -9999), errors="coerce").fillna(-9999).astype(int)
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

    index_map: dict[tuple[str, int, int], int] = {}
    for i in range(n):
        c, r = int(col.iloc[i]), int(row.iloc[i])
        if c < 0 or r < 0:
            continue
        index_map[(str(mgrs.iloc[i]), c, r)] = i

    for i in range(n):
        m = str(mgrs.iloc[i])
        c, r = int(col.iloc[i]), int(row.iloc[i])
        if c < 0 or r < 0:
            continue
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if dc == 0 and dr == 0:
                    continue
                j = index_map.get((m, c + dc, r + dr))
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


def _assign_split_to_units(
    units: list,
    rng: np.random.Generator,
    *,
    train_frac: float,
    val_frac: float,
    test_frac: float,
    rare_name: str,
    rare_force_holdout: tuple[str, ...],
) -> dict:
    rng.shuffle(units)
    n = len(units)
    if n == 1:
        return {units[0]: "train"}
    if n == 2:
        return {units[0]: "train", units[1]: "val"}
    n_val = max(1, int(round(n * val_frac)))
    n_test = max(1, int(round(n * test_frac)))
    if rare_name in rare_force_holdout and n >= 4:
        n_val = max(n_val, 1)
        n_test = max(n_test, 1)
    elif rare_name in rare_force_holdout and n >= 2:
        n_val = max(n_val, 1)
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
    parts = parts[:n]
    return dict(zip(units, parts))


def assign_cluster_aware_split(
    df: pd.DataFrame,
    *,
    seed: int,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
    rare_force_holdout: tuple[str, ...] = (),
) -> pd.Series:
    """Split estratificado asignado por cluster espacial (evita leakage vecinal)."""
    if df.empty:
        return pd.Series(dtype=str)
    rng = np.random.default_rng(seed)
    work = df.copy()
    work["_cluster_id"] = spatial_cluster_ids(work)
    work["_stratum"] = work.apply(_stratum_key, axis=1)
    split_by_cluster: dict[int, str] = {}

    for stratum, grp in work.groupby("_stratum", group_keys=False):
        cids = sorted(grp["_cluster_id"].unique())
        rare_name = str(stratum)[5:] if str(stratum).startswith("rare:") else ""
        mapping = _assign_split_to_units(
            cids,
            rng,
            train_frac=train_frac,
            val_frac=val_frac,
            test_frac=test_frac,
            rare_name=rare_name,
            rare_force_holdout=rare_force_holdout,
        )
        split_by_cluster.update(mapping)

    return work["_cluster_id"].map(split_by_cluster).fillna("train")


def verify_cluster_split(df: pd.DataFrame, split_col: str = "split") -> dict[str, int]:
    """Cuenta pares vecinos con split distinto (debe ser 0)."""
    if df.empty or split_col not in df.columns:
        return {"neighbor_pairs": 0, "leak_pairs": 0}
    work = df.copy()
    work["_cluster_id"] = spatial_cluster_ids(work)
    mgrs = work.get("mgrs_src", work.get("mgrs_dom", pd.Series("", index=work.index))).astype(str)
    col = pd.to_numeric(work.get("col_idx", -9999), errors="coerce").fillna(-9999).astype(int)
    row = pd.to_numeric(work.get("row_idx", -9999), errors="coerce").fillna(-9999).astype(int)
    pos: dict[tuple[str, int, int], str] = {}
    split_map: dict[tuple[str, int, int], str] = {}
    for idx, r in work.iterrows():
        c, rw = int(col.loc[idx]), int(row.loc[idx])
        if c < 0 or rw < 0:
            continue
        key = (str(mgrs.loc[idx]), c, rw)
        pos[key] = str(r["grid_id"])
        split_map[key] = str(r[split_col])

    leak = 0
    pairs = 0
    for key, gid in pos.items():
        m, c, rw = key
        sp = split_map[key]
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if dc == 0 and dr == 0:
                    continue
                nk = (m, c + dc, rw + dr)
                if nk in split_map:
                    pairs += 1
                    if split_map[nk] != sp:
                        leak += 1
    return {"neighbor_pairs": pairs, "leak_pairs": leak // 2}


def build_ecoregion_reserves(
    selected: pd.DataFrame,
    candidates: pd.DataFrame,
    used_ids: set[str],
    *,
    eco_ids: set[int],
    n_reserve: int,
    score_col: str = "sc_e_s",
) -> pd.DataFrame:
    """Candidatos suplentes para ecorregiones fragiles (E3, E6)."""
    if n_reserve <= 0 or candidates.empty:
        return pd.DataFrame()

    selected_counts = selected.groupby("eco_dom_id").size().to_dict() if not selected.empty else {}
    free = candidates[~candidates["grid_id"].isin(used_ids)].copy()
    free = block_desert_otra_candidates(free)
    free = block_water_in_fill(free)
    if free.empty:
        return pd.DataFrame()

    if score_col not in free.columns:
        score_col = "sc_e_s" if "sc_e_s" in free.columns else free.columns[0]
    free = prefer_mixto_score(free, score_col)

    parts: list[pd.DataFrame] = []
    for eco_id in sorted(eco_ids):
        if selected_counts.get(eco_id, 0) > 6:
            continue
        pool = free[free["eco_dom_id"].astype(int) == eco_id].head(n_reserve).copy()
        if pool.empty:
            continue
        pool["sample_role"] = "reserva_eco"
        pool["reserve_for_eco_id"] = eco_id
        parts.append(pool)

    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def _stratum_key(row: pd.Series) -> str:
    rare = str(row.get("target_rare_class", "") or "").strip()
    if rare:
        return f"rare:{rare}"
    st = str(row.get("sample_type", "tipo"))
    eco = int(row.get("eco_dom_id", -1) or -1)
    return f"{st}|eco:{eco}"


def assign_stratified_split(
    df: pd.DataFrame,
    *,
    seed: int,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
    rare_force_holdout: tuple[str, ...] = (),
) -> pd.Series:
    """Split estratificado por tipo, ecorregion y clase critica dedicada."""
    if df.empty:
        return pd.Series(dtype=str)
    rng = np.random.default_rng(seed)
    split_by_gid: dict[str, str] = {}
    keys = df.apply(_stratum_key, axis=1)

    for stratum, grp in df.groupby(keys, group_keys=False):
        gids = list(grp["grid_id"].unique())
        rng.shuffle(gids)
        n = len(gids)
        rare_name = str(stratum)[5:] if str(stratum).startswith("rare:") else ""

        if n == 1:
            mapping = {gids[0]: "train"}
        elif n == 2:
            mapping = {gids[0]: "train", gids[1]: "val"}
        else:
            n_val = max(1, int(round(n * val_frac)))
            n_test = max(1, int(round(n * test_frac)))
            if rare_name in rare_force_holdout and n >= 4:
                n_val = max(n_val, 1)
                n_test = max(n_test, 1)
            elif rare_name in rare_force_holdout and n >= 2:
                n_val = max(n_val, 1)
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
            parts = parts[:n]
            mapping = dict(zip(gids, parts))
        split_by_gid.update(mapping)

    return df["grid_id"].map(split_by_gid).fillna("train")


def take_non_overlapping_rows(
    free: pd.DataFrame,
    n: int,
    spatial_tracker=None,
) -> pd.DataFrame:
    """Toma hasta n filas de free sin solape con spatial_tracker."""
    if n <= 0 or free.empty:
        return free.iloc[0:0]
    rows: list[pd.Series] = []
    for _, row in free.iterrows():
        one = pd.DataFrame([row])
        if spatial_tracker is not None and spatial_tracker.filter(one).empty:
            continue
        rows.append(row)
        if spatial_tracker is not None:
            spatial_tracker.register(one)
        if len(rows) >= n:
            break
    return pd.DataFrame(rows) if rows else free.iloc[0:0]


def fill_ecoregion_quotas(
    selected: pd.DataFrame,
    candidates: pd.DataFrame,
    used_ids: set[str],
    *,
    min_per_eco: int,
    priority_ecos: set[int],
    max_add: int,
    score_col: str = "sc_e_h",
    spatial_tracker=None,
) -> tuple[pd.DataFrame, set[str]]:
    """Segunda pasada: sube ecorregiones deficitarias con candidatos libres."""
    if max_add <= 0 or candidates.empty:
        return selected, used_ids

    selected = selected.copy()
    added_parts: list[pd.DataFrame] = []
    n_added = 0

    eco_counts = selected.groupby("eco_dom_id").size().to_dict() if not selected.empty else {}
    free = candidates[~candidates["grid_id"].isin(used_ids)].copy()
    free = block_desert_otra_candidates(free)
    free = block_water_in_fill(free)
    if free.empty:
        return selected, used_ids

    if score_col not in free.columns:
        free["_score"] = 1.0
        score_col = "_score"

    def temporal_bucket(row: pd.Series) -> str:
        tr = float(row.get("transition_pct", 0) or 0)
        if tr >= 8:
            return "transicion"
        best_p = None
        for p in ("P4", "P3", "P2", "P1"):
            if float(row.get(f"n_stb_{p}", 0) or 0) >= 2:
                best_p = p
                break
        return "anual" if best_p else "estable"

    eco_order = sorted(
        set(priority_ecos) | set(free["eco_dom_id"].astype(int).unique()),
        key=lambda e: (0 if e in priority_ecos else 1, eco_counts.get(e, 0)),
    )

    for eco_id in eco_order:
        if n_added >= max_add:
            break
        need = max(0, min_per_eco - eco_counts.get(eco_id, 0))
        if need <= 0:
            continue

        eco_sel = selected[selected["eco_dom_id"].astype(int) == eco_id]
        have_temporal = set(eco_sel.get("dim_temporal", pd.Series(dtype=object)).astype(str))
        have_modal = set(
            pd.to_numeric(eco_sel.get("lulc_mode_id", -9999), errors="coerce")
            .fillna(-9999)
            .astype(int)
        )

        pool = free[free["eco_dom_id"].astype(int) == eco_id].copy()
        if pool.empty:
            continue

        pool["_temporal"] = pool.apply(temporal_bucket, axis=1)
        pool["_modal"] = pd.to_numeric(pool.get("lulc_mode_id", -9999), errors="coerce").fillna(-9999).astype(int)
        pool["_prio"] = 0
        pool.loc[~pool["_temporal"].isin(have_temporal), "_prio"] += 2
        pool.loc[~pool["_modal"].isin(have_modal), "_prio"] += 1
        pool.loc[pool["_modal"] == OTRA_SIN_VEG_ID, "_prio"] -= 1
        pool["_mix_bonus"] = (
            pool.get("grid_mode", pd.Series("mixto", index=pool.index)).astype(str) == "mixto"
        ).astype(float)
        pool = pool.sort_values(["_prio", "_mix_bonus", score_col], ascending=[False, False, False])

        take = take_non_overlapping_rows(
            pool.drop(columns=["_temporal", "_modal", "_prio"], errors="ignore"),
            min(need, max_add - n_added),
            spatial_tracker,
        ).copy()
        if take.empty:
            continue

        for _, row in take.iterrows():
            tr = float(row.get("transition_pct", 0) or 0)
            if tr >= 8:
                st, dt, ds = "transicion_simple_media", "transicion", "simple_media"
            elif temporal_bucket(row) == "anual":
                st, dt, ds = "anual_simple_media", "anual", "simple_media"
            else:
                st, dt, ds = "estable_simple_media", "estable", "simple_media"
            take.loc[row.name, "sample_type"] = st
            take.loc[row.name, "dim_temporal"] = dt
            take.loc[row.name, "dim_espacial"] = ds

        take["target_rare_class"] = ""
        take["target_rare_class_id"] = -9999
        if "review_tier" not in take.columns:
            take["review_tier"] = 2
        else:
            take["review_tier"] = 2

        added_parts.append(take)
        used_ids |= set(take["grid_id"].tolist())
        eco_counts[eco_id] = eco_counts.get(eco_id, 0) + len(take)
        n_added += len(take)

    if added_parts:
        selected = pd.concat([selected] + added_parts, ignore_index=True)
    return selected, used_ids


def infer_fill_sample_type(row: pd.Series) -> tuple[str, str, str]:
    tr = float(row.get("transition_pct", 0) or 0)
    if tr >= 8:
        return "transicion_simple_media", "transicion", "simple_media"
    for p in ("P4", "P3", "P2", "P1"):
        if float(row.get(f"n_stb_{p}", 0) or 0) >= 2:
            gm = str(row.get("grid_mode", "mixto"))
            if gm == "mixto":
                return "anual_simple_media", "anual", "simple_media"
            return "anual_homogenea", "anual", "homogenea"
    gm = str(row.get("grid_mode", "mixto"))
    if gm == "homogeneo":
        return "estable_homogenea", "estable", "homogenea"
    return "estable_simple_media", "estable", "simple_media"


def fill_to_total_target(
    selected: pd.DataFrame,
    candidates: pd.DataFrame,
    used_ids: set[str],
    *,
    target_n: int,
    score_col: str = "sc_e_s",
    spatial_tracker=None,
) -> tuple[pd.DataFrame, set[str]]:
    """Tercera pasada: completa hasta target_n con candidatos generales libres."""
    if candidates.empty or len(selected) >= target_n:
        return selected, used_ids

    need = target_n - len(selected)
    free = candidates[~candidates["grid_id"].isin(used_ids)].copy()
    free = block_desert_otra_candidates(free)
    free = block_water_in_fill(free)
    if free.empty:
        return selected, used_ids

    if score_col not in free.columns:
        for alt in ("sc_e_s", "sc_a_s", "sc_t_s", "sc_e_h"):
            if alt in free.columns:
                score_col = alt
                break
        else:
            free["_score"] = 1.0
            score_col = "_score"

    free = prefer_mixto_score(free, score_col)
    take = take_non_overlapping_rows(free, need, spatial_tracker).copy()
    types, dims_t, dims_s = [], [], []
    for _, row in take.iterrows():
        st, dt, ds = infer_fill_sample_type(row)
        types.append(st)
        dims_t.append(dt)
        dims_s.append(ds)
    take["sample_type"] = types
    take["dim_temporal"] = dims_t
    take["dim_espacial"] = dims_s
    take["target_rare_class"] = ""
    take["target_rare_class_id"] = -9999
    take["review_tier"] = 2
    take["ref_period"] = ""
    take["ref_year"] = -9999
    take["ref_sensor"] = ""

    used_ids |= set(take["grid_id"].tolist())
    selected = pd.concat([selected, take], ignore_index=True)
    return selected, used_ids
