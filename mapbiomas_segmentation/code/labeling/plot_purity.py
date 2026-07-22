"""Purity histogram for tau calibration (phase 1)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from segmentation_labels.stats import SegmentStats

PERCENTILE_NAMES = ("p10", "p25", "p50", "p75", "p90")


def compute_purity_percentiles(
    stats: SegmentStats,
    *,
    n_min_pixels: int,
) -> dict[str, float]:
    """Return purity percentiles for segments with enough valid C2 pixels."""
    mask = stats.n_valid >= n_min_pixels
    purity = stats.purity[mask]
    if purity.size == 0:
        raise ValueError("No segments meet N_MIN_PIXELS for the purity histogram.")
    values = np.percentile(purity, [10, 25, 50, 75, 90])
    return {name: float(v) for name, v in zip(PERCENTILE_NAMES, values)}


def plot_purity_histogram(
    stats: SegmentStats,
    out_path: Path,
    *,
    n_min_pixels: int,
    n_bins: int = 50,
    percentiles_json: Path | None = None,
) -> dict[str, float]:
    """Save unweighted and area-weighted purity histograms."""
    mask = stats.n_valid >= n_min_pixels
    purity = stats.purity[mask]
    weights = stats.n_total[mask].astype(np.float64)

    pct = compute_purity_percentiles(stats, n_min_pixels=n_min_pixels)
    print("Purity percentiles (segments with n_valid >= N_MIN_PIXELS):")
    for name in PERCENTILE_NAMES:
        print(f"  {name}: {pct[name]:.4f}")

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(purity, bins=n_bins, alpha=0.6, label="segment count", density=True)
    ax.hist(
        purity,
        bins=n_bins,
        weights=weights,
        alpha=0.6,
        histtype="step",
        linewidth=2,
        label="area-weighted",
        density=True,
    )
    ax.set_xlabel("Purity (mode count / valid pixels)")
    ax.set_ylabel("Density")
    ax.set_title("Segment purity distribution")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Saved purity histogram: {out_path}")

    if percentiles_json is not None:
        percentiles_json.parent.mkdir(parents=True, exist_ok=True)
        percentiles_json.write_text(json.dumps(pct, indent=2), encoding="utf-8")
        print(f"Saved purity percentiles: {percentiles_json}")

    return pct
