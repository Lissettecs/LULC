#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
09_generate_rectangle_review_plan.py

Genera un plan de revisión temporal para rectángulos seleccionados SSL4EO-L.

Entrada:
  GeoJSON/GPKG de selección de rectángulos, por ejemplo:
  final_samples/seleccion_grilla_ssl4eo_muestras_UTM19_scale300.geojson

Salida:
  CSV con una fila por rectángulo y campos:
    review_years
    n_review_years
    review_rule
    review_priority
    review_notes

La lógica usa los campos generados por 03_rectangle_selection.py:
  dim_temporal, sample_type, ref_year, stable_years, md_id_P1..P4,
  md_nm_P1..P4, stb_yrs_P1..P4, transition_pct, target_rare_class, review_tier.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd


YEARS = list(range(1999, 2025))

PERIODS = {
    "P1": (1999, 2005),
    "P2": (2006, 2012),
    "P3": (2013, 2018),
    "P4": (2019, 2024),
}

PERIOD_BOUNDARY_WINDOWS = {
    ("P1", "P2"): [2004, 2005, 2006, 2007],
    ("P2", "P3"): [2011, 2012, 2013, 2014],
    ("P3", "P4"): [2017, 2018, 2019, 2020],
}

STABLE_ANCHORS = [1999, 2013, 2024]
TRANSITION_ANCHORS = [1999, 2005, 2012, 2018, 2024]


def parse_years(value) -> list[int]:
    if value is None or pd.isna(value):
        return []
    years = []
    for part in str(value).split(","):
        part = part.strip()
        if part.isdigit():
            y = int(part)
            if 1999 <= y <= 2024:
                years.append(y)
    return sorted(set(years))


def clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in ("nan", "none"):
        return ""
    return text


def safe_int(value, default: int = -9999) -> int:
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except Exception:
        return default


def nearest_year(target: int, candidates: list[int]) -> int | None:
    if not candidates:
        return None
    return sorted(candidates, key=lambda y: (abs(y - target), y))[0]


def compact_years(years: list[int], max_n: int | None = None) -> list[int]:
    out = sorted(set(y for y in years if 1999 <= int(y) <= 2024))
    if max_n is not None and len(out) > max_n:
        # Conserva primero, último y años distribuidos.
        if max_n <= 2:
            return out[:max_n]
        idx = [round(i * (len(out) - 1) / (max_n - 1)) for i in range(max_n)]
        out = [out[i] for i in sorted(set(idx))]
        while len(out) < max_n:
            for y in sorted(set(years)):
                if y not in out:
                    out.append(y)
                if len(out) == max_n:
                    break
        out = sorted(set(out))
    return out


def period_mode_values(row: pd.Series, prefix: str = "md_id") -> dict[str, int]:
    return {p: safe_int(row.get(f"{prefix}_{p}")) for p in PERIODS}


def period_mode_names(row: pd.Series) -> dict[str, str]:
    return {p: clean_text(row.get(f"md_nm_{p}")) for p in PERIODS}


def transition_period_windows(row: pd.Series) -> list[int]:
    ids = period_mode_values(row)
    periods = ["P1", "P2", "P3", "P4"]
    years: list[int] = []
    for a, b in zip(periods[:-1], periods[1:]):
        if ids.get(a, -9999) != ids.get(b, -9999):
            years.extend(PERIOD_BOUNDARY_WINDOWS[(a, b)])
    return compact_years(years)


def nonstable_windows(row: pd.Series) -> list[int]:
    stable = parse_years(row.get("stable_years"))
    if not stable:
        return []
    nonstable = sorted(set(YEARS) - set(stable))
    years: list[int] = []
    for y in nonstable:
        years.extend([y - 1, y, y + 1])
    return compact_years(years, max_n=9)


def rare_period_years(row: pd.Series) -> list[int]:
    rare_name = clean_text(row.get("target_rare_class"))
    rare_id = safe_int(row.get("target_rare_class_id"))
    if not rare_name and rare_id <= 0:
        return []

    ids = period_mode_values(row)
    names = period_mode_names(row)

    years: list[int] = []
    for period, (start, end) in PERIODS.items():
        id_match = rare_id > 0 and ids.get(period) == rare_id
        name_match = rare_name and names.get(period) == rare_name
        if not id_match and not name_match:
            continue

        stb = parse_years(row.get(f"stb_yrs_{period}"))
        if stb:
            years.extend([stb[0], stb[-1]])
        else:
            years.extend([start, end])

    return compact_years(years, max_n=6)


