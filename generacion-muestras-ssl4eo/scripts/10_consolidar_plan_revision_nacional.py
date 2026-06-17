#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
10_consolidar_plan_revision_nacional.py

Consolida los planes de revisión UTM18 y UTM19 generados por
09_generar_plan_revision_rectangulos.py.

Entrada esperada:
  archivos_intermedios/revision/plan_revision_UTM18_scale300.csv
  archivos_intermedios/revision/plan_revision_UTM19_scale300.csv

Salidas:
  archivos_intermedios/revision/plan_revision_nacional_scale300.csv
  archivos_intermedios/revision/listado_revision_manual.csv
  archivos_intermedios/revision/resumen_revision_por_utm.csv
  archivos_intermedios/revision/resumen_revision_por_tipo.csv
  archivos_intermedios/revision/resumen_revision_por_regla.csv
  archivos_intermedios/revision/resumen_revision_por_anio.csv
  archivos_intermedios/revision/resumen_revision_por_prioridad.csv
  archivos_intermedios/revision/plan_revision_por_rectangulo_anio.csv

Uso desde PowerShell / Cursor:

  cd E:\\GEP\\MapBiomas\\COLECCION_3\\MUESTRAS\\grillas

  python scripts\\10_consolidar_plan_revision_nacional.py

También permite rutas personalizadas:

  python scripts\\10_consolidar_plan_revision_nacional.py ^
    --input archivos_intermedios\\revision\\plan_revision_UTM18_scale300.csv ^
            archivos_intermedios\\revision\\plan_revision_UTM19_scale300.csv ^
    --out-dir archivos_intermedios\\revision
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_ROOT = Path(r"E:\GEP\MapBiomas\COLECCION_3\MUESTRAS\grillas")
DEFAULT_REV_DIR = DEFAULT_ROOT / "archivos_intermedios" / "revision"

DEFAULT_INPUTS = [
    DEFAULT_REV_DIR / "plan_revision_UTM18_scale300.csv",
    DEFAULT_REV_DIR / "plan_revision_UTM19_scale300.csv",
]


def infer_utm_from_filename(path: Path) -> str:
    """Infiere UTM18/UTM19 desde el nombre del archivo."""
    name = path.name.upper()
    if "UTM18" in name:
        return "UTM18"
    if "UTM19" in name:
        return "UTM19"
    return "UTM"


def resolve_path(path: Path, root: Path) -> Path:
    """Resuelve rutas relativas respecto a la carpeta raíz del proyecto."""
    if path.is_absolute():
        return path
    return root / path


def split_years(value) -> list[int]:
    """
    Convierte el campo review_years a lista de enteros.

    Ejemplos:
      "1999,2013,2024" -> [1999, 2013, 2024]
      "" -> []
      NaN -> []
    """
    if pd.isna(value):
        return []

    text = str(value).strip()
    if not text:
        return []

    years: list[int] = []

    for part in text.split(","):
        part = part.strip()
        if not part:
            continue

        try:
            year = int(float(part))
        except ValueError:
            continue

        if 1900 <= year <= 2100:
            years.append(year)

    return sorted(set(years))


def normalize_text_column(df: pd.DataFrame, col: str, default: str = "") -> pd.DataFrame:
    """Crea o normaliza una columna de texto."""
    if col not in df.columns:
        df[col] = default
    df[col] = df[col].fillna(default).astype(str)
    return df


def normalize_numeric_column(
    df: pd.DataFrame,
    col: str,
    default: float | int = 0,
    as_int: bool = False,
) -> pd.DataFrame:
    """Crea o normaliza una columna numérica."""
    if col not in df.columns:
        df[col] = default
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(default)
    if as_int:
        df[col] = df[col].astype(int)
    return df


def load_plan(path: Path, root: Path) -> pd.DataFrame:
    """Carga un plan UTM y asegura columnas mínimas."""
    path = resolve_path(path, root)

    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo de entrada: {path}")

    df = pd.read_csv(path, encoding="utf-8-sig")

    if "utm" not in df.columns:
        df["utm"] = infer_utm_from_filename(path)
    else:
        df["utm"] = df["utm"].fillna(infer_utm_from_filename(path)).astype(str)

    df["fuente_plan"] = path.name

    if "grid_id" not in df.columns:
        raise ValueError(f"El archivo no contiene la columna grid_id: {path}")

    return df


