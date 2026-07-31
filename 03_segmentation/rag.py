"""RAG merge on SLIC superpixels (same logic as seg-labeling)."""

from __future__ import annotations

import numpy as np
from skimage.graph import cut_threshold, rag_mean_color
from skimage.segmentation import relabel_sequential

from config.params_slic import RAG_PERCENTILE

RAG_PERCENTIL = RAG_PERCENTILE  # backward-compatible alias


def _prepare_image(feats: np.ndarray, valid: np.ndarray) -> np.ndarray:
    out = feats.astype(np.float32, copy=True)
    for c in range(out.shape[-1]):
        band = out[..., c]
        median = float(np.median(band[valid])) if np.any(valid) else 0.0
        band[~valid] = median
        out[..., c] = band
    return np.nan_to_num(out, nan=0.0, posinf=1.0, neginf=0.0)


def _edge_weights(g) -> np.ndarray:
    if g.number_of_edges() == 0:
        return np.array([], dtype=np.float64)
    weights = np.array([d["weight"] for _, _, d in g.edges(data=True)], dtype=np.float64)
    return weights[np.isfinite(weights)]


def threshold_from_percentile(weights: np.ndarray, percentile: int) -> float:
    if weights.size == 0:
        raise ValueError("RAG graph has no edges with finite weight")
    thr = float(np.percentile(weights, percentile))
    if not np.isfinite(thr):
        raise ValueError(f"RAG p{percentile} threshold is not finite")
    return thr


def merge_rag_threshold(
    labels_slic: np.ndarray,
    feats: np.ndarray,
    valid: np.ndarray,
    percentile: int = RAG_PERCENTILE,
) -> tuple[np.ndarray, dict]:
    """
    cut_threshold on mean-color RAG (segmentation bands).

    Returns merged labels and stats dict.
    """
    n_slic = len(np.unique(labels_slic[valid]))
    img = _prepare_image(feats, valid)
    g = rag_mean_color(img, labels_slic)
    if 0 in g:
        g.remove_node(0)

    weights = _edge_weights(g)
    thr = threshold_from_percentile(weights, percentile)

    merged = cut_threshold(labels_slic, g, thr).astype(np.int32)
    merged[~valid] = 0
    merged, _, _ = relabel_sequential(merged, offset=1)
    merged[~valid] = 0

    n_rag = len(np.unique(merged[valid]))
    stats = {
        "n_segments_slic": int(n_slic),
        "n_segments_rag": int(n_rag),
        "rag_percentil": int(percentile),
        "rag_percentile": int(percentile),
        "rag_threshold": round(thr, 6),
        "rag_n_edges": int(weights.size),
        "rag_n_aristas": int(weights.size),
        "rag_reduction_pct": round(100.0 * (1 - n_rag / max(n_slic, 1)), 2),
    }
    return merged, stats


# Backward-compatible alias
fusionar_rag_threshold = merge_rag_threshold
