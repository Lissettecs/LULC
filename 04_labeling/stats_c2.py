"""Estadísticas de etiquetado C2 por segmento."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from config.clases_c2 import CLASES_TIER_PROTEGIDO, C2_NODATA, nombre_clase


@dataclass(frozen=True)
class LabelStats:
    segment_ids: np.ndarray
    area_px: np.ndarray
    n_valid: np.ndarray
    clase_moda: np.ndarray
    pureza: np.ndarray
    clase_2: np.ndarray
    pureza_2: np.ndarray
    n_clases: np.ndarray
    tiene_protegida: np.ndarray


def _distribucion_top3(p1: float, p2: float, n_valid: int, count1: int, count2: int) -> str:
    """Formato '95/2/1' sobre píxeles C2 válidos."""
    if n_valid <= 0:
        return "0/0/0"
    resto = max(0, n_valid - count1 - count2)
    p3 = 100.0 * resto / n_valid
    return f"{p1:.0f}/{p2:.0f}/{p3:.0f}"


def calcular_stats_c2(
    segments: np.ndarray,
    c2: np.ndarray,
    c2_nodata: frozenset[int] = C2_NODATA,
    clases_protegidas: frozenset[int] = CLASES_TIER_PROTEGIDO,
    background_id: int = 0,
) -> LabelStats:
    """
    Por cada segment_id:
      - clase_moda, pureza (%)
      - clase_2, pureza_2 (%)
      - n_clases (clases C2 válidas distintas)
      - area_px (píxeles del segmento, incl. nodata C2)
      - tiene_protegida
    """
    seg = segments.ravel().astype(np.int64, copy=False)
    lc = c2.ravel().astype(np.int64, copy=False)

    foreground = seg != background_id
    if not foreground.any():
        raise ValueError("Sin segmentos en el raster (todo background).")

    seg_fg = seg[foreground]
    segment_ids = np.unique(seg_fg)
    k = segment_ids.size
    seg_idx_all = np.searchsorted(segment_ids, seg_fg)

    area_px = np.bincount(seg_idx_all, minlength=k).astype(np.int64)

    valid_lc = foreground & ~np.isin(lc, list(c2_nodata))
    if not valid_lc.any():
        raise ValueError("Sin píxeles C2 válidos bajo segmentos.")

    seg_v = seg[valid_lc]
    lc_v = lc[valid_lc]
    seg_idx = np.searchsorted(segment_ids, seg_v)

    classes = np.unique(lc_v)
    nc = classes.size
    counts = np.zeros((k, nc), dtype=np.int64)
    for j, cls in enumerate(classes):
        counts[:, j] = np.bincount(seg_idx[lc_v == cls], minlength=k)

    n_valid = counts.sum(axis=1).astype(np.int64)

    best_j = np.argmax(counts, axis=1)
    count_moda = counts[np.arange(k), best_j]
    clase_moda = classes[best_j]

    with np.errstate(divide="ignore", invalid="ignore"):
        pureza = np.where(n_valid > 0, 100.0 * count_moda / n_valid, 0.0)

    # Segunda clase
    counts_copy = counts.copy()
    counts_copy[np.arange(k), best_j] = -1
    second_j = np.argmax(counts_copy, axis=1)
    count_2 = counts[np.arange(k), second_j]
    has_second = count_2 > 0
    clase_2 = np.zeros(k, dtype=np.int64)
    clase_2[has_second] = classes[second_j[has_second]]
    pureza_2 = np.where(n_valid > 0, 100.0 * count_2 / n_valid, 0.0)
    pureza_2[~has_second] = 0.0

    n_clases = (counts > 0).sum(axis=1).astype(np.int64)

    prot_cols = [j for j, cls in enumerate(classes) if int(cls) in clases_protegidas]
    if prot_cols:
        tiene_protegida = counts[:, prot_cols].sum(axis=1) > 0
    else:
        tiene_protegida = np.zeros(k, dtype=bool)

    return LabelStats(
        segment_ids=segment_ids,
        area_px=area_px,
        n_valid=n_valid,
        clase_moda=clase_moda.astype(np.int64),
        pureza=pureza.astype(np.float64),
        clase_2=clase_2.astype(np.int64),
        pureza_2=pureza_2.astype(np.float64),
        n_clases=n_clases,
        tiene_protegida=tiene_protegida,
    )


def stats_a_dataframe(stats: LabelStats) -> pd.DataFrame:
    rows = []
    for i in range(stats.segment_ids.size):
        sid = int(stats.segment_ids[i])
        p1 = float(stats.pureza[i])
        p2 = float(stats.pureza_2[i])
        c1 = int(stats.clase_moda[i])
        c2 = int(stats.clase_2[i])
        nv = int(stats.n_valid[i])
        cnt1 = int(round(p1 * nv / 100.0)) if nv else 0
        cnt2 = int(round(p2 * nv / 100.0)) if c2 else 0
        rows.append(
            {
                "segment_id": sid,
                "area_px": int(stats.area_px[i]),
                "n_valid_c2": nv,
                "clase_moda": c1,
                "clase_moda_nombre": nombre_clase(c1),
                "pureza": round(p1, 2),
                "clase_2": c2,
                "clase_2_nombre": nombre_clase(c2) if c2 else "",
                "pureza_2": round(p2, 2),
                "n_clases": int(stats.n_clases[i]),
                "tiene_protegida": bool(stats.tiene_protegida[i]),
                "distribucion_top3": _distribucion_top3(p1, p2, nv, cnt1, cnt2),
            }
        )
    return pd.DataFrame(rows).sort_values("segment_id").reset_index(drop=True)
