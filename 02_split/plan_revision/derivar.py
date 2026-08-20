"""Reglas de derivación de rev_year1/2/3 por tipo de muestra."""

from __future__ import annotations

from typing import Any

import pandas as pd

from config import params_plan_revision as P

REV_COLS = [
    "rev_year1", "rev_role1",
    "rev_year2", "rev_role2",
    "rev_year3", "rev_role3",
    "rev_n_years", "rev_metodo",
]


def periodo_de_anio(anio: int) -> str | None:
    for nombre, (ini, fin) in P.PERIODOS.items():
        if ini <= anio <= fin:
            return nombre
    return None


def _num(row: pd.Series, col: str, default: float = 0.0) -> float:
    val = row.get(col, default)
    if pd.isna(val):
        return default
    return float(val)


def _int(row: pd.Series, col: str, default: int = 0) -> int:
    return int(round(_num(row, col, default)))


def _md_periodo(row: pd.Series, periodo: str) -> tuple[int | None, float]:
    md_id = _int(row, f"md_id_{periodo}", -9999)
    md_pct = _num(row, f"md_pct_{periodo}", 0.0)
    if md_id in (-9999, 0):
        return None, md_pct
    return md_id, md_pct


def _mods_periodo(row: pd.Series) -> list[tuple[str, int]]:
    mods: list[tuple[str, int]] = []
    for periodo in P.ORDEN_PERIODOS:
        md_id, _ = _md_periodo(row, periodo)
        if md_id is not None:
            mods.append((periodo, md_id))
    return mods


def _contar_anios(rev: dict[str, Any]) -> int:
    return sum(1 for i in (1, 2, 3) if rev.get(f"rev_year{i}", P.SENTINEL) != P.SENTINEL)


def _empaquetar(
    y1: int,
    r1: str,
    y2: int = P.SENTINEL,
    r2: str = "",
    y3: int = P.SENTINEL,
    r3: str = "",
    metodo: str = "",
) -> dict[str, Any]:
    rev = {
        "rev_year1": y1,
        "rev_role1": r1,
        "rev_year2": y2,
        "rev_role2": r2,
        "rev_year3": y3,
        "rev_role3": r3,
        "rev_metodo": metodo,
    }
    rev["rev_n_years"] = _contar_anios(rev)
    return rev


def _periodo_mayor_cambio(row: pd.Series) -> str:
    """Periodo con mayor salto entre modas consecutivas."""
    mods = _mods_periodo(row)
    mejor_p = P.ORDEN_PERIODOS[-1]
    mejor_score = -1.0
    for i in range(len(mods) - 1):
        p1, id1 = mods[i]
        p2, id2 = mods[i + 1]
        _, pct1 = _md_periodo(row, p1)
        _, pct2 = _md_periodo(row, p2)
        score = abs(pct1 - pct2)
        if id1 != id2:
            score += 100.0
        if score > mejor_score:
            mejor_score = score
            mejor_p = p2
    return mejor_p


def _periodo_mayor_area_valida(row: pd.Series) -> str:
    """Periodo con más años estables observados (proxy de área válida)."""
    return max(
        P.ORDEN_PERIODOS,
        key=lambda p: _num(row, f"n_stb_{p}", 0.0),
    )


def _asignar_anual(row: pd.Series) -> dict[str, Any]:
    ref = _int(row, "ref_year", P.SENTINEL)
    if ref == P.SENTINEL or ref < P.ANIO_MIN:
        ref = P.ANIO_MEDIO_PERIODO[P.ORDEN_PERIODOS[-1]]
    return _empaquetar(ref, "anual", metodo="ref_year_directo")


def _asignar_estable(row: pd.Series) -> dict[str, Any]:
    start = _int(row, "stab_run_start", P.ANIO_MIN)
    end = _int(row, "stab_run_end", P.ANIO_MAX)
    if start > end:
        start, end = end, start
    rev_year1 = (start + end) // 2
    rev_year1 = max(start, min(end, rev_year1))
    p_ancla = periodo_de_anio(rev_year1)

    y2, r2 = P.SENTINEL, ""
    if p_ancla is not None and start < end:
        candidatos = [p for p in P.ORDEN_PERIODOS if p != p_ancla]
        dentro = [
            p for p in candidatos
            if start <= P.ANIO_MEDIO_PERIODO[p] <= end
        ]
        if dentro:
            p_control = max(
                dentro,
                key=lambda p: abs(P.PERIODOS[p][0] - P.PERIODOS[p_ancla][0]),
            )
            y2 = P.ANIO_MEDIO_PERIODO[p_control]
            r2 = "control_sensor"

    return _empaquetar(
        rev_year1,
        "ancla",
        y2,
        r2,
        metodo="estable_ancla_control",
    )