def stable_review_years(row: pd.Series) -> list[int]:
    stable = parse_years(row.get("stable_years"))

    if not stable:
        # Fallback defensivo.
        return STABLE_ANCHORS.copy()

    chosen: list[int] = []

    # Primer ancla: preferir 1999; si no está, buscar cerca de 2001.
    if 1999 in stable:
        chosen.append(1999)
    else:
        y = nearest_year(2001, stable)
        if y is not None:
            chosen.append(y)

    # Ancla media.
    y = 2013 if 2013 in stable else nearest_year(2013, stable)
    if y is not None:
        chosen.append(y)

    # Última ancla.
    if 2024 in stable:
        chosen.append(2024)
    else:
        y = max(stable) if stable else None
        if y is not None:
            chosen.append(y)

    return compact_years(chosen)


def annual_review_years(row: pd.Series) -> list[int]:
    ref_year = safe_int(row.get("ref_year"))
    if 1999 <= ref_year <= 2024:
        return [ref_year]
    return []


def transition_review_years(row: pd.Series) -> tuple[list[int], str]:
    # 1) Si cambió la clase modal entre periodos, revisar ventanas de límite.
    boundary_years = transition_period_windows(row)
    if boundary_years:
        return compact_years(boundary_years, max_n=9), "transicion_cambio_modal_entre_periodos"

    # 2) Si hay años no estables respecto al modo global, revisar alrededor de esos años.
    ns_years = nonstable_windows(row)
    if ns_years:
        return compact_years(ns_years, max_n=9), "transicion_anios_no_estables"

    # 3) Fallback: transición detectada por porcentaje, pero sin año exacto.
    return TRANSITION_ANCHORS.copy(), "transicion_sin_anio_exacto_usar_anclas"


def review_plan_for_row(row: pd.Series) -> dict:
    dim = clean_text(row.get("dim_temporal"))
    sample_type = clean_text(row.get("sample_type"))
    rare_name = clean_text(row.get("target_rare_class"))
    review_tier = safe_int(row.get("review_tier"), default=2)

    years: list[int] = []
    rule = ""
    notes: list[str] = []

    if dim == "anual":
        years = annual_review_years(row)
        rule = "anual_ref_year"
        if not years:
            notes.append("anual_sin_ref_year_valido")
            # Respaldo: usar años estables por periodo si existen.
            stable = parse_years(row.get("stable_years"))
            if stable:
                y = nearest_year(2019, stable)
                if y is not None:
                    years = [y]
                    rule = "anual_fallback_stable_year"

    elif dim == "estable":
        years = stable_review_years(row)
        rule = "estable_anclas_temporales"

    elif dim == "transicion":
        years, rule = transition_review_years(row)

    else:
        # Fallback defensivo para registros sin dim_temporal.
        years = stable_review_years(row)
        rule = "fallback_anclas_temporales"
        notes.append("dim_temporal_no_reconocida")

    rare_years = rare_period_years(row)
    if rare_years:
        before = set(years)
        years = compact_years(years + rare_years, max_n=10)
        if set(years) != before:
            notes.append("incluye_anios_clase_rara")

    # Prioridad: menor número = más urgente.
    # Respeta review_tier, pero aumenta prioridad para clases raras y transiciones.
    priority = review_tier
    if rare_name:
        priority = min(priority, 1)
    if dim == "transicion":
        priority = min(priority, 1)
    if sample_type in ("transicion_homogenea", "anual_homogenea"):
        priority = min(priority, 1)

    years = compact_years(years)
    return {
        "review_years": ",".join(str(y) for y in years),
        "n_review_years": len(years),
        "review_rule": rule,
        "review_priority": priority,
        "review_notes": ";".join(notes),
    }


def process_file(input_path: Path, output_path: Path | None = None) -> Path:
    gdf = gpd.read_file(input_path)
    attrs = pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))

    plan = attrs.apply(review_plan_for_row, axis=1, result_type="expand")
    out = pd.concat([attrs, plan], axis=1)

    if output_path is None:
        output_path = input_path.with_name(input_path.stem + "_plan_revision.csv")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera plan de años de revisión para rectángulos SSL4EO.")
    parser.add_argument("--input", "-i", type=Path, required=True, help="GeoJSON/GPKG de rectángulos seleccionados.")
    parser.add_argument("--output", "-o", type=Path, default=None, help="CSV de salida.")
    args = parser.parse_args()

    out = process_file(args.input, args.output)
    print(f"Plan de revisión escrito en: {out}")

    df = pd.read_csv(out)
    print("\nResumen por regla:")
    print(df["review_rule"].value_counts().to_string())

    print("\nResumen por dimensión temporal:")
    print(df.groupby(["dim_temporal", "review_rule"]).size().to_string())

    print("\nNúmero de años a revisar:")
    print(df["n_review_years"].describe().round(2).to_string())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
