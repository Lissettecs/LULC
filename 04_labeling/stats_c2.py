"""C2 labeling statistics per segment."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from config.c2_classes import CLASES_TIER_PROTEGIDO, C2_NODATA, class_name


@dataclass(frozen=True)
class LabelStats:
    segment_ids: np.ndarray
    area_px: np.ndarray
    n_valid: np.ndarray
    mode_class: np.ndarray
    proportion: np.ndarray
    class_2: np.ndarray
    proportion_2: np.ndarray
    class_3: np.ndarray
    proportion_3: np.ndarray
    n_classes: np.ndarray
    has_protected: np.ndarray


def _top3_distribution(p1: float, p2: float, p3: float) -> str:
    return f"{p1:.0f}/{p2:.0f}/{p3:.0f}"


def compute_c2_stats(
    segments: np.ndarray,
    c2: np.ndarray,
    c2_nodata: frozenset[int] = C2_NODATA,
    protected_classes: frozenset[int] = CLASES_TIER_PROTEGIDO,
    background_id: int = 0,
) -> LabelStats:
    seg = segments.ravel().astype(np.int64, copy=False)
    lc = c2.ravel().astype(np.int64, copy=False)

    foreground = seg != background_id
    if not foreground.any():
        raise ValueError("No segments in raster (all background).")

    seg_fg = seg[foreground]
    segment_ids = np.unique(seg_fg)
    k = segment_ids.size
    seg_idx_all = np.searchsorted(segment_ids, seg_fg)

    area_px = np.bincount(seg_idx_all, minlength=k).astype(np.int64)

    valid_lc = foreground & ~np.isin(lc, list(c2_nodata))
    if not valid_lc.any():
        raise ValueError("No valid C2 pixels under segments.")

    seg_v = seg[valid_lc]
    lc_v = lc[valid_lc]
    seg_idx = np.searchsorted(segment_ids, seg_v)

    classes = np.unique(lc_v)
    nc = classes.size
    counts = np.zeros((k, nc), dtype=np.int64)
    for j, cls in enumerate(classes):
        counts[:, j] = np.bincount(seg_idx[lc_v == cls], minlength=k)

    n_valid = counts.sum(axis=1).astype(np.int64)

    # Top-3 classes by pixel count within each segment
    work = counts.copy()
    rank_j = np.full((k, 3), -1, dtype=np.int64)
    rank_count = np.zeros((k, 3), dtype=np.int64)
    for r in range(3):
        if nc == 0:
            break
        best = np.argmax(work, axis=1)
        best_count = work[np.arange(k), best]
        has = best_count > 0
        rank_j[has, r] = best[has]
        rank_count[has, r] = best_count[has]
        work[np.arange(k)[has], best[has]] = -1

    mode_class = np.zeros(k, dtype=np.int64)
    class_2 = np.zeros(k, dtype=np.int64)
    class_3 = np.zeros(k, dtype=np.int64)
    m0 = rank_j[:, 0] >= 0
    m1 = rank_j[:, 1] >= 0
    m2 = rank_j[:, 2] >= 0
    mode_class[m0] = classes[rank_j[m0, 0]]
    class_2[m1] = classes[rank_j[m1, 1]]
    class_3[m2] = classes[rank_j[m2, 2]]

    with np.errstate(divide="ignore", invalid="ignore"):
        proportion = np.where(n_valid > 0, 100.0 * rank_count[:, 0] / n_valid, 0.0)
        proportion_2 = np.where(n_valid > 0, 100.0 * rank_count[:, 1] / n_valid, 0.0)
        proportion_3 = np.where(n_valid > 0, 100.0 * rank_count[:, 2] / n_valid, 0.0)
    proportion_2[~m1] = 0.0
    proportion_3[~m2] = 0.0

    n_classes = (counts > 0).sum(axis=1).astype(np.int64)

    prot_cols = [j for j, cls in enumerate(classes) if int(cls) in protected_classes]
    if prot_cols:
        has_protected = counts[:, prot_cols].sum(axis=1) > 0
    else:
        has_protected = np.zeros(k, dtype=bool)

    return LabelStats(
        segment_ids=segment_ids,
        area_px=area_px,
        n_valid=n_valid,
        mode_class=mode_class.astype(np.int64),
        proportion=proportion.astype(np.float64),
        class_2=class_2.astype(np.int64),
        proportion_2=proportion_2.astype(np.float64),
        class_3=class_3.astype(np.int64),
        proportion_3=proportion_3.astype(np.float64),
        n_classes=n_classes,
        has_protected=has_protected,
    )


# Backward-compatible aliases
calcular_stats_c2 = compute_c2_stats


def stats_to_dataframe(stats: LabelStats) -> pd.DataFrame:
    rows = []
    for i in range(stats.segment_ids.size):
        sid = int(stats.segment_ids[i])
        p1 = float(stats.proportion[i])
        p2 = float(stats.proportion_2[i])
        p3 = float(stats.proportion_3[i])
        c1 = int(stats.mode_class[i])
        c2 = int(stats.class_2[i])
        c3 = int(stats.class_3[i])
        rows.append(
            {
                "segment_id": sid,
                "area_px": int(stats.area_px[i]),
                "n_valid_c2": int(stats.n_valid[i]),
                "mode_class": c1,
                "mode_class_name": class_name(c1),
                "proportion": round(p1, 2),
                "class_2": c2,
                "class_2_name": class_name(c2) if c2 else "",
                "proportion_2": round(p2, 2),
                "class_3": c3,
                "class_3_name": class_name(c3) if c3 else "",
                "proportion_3": round(p3, 2),
                "n_classes": int(stats.n_classes[i]),
                "has_protected": bool(stats.has_protected[i]),
                "top3_distribution": _top3_distribution(p1, p2, p3),
            }
        )
    return pd.DataFrame(rows).sort_values("segment_id").reset_index(drop=True)


stats_a_dataframe = stats_to_dataframe
