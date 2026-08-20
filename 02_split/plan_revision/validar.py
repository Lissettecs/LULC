"""Validaciones del plan de años de revisión."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from config import params_plan_revision as P
from plan_revision.derivar import periodo_de_anio


@dataclass
class ResultadoValidacion:
    ok: bool = True
    errores: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)

    def fallar(self, msg: str) -> None:
        self.ok = False
        self.errores.append(msg)

    def advertir(self, msg: str) -> None:
        self.advertencias.append(msg)


def _anios_rev(row: pd.Series) -> list[int]:
    return [
        int(row[f"rev_year{i}"])
        for i in (1, 2, 3)
        if int(row.get(f"rev_year{i}", P.SENTINEL)) != P.SENTINEL
    ]


def validar_plan(df: pd.DataFrame) -> ResultadoValidacion:
    res = ResultadoValidacion()
    if df.empty:
        res.fallar("DataFrame vacío")
        return res

    for idx, row in df.iterrows():
        gid = row.get("grid_id", idx)
        y1 = int(row.get("rev_year1", P.SENTINEL))
        if y1 == P.SENTINEL:
            res.fallar(f"{gid}: rev_year1 ausente")
            continue
        if not (P.ANIO_MIN <= y1 <= P.ANIO_MAX):
            res.fallar(f"{gid}: rev_year1={y1} fuera de rango")

        anios = _anios_rev(row)
        if len(anios) != int(row.get("rev_n_years", 0)):
            res.fallar(
                f"{gid}: rev_n_years={row.get('rev_n_years')} "
                f"no coincide con {len(anios)} años"
            )
        if len(anios) != len(set(anios)):
            res.fallar(f"{gid}: años duplicados {anios}")

        for i in (1, 2, 3):
            y = int(row.get(f"rev_year{i}", P.SENTINEL))
            rol = str(row.get(f"rev_role{i}", ""))
            if y != P.SENTINEL and not rol:
                res.fallar(f"{gid}: rev_year{i}={y} sin rev_role{i}")
            if y == P.SENTINEL and rol:
                res.fallar(f"{gid}: rev_role{i}='{rol}' sin rev_year{i}")

        tipo = str(row.get("sample_type", ""))
        if tipo in P.TIPOS_ESTABLE:
            start = int(row.get("stab_run_start", P.ANIO_MIN))
            end = int(row.get("stab_run_end", P.ANIO_MAX))
            if not (start <= y1 <= end):
                res.fallar(
                    f"{gid}: ancla {y1} fuera de tramo estable [{start}, {end}]"
                )
            y2 = int(row.get("rev_year2", P.SENTINEL))
            if y2 != P.SENTINEL:
                p1 = periodo_de_anio(y1)
                p2 = periodo_de_anio(y2)
                if p1 and p2 and p1 == p2:
                    res.fallar(
                        f"{gid}: control {y2} en mismo periodo Landsat que ancla {y1}"
                    )

        if tipo in P.TIPOS_TRANSICION:
            metodo = str(row.get("rev_metodo", ""))
            if metodo != "transicion_fallback_sin_cambio_periodo":
                if int(row.get("rev_n_years", 0)) != 3:
                    res.fallar(
                        f"{gid}: transición sin fallback debe tener 3 años "
                        f"(tiene {row.get('rev_n_years')})"
                    )

    n_sin_y1 = int((df["rev_year1"] == P.SENTINEL).sum())
    if n_sin_y1:
        res.fallar(f"{n_sin_y1} rectángulos sin rev_year1")

    return res
