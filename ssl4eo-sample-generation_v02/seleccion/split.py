"""Split train/val/test por cluster dentro de cada ecorregión."""

from __future__ import annotations

import logging

import pandas as pd

from config import params_seleccion as P
from seleccion.balanceo import asignar_split_por_cluster, ids_cluster_espacial, verificar_split_clusters


def aplicar_split_ecorregion(
    df: pd.DataFrame,
    eco_id: int,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, bool]:
    """Asigna split; retorna (df, split_inviable)."""
    if df.empty:
        return df, False

    out = df.copy()
    censo_mask = out.get("modo_tratamiento", pd.Series("", index=out.index)).astype(str) == "censo"

    meta: dict = {}
    if P.CENSO_PARTICIPA_SPLIT:
        trabajo = out
    else:
        out.loc[censo_mask, "split"] = "train"
        out.loc[censo_mask, "motivo_split"] = "censo"
        trabajo = out[~censo_mask].copy()

    if not trabajo.empty:
        trabajo = trabajo.copy()
        splits = asignar_split_por_cluster(
            trabajo,
            seed=P.RANDOM_SEED + eco_id,
            train_frac=P.SPLIT_PROPORCIONES["train"],
            val_frac=P.SPLIT_PROPORCIONES["val"],
            test_frac=P.SPLIT_PROPORCIONES["test"],
        )
        meta: dict = {}
        trabajo["split"] = splits
        trabajo["motivo_split"] = "cluster"
        if P.CENSO_PARTICIPA_SPLIT:
            out = trabajo
        else:
            out = pd.concat([out[censo_mask], trabajo], ignore_index=True)

    tmp = out.copy()
    tmp["_cluster_id"] = ids_cluster_espacial(tmp)
    val_clusters = tmp.loc[tmp["split"] == "val", "_cluster_id"].nunique()
    test_clusters = tmp.loc[tmp["split"] == "test", "_cluster_id"].nunique()
    min_val = P.SPLIT_MIN_CLUSTERS.get("val", 2)
    min_test = P.SPLIT_MIN_CLUSTERS.get("test", 2)
    n_train = int((tmp["split"] == "train").sum())
    n_tot = len(tmp)
    pct_train = n_train / max(n_tot, 1)

    inviable_min = bool(n_tot > 0 and (val_clusters < min_val or test_clusters < min_test))
    inviable_techo = bool(meta.get("techo_incompatible", False))
    inviable_train = bool(n_tot > 0 and pct_train < P.SPLIT_MIN_PCT_TRAIN)
    inviable = inviable_min or inviable_techo or inviable_train

    out["split_inviable"] = inviable
    if inviable:
        motivos = []
        if inviable_min:
            motivos.append(f"clusters val={val_clusters} test={test_clusters} (mín {min_val}/{min_test})")
        if inviable_techo:
            motivos.append("mínimo↔techo incompatible")
        if inviable_train:
            motivos.append(f"pct_train={pct_train:.1%} < {P.SPLIT_MIN_PCT_TRAIN:.0%}")
        logger.warning("  Eco %d: split_inviable (%s)", eco_id, "; ".join(motivos))
    elif pct_train < P.SPLIT_MIN_PCT_TRAIN:
        logger.warning(
            "  Eco %d: pct_train=%.1f%% bajo SPLIT_MIN_PCT_TRAIN=%.0f%%",
            eco_id,
            100 * pct_train,
            100 * P.SPLIT_MIN_PCT_TRAIN,
        )

    stats = verificar_split_clusters(out, "split")
    logger.info(
        "  Eco %d split: train=%d (%.0f%%) val=%d test=%d fugas=%d",
        eco_id,
        n_train,
        100 * pct_train,
        int((out["split"] == "val").sum()),
        int((out["split"] == "test").sum()),
        stats["leak_pairs"],
    )
    return out, inviable
