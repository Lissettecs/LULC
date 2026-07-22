"""Threshold-based label assignment per segment."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from segmentation_labels.stats import SegmentStats


@dataclass(frozen=True)
class AssignmentResult:
    label_final: np.ndarray
    valid: np.ndarray
    reason: np.ndarray


def assign_labels(
    stats: SegmentStats,
    *,
    tau_purity: float,
    kappa_coverage: float,
    n_min_pixels: int,
    label_mixed: int,
    label_nodata: int,
) -> AssignmentResult:
    """Assign final C2 labels using purity and coverage thresholds."""
    n = stats.segment_ids.size
    label_final = np.empty(n, dtype=np.int64)
    valid = np.zeros(n, dtype=bool)
    reason = np.empty(n, dtype=object)

    no_data = (stats.n_valid < n_min_pixels) | (stats.coverage < kappa_coverage)
    mixed = ~no_data & (stats.purity < tau_purity)
    ok = ~no_data & ~mixed

    label_final[no_data] = label_nodata
    valid[no_data] = False
    reason[no_data] = "no_data"

    label_final[mixed] = label_mixed
    valid[mixed] = False
    reason[mixed] = "mixed"

    label_final[ok] = stats.label_mode[ok]
    valid[ok] = True
    reason[ok] = "ok"

    assert reason.size == n
    assert np.isin(reason, ["ok", "mixed", "no_data"]).all()
    assert (ok.sum() + mixed.sum() + no_data.sum()) == n

    return AssignmentResult(
        label_final=label_final,
        valid=valid,
        reason=reason,
    )


def print_assignment_summary(reason: np.ndarray) -> None:
    """Print segment counts and percentages by assignment reason."""
    n = reason.size
    for key in ("ok", "mixed", "no_data"):
        count = int((reason == key).sum())
        pct = 100.0 * count / n if n else 0.0
        print(f"  {key:8s}: {count:8d} ({pct:5.1f}%)")