def prepare_national_plan(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Une y normaliza el plan nacional."""
    nacional = pd.concat(frames, ignore_index=True)

    # Campos mínimos
    text_defaults = {
        "utm": "UTM",
        "grid_id": "",
        "review_years": "",
        "review_rule": "sin_regla",
        "review_notes": "",
        "sample_type": "sin_tipo",
        "dim_temporal": "sin_dim_temporal",
        "dim_espacial": "sin_dim_espacial",
        "split": "sin_split",
        "target_rare_class": "",
        "review_desc": "",
        "review_status": "",
        "ref_period": "",
        "ref_sensor": "",
        "lulc_mode_name": "",
        "eco_dom_name": "",
        "fuente_plan": "",
    }

    for col, default in text_defaults.items():
        nacional = normalize_text_column(nacional, col, default)

    numeric_defaults = {
        "review_priority": 3,
        "review_tier": 3,
        "ref_year": -9999,
        "lulc_mode_id": -9999,
        "eco_dom_id": -9999,
        "transition_pct": 0,
        "max_stab_run": 0,
    }

    for col, default in numeric_defaults.items():
        nacional = normalize_numeric_column(
            nacional,
            col,
            default=default,
            as_int=col in {"review_priority", "review_tier", "ref_year", "lulc_mode_id", "eco_dom_id"},
        )

    # Normalizar años de revisión
    nacional["review_years_list"] = nacional["review_years"].apply(split_years)
    nacional["review_years"] = nacional["review_years_list"].apply(
        lambda years: ",".join(str(y) for y in years)
    )
    nacional["n_review_years"] = nacional["review_years_list"].apply(len)

    # Flags de control
    nacional["has_review_years"] = nacional["n_review_years"] > 0
    nacional["is_auto_sin_revision"] = nacional["review_desc"].eq("auto_sin_revision")
    nacional["has_rare_class"] = nacional["target_rare_class"].str.strip().ne("")

    # Orden operativo
    sort_cols = [
        "review_priority",
        "utm",
        "dim_temporal",
        "sample_type",
        "review_rule",
        "grid_id",
    ]
    nacional = nacional.sort_values(sort_cols).reset_index(drop=True)

    return nacional


def build_rect_year_table(nacional: pd.DataFrame) -> pd.DataFrame:
    """
    Expande review_years a formato largo:
      una fila = grid_id + year
    """
    rows = []

    for _, row in nacional.iterrows():
        years = row.get("review_years_list", [])
        for year in years:
            rows.append({
                "utm": row.get("utm", ""),
                "grid_id": row.get("grid_id", ""),
                "year": year,
                "sample_type": row.get("sample_type", ""),
                "dim_temporal": row.get("dim_temporal", ""),
                "dim_espacial": row.get("dim_espacial", ""),
                "review_rule": row.get("review_rule", ""),
                "review_priority": row.get("review_priority", ""),
                "review_tier": row.get("review_tier", ""),
                "review_desc": row.get("review_desc", ""),
                "review_status": row.get("review_status", ""),
                "split": row.get("split", ""),
                "target_rare_class": row.get("target_rare_class", ""),
                "lulc_mode_id": row.get("lulc_mode_id", ""),
                "lulc_mode_name": row.get("lulc_mode_name", ""),
                "eco_dom_id": row.get("eco_dom_id", ""),
                "eco_dom_name": row.get("eco_dom_name", ""),
                "ref_year": row.get("ref_year", ""),
                "ref_period": row.get("ref_period", ""),
                "ref_sensor": row.get("ref_sensor", ""),
                "fuente_plan": row.get("fuente_plan", ""),
            })

    if not rows:
        return pd.DataFrame(columns=[
            "utm", "grid_id", "year", "sample_type", "dim_temporal",
            "dim_espacial", "review_rule", "review_priority", "review_tier",
            "review_desc", "review_status", "split", "target_rare_class",
            "lulc_mode_id", "lulc_mode_name", "eco_dom_id", "eco_dom_name",
            "ref_year", "ref_period", "ref_sensor", "fuente_plan",
        ])

    out = pd.DataFrame(rows)
    out = out.sort_values(["year", "utm", "review_priority", "grid_id"]).reset_index(drop=True)
    return out


def build_resumen_utm(nacional: pd.DataFrame) -> pd.DataFrame:
    resumen = (
        nacional.groupby("utm", dropna=False)
        .agg(
            n_rectangulos=("grid_id", "count"),
            n_grid_id_unicos=("grid_id", "nunique"),
            n_anios_revision_total=("n_review_years", "sum"),
            n_anios_revision_promedio=("n_review_years", "mean"),
            n_sin_review_years=("has_review_years", lambda x: int((~x).sum())),
            n_auto_sin_revision=("is_auto_sin_revision", "sum"),
            n_con_clase_rara=("has_rare_class", "sum"),
        )
        .reset_index()
    )

    resumen["n_anios_revision_promedio"] = resumen["n_anios_revision_promedio"].round(2)

    total = pd.DataFrame([{
        "utm": "TOTAL",
        "n_rectangulos": len(nacional),
        "n_grid_id_unicos": nacional["grid_id"].nunique(),
        "n_anios_revision_total": int(nacional["n_review_years"].sum()),
        "n_anios_revision_promedio": round(float(nacional["n_review_years"].mean()), 2),
        "n_sin_review_years": int((~nacional["has_review_years"]).sum()),
        "n_auto_sin_revision": int(nacional["is_auto_sin_revision"].sum()),
        "n_con_clase_rara": int(nacional["has_rare_class"].sum()),
    }])

    return pd.concat([resumen, total], ignore_index=True)


def build_resumen_tipo(nacional: pd.DataFrame) -> pd.DataFrame:
    resumen = (
        nacional.groupby(["utm", "dim_temporal", "dim_espacial", "sample_type"], dropna=False)
        .agg(
            n_rectangulos=("grid_id", "count"),
            n_anios_revision_total=("n_review_years", "sum"),
            n_anios_revision_promedio=("n_review_years", "mean"),
            n_con_clase_rara=("has_rare_class", "sum"),
        )
        .reset_index()
        .sort_values(["utm", "dim_temporal", "dim_espacial", "sample_type"])
    )

    resumen["n_anios_revision_promedio"] = resumen["n_anios_revision_promedio"].round(2)
    return resumen


def build_resumen_regla(nacional: pd.DataFrame) -> pd.DataFrame:
    resumen = (
        nacional.groupby(["utm", "review_rule"], dropna=False)
        .agg(
            n_rectangulos=("grid_id", "count"),
            n_anios_revision_total=("n_review_years", "sum"),
            n_anios_revision_promedio=("n_review_years", "mean"),
        )
        .reset_index()
        .sort_values(["utm", "review_rule"])
    )

    resumen["n_anios_revision_promedio"] = resumen["n_anios_revision_promedio"].round(2)
    return resumen


def build_resumen_prioridad(nacional: pd.DataFrame) -> pd.DataFrame:
    resumen = (
        nacional.groupby(["utm", "review_priority", "review_desc"], dropna=False)
        .agg(
            n_rectangulos=("grid_id", "count"),
            n_anios_revision_total=("n_review_years", "sum"),
        )
        .reset_index()
        .sort_values(["utm", "review_priority", "review_desc"])
    )

    return resumen


def build_resumen_anio(rect_year: pd.DataFrame) -> pd.DataFrame:
    if rect_year.empty:
        return pd.DataFrame(columns=[
            "year", "utm", "n_rectangulos_a_revisar",
            "n_train", "n_val", "n_test",
            "n_anual", "n_estable", "n_transicion",
        ])

    tmp = rect_year.copy()
    tmp["split"] = tmp["split"].fillna("sin_split").astype(str)
    tmp["dim_temporal"] = tmp["dim_temporal"].fillna("sin_dim_temporal").astype(str)

    base = (
        tmp.groupby(["year", "utm"], dropna=False)
        .size()
        .reset_index(name="n_rectangulos_a_revisar")
    )

    split_pivot = (
        pd.crosstab(
            index=[tmp["year"], tmp["utm"]],
            columns=tmp["split"],
        )
        .reset_index()
    )

    dim_pivot = (
        pd.crosstab(
            index=[tmp["year"], tmp["utm"]],
            columns=tmp["dim_temporal"],
        )
        .reset_index()
    )

    out = base.merge(split_pivot, on=["year", "utm"], how="left")
    out = out.merge(dim_pivot, on=["year", "utm"], how="left")

    rename = {
        "train": "n_train",
        "val": "n_val",
        "validation": "n_val",
        "test": "n_test",
        "anual": "n_anual",
        "estable": "n_estable",
        "transicion": "n_transicion",
    }
    out = out.rename(columns=rename)

    for col in ["n_train", "n_val", "n_test", "n_anual", "n_estable", "n_transicion"]:
        if col not in out.columns:
            out[col] = 0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)

    out = out.sort_values(["year", "utm"]).reset_index(drop=True)
    return out


def build_listado_revision_manual(nacional: pd.DataFrame) -> pd.DataFrame:
    """
    Genera el listado de revisión manual.

    IMPORTANTE:
    Esta versión conserva TODOS los rectángulos.
    No excluye review_priority = 0.
    No excluye review_desc = auto_sin_revision.
    """
    manual = nacional.copy()

    keep_cols = [
        "utm",
        "grid_id",
        "sample_type",
        "dim_temporal",
        "dim_espacial",
        "review_years",
        "n_review_years",
        "review_rule",
        "review_priority",
        "review_notes",
        "review_tier",
        "review_desc",
        "review_status",
        "split",
        "lulc_mode_id",
        "lulc_mode_name",
        "eco_dom_id",
        "eco_dom_name",
        "target_rare_class",
        "transition_pct",
        "stable_years",
        "max_stab_run",
        "ref_year",
        "ref_period",
        "ref_sensor",
        "fuente_plan",
    ]

    keep_cols = [c for c in keep_cols if c in manual.columns]

    manual = manual[keep_cols].copy()
    manual = manual.sort_values([
        "utm",
        "review_priority",
        "dim_temporal",
        "sample_type",
        "grid_id",
    ]).reset_index(drop=True)

    return manual


def validate_outputs(nacional: pd.DataFrame) -> None:
    """Imprime chequeos básicos."""
    print("\n=== VALIDACIÓN ===")

    n = len(nacional)
    n_unique = nacional["grid_id"].nunique()
    n_dup = n - n_unique
    n_empty_years = int((nacional["n_review_years"] == 0).sum())

    print(f"Rectángulos totales:        {n}")
    print(f"Grid ID únicos:             {n_unique}")
    print(f"Grid ID duplicados:         {n_dup}")
    print(f"Sin años de revisión:       {n_empty_years}")
    print(f"Años revisión total:        {int(nacional['n_review_years'].sum())}")
    print(f"Promedio años/rectángulo:   {round(float(nacional['n_review_years'].mean()), 2)}")

    if n_dup > 0:
        print("\nADVERTENCIA: hay grid_id duplicados.")
        dup = nacional[nacional["grid_id"].duplicated(keep=False)][
            ["utm", "grid_id", "fuente_plan"]
        ].sort_values("grid_id")
        print(dup.to_string(index=False))

    if n_empty_years > 0:
        print("\nADVERTENCIA: hay rectángulos sin review_years.")
        cols = ["utm", "grid_id", "sample_type", "dim_temporal", "review_rule"]
        cols = [c for c in cols if c in nacional.columns]
        print(nacional.loc[nacional["n_review_years"] == 0, cols].to_string(index=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consolida planes de revisión UTM18 y UTM19 en un plan nacional."
    )

    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"Carpeta raíz del proyecto. Default: {DEFAULT_ROOT}",
    )

    parser.add_argument(
        "--input",
        nargs="*",
        type=Path,
        default=DEFAULT_INPUTS,
        help="CSV de planes UTM a consolidar.",
    )

    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_REV_DIR,
        help=f"Carpeta de salida. Default: {DEFAULT_REV_DIR}",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    root = args.root.resolve()
    out_dir = resolve_path(args.out_dir, root)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_files = [resolve_path(p, root) for p in args.input]

    print("=== CONSOLIDACIÓN PLAN DE REVISIÓN NACIONAL ===")
    print(f"Root:   {root}")
    print(f"Salida: {out_dir}")

    print("\nArchivos de entrada:")
    for path in input_files:
        print(f"  {path}")

    frames = [load_plan(path, root) for path in input_files]

    nacional = prepare_national_plan(frames)
    rect_year = build_rect_year_table(nacional)

    resumen_utm = build_resumen_utm(nacional)
    resumen_tipo = build_resumen_tipo(nacional)
    resumen_regla = build_resumen_regla(nacional)
    resumen_prioridad = build_resumen_prioridad(nacional)
    resumen_anio = build_resumen_anio(rect_year)
    manual = build_listado_revision_manual(nacional)

    # Quitar columna auxiliar antes de exportar
    nacional_export = nacional.drop(columns=["review_years_list"], errors="ignore")

    outputs = {
        "plan_revision_nacional_scale300.csv": nacional_export,
        "listado_revision_manual.csv": manual,
        "resumen_revision_por_utm.csv": resumen_utm,
        "resumen_revision_por_tipo.csv": resumen_tipo,
        "resumen_revision_por_regla.csv": resumen_regla,
        "resumen_revision_por_prioridad.csv": resumen_prioridad,
        "resumen_revision_por_anio.csv": resumen_anio,
        "plan_revision_por_rectangulo_anio.csv": rect_year,
    }

    print("\nEscribiendo salidas:")
    for filename, table in outputs.items():
        path = out_dir / filename
        table.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  {path}")

    validate_outputs(nacional)

    print("\n=== RESUMEN POR UTM ===")
    print(resumen_utm.to_string(index=False))

    print("\n=== RESUMEN POR REGLA ===")
    print(resumen_regla.to_string(index=False))

    print("\nListo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())