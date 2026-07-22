"""Utilidades compartidas entre Pipeline A y Pipeline B."""

from __future__ import annotations

import heapq
import time
from typing import Iterable

import numpy as np
from skimage.graph import cut_threshold, merge_hierarchical, rag_mean_color
from skimage.segmentation import relabel_sequential, slic

COMPACTNESS = 10.0
RAG_USE_INDICES = False
ABSORBER_LOG_EVERY = 1_000


def n_segments_desde_scale(n_pixeles_validos: int, scale: int) -> int:
    return max(2, int(n_pixeles_validos // scale))


def construir_features(datos: np.ndarray, validos: np.ndarray) -> np.ndarray:
    """Features para SLIC y RAG: sin NaN/nodata (misma preparación que SLIC)."""
    if RAG_USE_INDICES:
        raise NotImplementedError(
            "RAG_USE_INDICES=True no implementado (ablación futura). Usar False."
        )
    return preparar_imagen_slic(datos.astype(np.float32), validos)


def _feats_para_rag(feats: np.ndarray, validos: np.ndarray) -> np.ndarray:
    """Asegura imagen finita para rag_mean_color (nodata → mediana por banda)."""
    out = feats.astype(np.float32, copy=True)
    if not np.all(np.isfinite(out[validos])):
        out = preparar_imagen_slic(out, validos)
    out = np.nan_to_num(out, nan=0.0, posinf=1.0, neginf=0.0)
    return out


def preparar_imagen_slic(datos: np.ndarray, validos: np.ndarray) -> np.ndarray:
    """Mediana por banda en nodata; SLIC sobre el rectángulo completo (sin mask)."""
    salida = datos.astype(np.float32, copy=True)
    for canal in range(salida.shape[-1]):
        banda = salida[..., canal]
        mediana = float(np.median(banda[validos])) if np.any(validos) else 0.0
        banda[~validos] = mediana
        salida[..., canal] = banda
    return salida


def ejecutar_slic(
    feats: np.ndarray,
    validos: np.ndarray,
    n_segments: int,
    sigma: float,
) -> np.ndarray:
    img = preparar_imagen_slic(feats, validos)
    sp = slic(
        img,
        n_segments=n_segments,
        compactness=COMPACTNESS,
        sigma=sigma,
        channel_axis=-1,
        enforce_connectivity=True,
        start_label=1,
    )
    sp = sp.astype(np.int32)
    sp[~validos] = 0
    return sp


def _peso_media_color(graph, src, dst, n) -> dict:
    diff = graph.nodes[dst]["mean color"] - graph.nodes[n]["mean color"]
    return {"weight": float(np.linalg.norm(diff))}


def _fusion_media_color(graph, src, dst) -> None:
    graph.nodes[dst]["total color"] += graph.nodes[src]["total color"]
    graph.nodes[dst]["pixel count"] += graph.nodes[src]["pixel count"]
    graph.nodes[dst]["mean color"] = (
        graph.nodes[dst]["total color"] / graph.nodes[dst]["pixel count"]
    )


def fusionar_hierarchical_rag(
    labels_slic: np.ndarray,
    feats: np.ndarray,
    thr_abs: float,
    validos: np.ndarray,
) -> np.ndarray:
    img = _feats_para_rag(feats, validos)
    g = rag_mean_color(img, labels_slic)
    if 0 in g:
        g.remove_node(0)
    merged = merge_hierarchical(
        labels_slic,
        g,
        thresh=thr_abs,
        rag_copy=False,
        in_place_merge=True,
        merge_func=_fusion_media_color,
        weight_func=_peso_media_color,
    )
    merged = merged.astype(np.int32)
    merged[~validos] = 0
    merged, _, _ = relabel_sequential(merged, offset=1)
    merged[~validos] = 0
    return merged


def fusionar_threshold_rag(
    labels_slic: np.ndarray,
    feats: np.ndarray,
    thr_abs: float,
    validos: np.ndarray,
) -> np.ndarray:
    img = _feats_para_rag(feats, validos)
    g = rag_mean_color(img, labels_slic)
    if 0 in g:
        g.remove_node(0)
    merged = cut_threshold(labels_slic, g, thr_abs)
    merged = merged.astype(np.int32)
    merged[~validos] = 0
    merged, _, _ = relabel_sequential(merged, offset=1)
    merged[~validos] = 0
    return merged


def _peso_arista_entre(g, a: int, b: int) -> float:
    diff = g.nodes[a]["mean color"] - g.nodes[b]["mean color"]
    return float(np.linalg.norm(diff))


def _absorber_nodo_rag(g, chica: int, destino: int) -> None:
    if chica == destino or chica not in g or destino not in g:
        return

    _fusion_media_color(g, chica, destino)

    for vecino in list(g.neighbors(chica)):
        if vecino == destino:
            continue
        peso = _peso_arista_entre(g, destino, vecino)
        if g.has_edge(destino, vecino):
            g[destino][vecino]["weight"] = peso
        else:
            g.add_edge(destino, vecino, weight=peso)

    g.remove_node(chica)

    for vecino in g.neighbors(destino):
        g[destino][vecino]["weight"] = _peso_arista_entre(g, destino, vecino)


def _conteo_regiones(labels: np.ndarray, validos: np.ndarray) -> dict[int, int]:
    ids, counts = np.unique(labels[validos], return_counts=True)
    return {int(i): int(c) for i, c in zip(ids, counts) if i != 0}


def absorber_pequenos(
    merged: np.ndarray,
    feats: np.ndarray,
    validos: np.ndarray,
    min_px: int,
) -> tuple[np.ndarray, int]:
    """Absorbe regiones < min_px en el vecino espectralmente más similar."""
    if min_px <= 0:
        return merged.copy(), 0

    t0 = time.perf_counter()
    labels = merged.copy()
    labels[~validos] = 0

    img = _feats_para_rag(feats, validos)
    g = rag_mean_color(img, labels)
    if 0 in g:
        g.remove_node(0)

    counts = _conteo_regiones(labels, validos)
    heap: list[tuple[int, int]] = [
        (c, label_id) for label_id, c in counts.items() if c < min_px
    ]
    heapq.heapify(heap)
    irresolubles: set[int] = set()
    n_absorb = 0

    while heap:
        c, chico = heapq.heappop(heap)
        if chico in irresolubles:
            continue
        actual = counts.get(chico, 0)
        if actual != c:
            if 0 < actual < min_px:
                heapq.heappush(heap, (actual, chico))
            continue
        if actual >= min_px or actual == 0:
            continue
        if chico not in g:
            irresolubles.add(chico)
            continue

        vecinos = [n for n in g.neighbors(chico) if n != 0]
        if not vecinos:
            irresolubles.add(chico)
            continue

        mc = g.nodes[chico]["mean color"]
        destino = min(
            vecinos,
            key=lambda n: float(np.linalg.norm(g.nodes[n]["mean color"] - mc)),
        )

        labels[labels == chico] = destino
        _absorber_nodo_rag(g, chico, destino)
        counts[destino] = counts.get(destino, 0) + counts.pop(chico)
        n_absorb += 1

        if counts[destino] < min_px:
            heapq.heappush(heap, (counts[destino], destino))

        if ABSORBER_LOG_EVERY > 0 and n_absorb % ABSORBER_LOG_EVERY == 0:
            elapsed = time.perf_counter() - t0
            print(
                f"     ... {n_absorb:,} absorciones · regiones≈{len(counts):,} "
                f"· irresolubles={len(irresolubles):,} · {elapsed:.1f}s",
                flush=True,
            )

    labels, _, _ = relabel_sequential(labels, offset=1)
    labels[~validos] = 0
    elapsed = time.perf_counter() - t0
    print(
        f"     etapa 3 lista: {n_absorb:,} absorciones, "
        f"irresolubles={len(irresolubles):,} en {elapsed:.1f}s",
        flush=True,
    )
    return labels.astype(np.int32), len(irresolubles)


def pesos_aristas_rag(g) -> np.ndarray:
    if g.number_of_edges() == 0:
        return np.array([], dtype=np.float64)
    pesos = np.array([d["weight"] for _, _, d in g.edges(data=True)], dtype=np.float64)
    return pesos[np.isfinite(pesos)]


def umbral_rag_desde_pesos(pesos: np.ndarray, percentil: int) -> float:
    if pesos.size == 0:
        raise ValueError("RAG sin aristas con peso finito")
    thr = float(np.percentile(pesos, percentil))
    if not np.isfinite(thr):
        raise ValueError(f"Umbral RAG p{percentil} no finito (pesos inválidos)")
    return thr


def imprimir_distribucion_pesos(pesos: np.ndarray, scale: int, sigma: float) -> None:
    if pesos.size == 0:
        print(f"  → RAG distribución pesos (s={scale}, σ={sigma}): sin aristas")
        return
    percentiles = [5, 10, 25, 50, 75, 90]
    pct_vals = {p: float(np.percentile(pesos, p)) for p in percentiles}
    detalle = " · ".join(f"p{p}={pct_vals[p]:.6f}" for p in percentiles)
    print(
        f"  → RAG distribución pesos (s={scale}, σ={sigma}), "
        f"n_aristas={pesos.size:,}: min={pesos.min():.6f} max={pesos.max():.6f}"
    )
    print(f"     {detalle}")


def verificar_stats_rag(stats: dict) -> None:
    tam_max = stats["tam_max_px"]
    if tam_max >= 1_000_000:
        print(f"  → [ADVERTENCIA] posible fuga residual: tam_max_px={tam_max:,} (≥1M px)")
    else:
        print(f"  → tam_max_px={tam_max:,} (OK: decenas de miles, no millones)")


def verificar_stats_final(stats: dict, min_px: int, n_irresolubles: int) -> None:
    tam_min = stats["tam_min_px"]
    if min_px > 0 and tam_min < min_px:
        print(
            f"  → [ADVERTENCIA] tam_min_px={tam_min} < min_px ({min_px}); "
            f"chicos irresolubles: {n_irresolubles}"
        )
    elif min_px > 0:
        print(f"  → tam_min_px={tam_min} (≥ {min_px})")
    if n_irresolubles > 0:
        print(f"  → chicos irresolubles: {n_irresolubles}")


def stem_combo(tile: str, year: int, scale: int, sigma: float) -> str:
    return f"seg_{tile}_{year}_s{scale}_sig{sigma}"


def sufijo_ragp(percentil: int) -> str:
    return f"ragp{percentil}"


def sufijo_hier(percentil: int) -> str:
    return f"hier_p{percentil}"


def todas_combinaciones(
    scales: Iterable[int],
    sigmas: Iterable[float],
    percentiles: Iterable[int],
) -> list[tuple[int, float, int]]:
    return [
        (scale, sigma, int(pct))
        for scale in scales
        for sigma in sigmas
        for pct in percentiles
    ]


def combo_desde_indice(
    scales: Iterable[int],
    sigmas: Iterable[float],
    percentiles: Iterable[int],
    idx: int,
) -> tuple[int, float, int]:
    combos = todas_combinaciones(scales, sigmas, percentiles)
    if idx < 0 or idx >= len(combos):
        raise ValueError(f"--combo-index fuera de rango: {idx} (0..{len(combos) - 1})")
    return combos[idx]


def resolver_grid_filtros(
    scales: list[int],
    sigmas: list[float],
    percentiles: list[int],
    scale: int | None,
    sigma: float | None,
    rag_percentil: int | None,
    combo_index: int | None,
) -> tuple[list[int], list[float], list[int]]:
    if combo_index is not None:
        s, sig, pct = combo_desde_indice(scales, sigmas, percentiles, combo_index)
        return [s], [sig], [pct]
    out_scales = [scale] if scale is not None else scales
    out_sigmas = [sigma] if sigma is not None else sigmas
    out_pcts = (
        [rag_percentil]
        if rag_percentil is not None
        else [int(p) for p in percentiles]
    )
    return out_scales, out_sigmas, out_pcts