def _asignar_transicion(row: pd.Series) -> dict[str, Any]:
    mods = _mods_periodo(row)
    cambio: tuple[str, str] | None = None
    for i in range(len(mods) - 1):
        if mods[i][1] != mods[i + 1][1]:
            cambio = (mods[i][0], mods[i + 1][0])
            break

    if cambio:
        p_antes, p_despues = cambio
        return _empaquetar(
            P.PERIODOS[p_despues][0],
            "durante_cambio",
            P.ANIO_MEDIO_PERIODO[p_antes],
            "antes",
            P.ANIO_MEDIO_PERIODO[p_despues],
            "despues",
            metodo="transicion_md_periodos",
        )

    p_fb = _periodo_mayor_cambio(row)
    ref = _int(row, "ref_year", P.SENTINEL)
    y1 = P.ANIO_MEDIO_PERIODO[p_fb] if ref == P.SENTINEL else ref
    return _empaquetar(
        y1,
        "durante_cambio",
        metodo="transicion_fallback_sin_cambio_periodo",
    )


def _asignar_presencia(row: pd.Series) -> dict[str, Any]:
    clase = _int(row, "clase_objetivo", -1)
    mejor_pct = -1.0
    p_mejor = P.ORDEN_PERIODOS[0]
    for periodo in P.ORDEN_PERIODOS:
        md_id, md_pct = _md_periodo(row, periodo)
        if md_id == clase and md_pct > mejor_pct:
            mejor_pct = md_pct
            p_mejor = periodo

    if mejor_pct >= 0:
        return _empaquetar(
            P.ANIO_MEDIO_PERIODO[p_mejor],
            "representativo_clase",
            metodo="censo_refuerzo_periodo_dominante",
        )

    ref = _int(row, "ref_year", P.SENTINEL)
    if ref != P.SENTINEL and P.ANIO_MIN <= ref <= P.ANIO_MAX:
        y1 = ref
    else:
        p_gen = max(P.ORDEN_PERIODOS, key=lambda p: _num(row, f"md_pct_{p}", 0.0))
        y1 = P.ANIO_MEDIO_PERIODO[p_gen]
    return _empaquetar(
        y1,
        "representativo_clase",
        metodo="censo_refuerzo_fallback",
    )


def _asignar_relleno(row: pd.Series) -> dict[str, Any]:
    tr = _num(row, "transition_pct", 0.0)
    stab = _num(row, "max_stab_run", 0.0)
    if tr > P.UMBRAL_TRANSICION:
        rev = _asignar_transicion(row)
        rev["rev_metodo"] = "relleno_por_composicion"
        return rev
    if stab >= P.UMBRAL_ESTABLE:
        rev = _asignar_estable(row)
        rev["rev_metodo"] = "relleno_por_composicion"
        return rev
    p = _periodo_mayor_area_valida(row)
    return _empaquetar(
        P.ANIO_MEDIO_PERIODO[p],
        "representativo_clase",
        metodo="relleno_por_composicion",
    )


def asignar_rev_years(row: pd.Series) -> dict[str, Any]:
    """Deriva rev_year1/2/3 y roles para un rectángulo."""
    tipo = str(row.get("sample_type", ""))
    if tipo in P.TIPOS_ANUAL:
        return _asignar_anual(row)
    if tipo in P.TIPOS_ESTABLE:
        return _asignar_estable(row)
    if tipo in P.TIPOS_TRANSICION:
        return _asignar_transicion(row)
    if tipo in P.TIPOS_PRESENCIA:
        return _asignar_presencia(row)
    if tipo == P.TIPO_RELLENO:
        return _asignar_relleno(row)

    # Tipo desconocido: un año representativo genérico
    p = _periodo_mayor_area_valida(row)
    return _empaquetar(
        P.ANIO_MEDIO_PERIODO[p],
        "representativo_clase",
        metodo="tipo_desconocido_fallback",
    )


def enriquecer_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Añade columnas rev_* a un DataFrame de selección."""
    out = df.copy()
    asignaciones = out.apply(asignar_rev_years, axis=1, result_type="expand")
    for col in REV_COLS:
        out[col] = asignaciones[col]
    return out
