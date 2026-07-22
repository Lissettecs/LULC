"""Vectorized per-segment statistics from segment and C2 rasters."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SegmentStats:
    segment_ids: np.ndarray
    n_total: np.ndarray
    n_valid: np.ndarray
    label_mode: np.ndarray
    count_mode: np.ndarray
    purity: np.ndarray
    coverage: np.ndarray


def compute_segment_stats(
    segments: np.ndarray,
    c2: np.ndarray,
    c2_nodata: list[int],
    background_id: int = 0,
) -> SegmentStats:
    """Compute majority-class statistics for every segment in one pass."""
    seg = segments.ravel().astype(np.int64, copy=False)
    lc = c2.ravel().astype(np.int64, copy=False)

    foreground = seg != background_id
    if not foreground.any():
        raise ValueError("No foreground segments found (all pixels are background).")

    seg_fg = seg[foreground]
    segment_ids, seg_idx = np.unique(seg_fg, return_inverse=True)
    k = segment_ids.size

    n_total = np.bincount(seg_idx, minlength=k).astype(np.int64)

    valid_mask = foreground & ~np.isin(lc, c2_nodata)
    seg_idx_valid = np.searchsorted(segment_ids, seg[valid_mask])
    n_valid = np.bincount(seg_idx_valid, minlength=k).astype(np.int64)

    classes = np.unique(lc[valid_mask])
    if classes.size == 0:
        label_mode = np.zeros(k, dtype=np.int64)
        count_mode = np.zeros(k, dtype=np.int64)
    else:
        counts = np.zeros((k, classes.size), dtype=np.int64)
        lc_valid = lc[valid_mask]

        for j, cls in enumerate(classes):
            cls_mask = lc_valid == cls
            counts[:, j] = np.bincount(seg_idx_valid[cls_mask], minlength=k)

        best_j = np.argmax(counts, axis=1)
        count_mode = counts[np.arange(k), best_j]
        label_mode = classes[best_j]

    with np.errstate(divide="ignore", invalid="ignore"):
        purity = np.where(n_valid > 0, count_mode / n_valid, 0.0).astype(np.float64)
        coverage = np.where(n_total > 0, n_valid / n_total, 0.0).astype(np.float64)

    assert purity.shape[0] == k
    assert np.all((purity >= 0.0) & (purity <= 1.0))
    assert np.all(n_valid <= n_total)

    return SegmentStats(
        segment_ids=segment_ids,
        n_total=n_total,
        n_valid=n_valid,
        label_mode=label_mode,
        count_mode=count_mode,
        purity=purity,
        coverage=coverage,
    )
