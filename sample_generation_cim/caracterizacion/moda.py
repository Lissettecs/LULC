"""Moda por eje, vectorizada.

v02 la calculaba con np.apply_along_axis + np.bincount, es decir un bucle de
Python con una llamada por píxel: 278.784 llamadas y ~0,5 s por cada moda de una
celda de 528 px. Como los IDs de clase presentes son pocos (rara vez más de 15 en
una celda), sale unas 6 veces más barato contar una máscara booleana por clase y
quedarse con la de mayor conteo. Se calculan seis modas por celda (composición,
cuatro periodos y espacial), así que la diferencia se nota sobre 11.858 celdas.

El desempate es el mismo que en bincount().argmax(): gana el ID más chico, porque
se recorre en orden ascendente con comparación estricta. Está contrastado contra
la implementación de v02, incluidos empates y exclusión de nodata.
"""

from __future__ import annotations

import numpy as np


def moda(
    arr: np.ndarray,
    eje: int = 0,
    ids: np.ndarray | None = None,
    excluir: tuple[int, ...] = (),
    sin_dato: int = 0,
) -> np.ndarray:
    """Moda de `arr` a lo largo de `eje`, ignorando las clases de `excluir`.

    Los elementos donde no queda ninguna clase admisible se devuelven como
    `sin_dato`.
    """
    a = np.moveaxis(arr, eje, 0)
    forma = a.shape[1:]
    plano = a.reshape(a.shape[0], -1)

    presentes = np.unique(plano) if ids is None else np.asarray(ids)
    candidatos = sorted(int(c) for c in presentes if int(c) not in excluir)

    mejor_cnt = np.zeros(plano.shape[1], dtype=np.int32)
    mejor_id = np.full(plano.shape[1], sin_dato, dtype=np.int16)
    for c in candidatos:
        cnt = (plano == c).sum(axis=0)
        gana = cnt > mejor_cnt
        mejor_cnt[gana] = cnt[gana]
        mejor_id[gana] = c
    return mejor_id.reshape(forma)


def moda_bloques(
    arr: np.ndarray, factor: int, excluir: tuple[int, ...] = (), sin_dato: int = 0
) -> np.ndarray:
    """Moda por bloques factor×factor sobre los dos últimos ejes.

    Acepta (h, w) o (t, h, w) y recorta el sobrante si el lado no es múltiplo del
    factor. Con STATS_BLOQUE_PX = 11 no sobra nada: divide exacto 528 y 792.
    """
    if arr.ndim == 2:
        return moda_bloques(arr[None], factor, excluir, sin_dato)[0]
    t, h, w = arr.shape
    nh, nw = h // factor, w // factor
    bloques = (
        arr[:, : nh * factor, : nw * factor]
        .reshape(t, nh, factor, nw, factor)
        .transpose(0, 1, 3, 2, 4)
        .reshape(t, nh, nw, factor * factor)
    )
    return moda(bloques, eje=3, excluir=excluir, sin_dato=sin_dato)
