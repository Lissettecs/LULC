#!/usr/bin/env python3
"""
Revision completa de rectangulos seleccionados (seleccion_rectangulos.py).

Genera tablas CSV y un informe de texto con:
  - Resumen general por UTM
  - Muestras por tipo (dim_temporal x dim_espacial)
  - Muestras por ecorregion x clase modal
  - Muestras por ecorregion x tipo de muestra
  - Clase modal x tipo de muestra
  - Clases criticas (CRITICAL_CLASS_IDS en caracterizacion_grillas_gee.py)
  - Calidad media por tipo
  - Split train/val/test y tier de revision

Uso:
  python scripts/05_revision_seleccion_rectangulos.py
  python scripts/05_revision_seleccion_rectangulos.py --utm 18 19
  python scripts/05_revision_seleccion_rectangulos.py --input muestras_finales/*.geojson
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from io import StringIO
from pathlib import Path

import geopandas as gpd
import pandas as pd

from clases_criticas import (
    CRITICAL_CLASS_NAMES,
    annotate_critical_classes,
    critical_summary,
)

from rutas_proyecto import FINALES_DIR, GRILLAS_ROOT, REVISION_DIR

ROOT = GRILLAS_ROOT
DEFAULT_GLOB = "seleccion_grilla_ssl4eo_muestras_UTM*_scale300.geojson"
DEFAULT_OUT = REVISION_DIR


def clean_label(value) -> str:
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", "-9999"):
        return "sin_nombre"
    return text


def infer_utm(path: Path) -> str:
    name = path.stem.upper()
    if "UTM18" in name:
        return "UTM18"
    if "UTM19" in name:
        return "UTM19"
    return "UTM"


def load_selections(paths: list[Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for p in paths:
        gdf = gpd.read_file(p)
        df = pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))
        df["utm"] = infer_utm(p)
        df["fuente"] = p.name
        frames.append(df)
    if not frames:
        raise FileNotFoundError("No se encontraron archivos de seleccion.")
    return pd.concat(frames, ignore_index=True)


def prepare_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ecorregion"] = df.get("eco_dom_name", pd.Series(dtype=object)).map(clean_label)
    df["clase_modal"] = df.get("lulc_mode_name", pd.Series(dtype=object)).map(clean_label)
    df["clase_ultimo"] = df.get("lulc_last_name", pd.Series(dtype=object)).map(clean_label)
    df["tipo_muestra"] = df.get("sample_type", pd.Series(dtype=object)).map(clean_label)
    df["dim_temporal"] = df.get("dim_temporal", pd.Series(dtype=object)).map(clean_label)
    df["dim_espacial"] = df.get("dim_espacial", pd.Series(dtype=object)).map(clean_label)
    df["grid_mode"] = df.get("grid_mode", pd.Series(dtype=object)).map(clean_label)
    df["split"] = df.get("split", pd.Series(dtype=object)).map(clean_label)
    df["clase_rara"] = df.get("target_rare_class", pd.Series(dtype=object)).fillna("").map(
        lambda x: clean_label(x) if str(x).strip() else ""
    )
    for col in ["achap_presence_pct", "achaparrado_pct", "valid_area_pct", "lulc_mode_pct",
                "transition_pct", "max_stab_run", "shannon_idx", "conf_risk_pct",
                "critical_pct", "eco_dom_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = annotate_critical_classes(df)
    achap_name = CRITICAL_CLASS_NAMES[67]
    df["tiene_achaparrado"] = df["clases_criticas"].str.contains(
        achap_name, regex=False, na=False
    )
    return df


def count_table(df: pd.DataFrame, group_cols: list[str], name: str = "n_muestras") -> pd.DataFrame:
    out = (
        df.groupby(group_cols, dropna=False)
        .size()
        .reset_index(name=name)
        .sort_values(group_cols)
    )
    return out


def pivot_count(df: pd.DataFrame, index: str, columns: str) -> pd.DataFrame:
    pt = pd.crosstab(df[index], df[columns], margins=True, margins_name="TOTAL")
    return pt.sort_index()


def quality_summary(df: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "valid_area_pct", "eco_dom_pct", "lulc_mode_pct", "transition_pct",
        "max_stab_run", "shannon_idx", "conf_risk_pct", "critical_pct",
        "achap_presence_pct", "achaparrado_pct",
    ]
    avail = [c for c in metrics if c in df.columns]
    if not avail:
        return pd.DataFrame()
    return (
        df.groupby(["utm", "tipo_muestra"], dropna=False)[avail]
        .agg(["count", "mean", "min", "max"])
        .round(2)
    )


def resumen_general(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for utm, g in df.groupby("utm"):
        rows.append({
            "utm": utm,
            "n_muestras": len(g),
            "n_grid_id_unicos": g["grid_id"].nunique(),
            "n_ecorregiones": g["ecorregion"].nunique(),
            "n_clases_modales": g["clase_modal"].nunique(),
            "n_tipos_muestra": g["tipo_muestra"].nunique(),
            "n_clases_criticas": int(g["tiene_clase_critica"].sum()),
            "n_achaparrado": int(g["tiene_achaparrado"].sum()),
            "n_homogeneo": int((g["grid_mode"] == "homogeneo").sum()),
            "n_mixto": int((g["grid_mode"] == "mixto").sum()),
        })
    total = df.copy()
    total["utm"] = "TOTAL"
    rows.append({
        "utm": "TOTAL",
        "n_muestras": len(total),
        "n_grid_id_unicos": total["grid_id"].nunique(),
        "n_ecorregiones": total["ecorregion"].nunique(),
        "n_clases_modales": total["clase_modal"].nunique(),
        "n_tipos_muestra": total["tipo_muestra"].nunique(),
        "n_clases_criticas": int(total["tiene_clase_critica"].sum()),
        "n_achaparrado": int(total["tiene_achaparrado"].sum()),
        "n_homogeneo": int((total["grid_mode"] == "homogeneo").sum()),
        "n_mixto": int((total["grid_mode"] == "mixto").sum()),
    })
    return pd.DataFrame(rows)


def build_text_report(
    df: pd.DataFrame,
    general: pd.DataFrame,
    por_tipo: pd.DataFrame,
    eco_clase_pivot: pd.DataFrame,
    eco_tipo_pivot: pd.DataFrame,
    crit: pd.DataFrame,
) -> str:
    buf = StringIO()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    buf.write(f"REVISION SELECCION RECTANGULOS SSL4EO-L\n")
    buf.write(f"Generado: {now}\n")
    buf.write("=" * 72 + "\n\n")

    buf.write("1. RESUMEN GENERAL\n")
    buf.write(general.to_string(index=False))
    buf.write("\n\n")

    buf.write("2. POR TIPO DE MUESTRA\n")
    buf.write(por_tipo.to_string(index=False))
    buf.write("\n\n")

    buf.write("3. ECORREGION x CLASE MODAL (pivot)\n")
    buf.write(eco_clase_pivot.to_string())
    buf.write("\n\n")

    buf.write("4. ECORREGION x TIPO DE MUESTRA (pivot)\n")
    buf.write(eco_tipo_pivot.to_string())
    buf.write("\n\n")

    crit = df[df["tiene_clase_critica"]].copy()
    if not crit.empty:
        buf.write("5. CLASES CRITICAS\n")
        buf.write(critical_summary(crit).to_string(index=False))
        buf.write("\n\n")
        cols = [c for c in [
            "utm", "grid_id", "ecorregion", "clase_modal", "clase_ultimo",
            "clases_criticas", "tipo_muestra", "critical_pct",
            "achap_presence_pct", "achaparrado_pct", "split",
        ] if c in crit.columns]
        buf.write(crit[cols].to_string(index=False))
        buf.write("\n\n")

    buf.write("6. SPLIT TRAIN / VAL / TEST\n")
    buf.write(count_table(df, ["utm", "split"]).to_string(index=False))
    buf.write("\n\n")

    buf.write("7. TIER DE REVISION\n")
    if "review_tier" in df.columns:
        buf.write(count_table(df, ["utm", "review_tier", "review_desc"]).to_string(index=False))
    buf.write("\n\n")

    buf.write("8. MUESTRAS ANUALES (ano de referencia)\n")
    anuales = df[df["dim_temporal"] == "anual"]
    if anuales.empty:
        buf.write("  (ninguna)\n")
    elif "ref_period" in anuales.columns:
        buf.write(
            count_table(anuales, ["utm", "tipo_muestra", "ref_period", "ref_year"])
            .to_string(index=False)
        )
    buf.write("\n")

    return buf.getvalue()


def run_revision(df: pd.DataFrame, out_dir: Path, tag: str = "") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{tag}" if tag else ""

    general = resumen_general(df)
    por_tipo = count_table(df, ["utm", "dim_temporal", "dim_espacial", "tipo_muestra"])
    eco_clase_long = count_table(df, ["utm", "ecorregion", "clase_modal"])
    eco_clase_pivot = pivot_count(df, "ecorregion", "clase_modal")
    eco_tipo_long = count_table(df, ["utm", "ecorregion", "tipo_muestra"])
    eco_tipo_pivot = pivot_count(df, "ecorregion", "tipo_muestra")
    clase_tipo_long = count_table(df, ["utm", "clase_modal", "tipo_muestra"])
    clase_tipo_pivot = pivot_count(df, "clase_modal", "tipo_muestra")
    grid_mode_tipo = count_table(df, ["utm", "grid_mode", "tipo_muestra"])
    split_tbl = count_table(df, ["utm", "split", "tipo_muestra"])
    crit = df[df["tiene_clase_critica"]].copy()
    achap = df[df["tiene_achaparrado"]].copy()
    crit_resumen = critical_summary(df)
    calidad = quality_summary(df)

    exports = {
        f"01_resumen_general{suffix}.csv": general,
        f"02_por_tipo_muestra{suffix}.csv": por_tipo,
        f"03_eco_x_clase_long{suffix}.csv": eco_clase_long,
        f"03_eco_x_clase_pivot{suffix}.csv": eco_clase_pivot,
        f"04_eco_x_tipo_long{suffix}.csv": eco_tipo_long,
        f"04_eco_x_tipo_pivot{suffix}.csv": eco_tipo_pivot,
        f"05_clase_x_tipo_long{suffix}.csv": clase_tipo_long,
        f"05_clase_x_tipo_pivot{suffix}.csv": clase_tipo_pivot,
        f"06_grid_mode_x_tipo{suffix}.csv": grid_mode_tipo,
        f"07_split_x_tipo{suffix}.csv": split_tbl,
        f"08_clases_criticas_resumen{suffix}.csv": crit_resumen,
        f"08_clases_criticas_detalle{suffix}.csv": crit,
        f"08_achaparrado_detalle{suffix}.csv": achap,
    }

    for fname, table in exports.items():
        path = out_dir / fname
        if isinstance(table, pd.DataFrame) and table.empty and (
            "achaparrado" in fname or "clases_criticas" in fname
        ):
            continue
        table.to_csv(path, index=True if table.index.name or isinstance(table.index, pd.MultiIndex) else False,
                     encoding="utf-8-sig")

    if not calidad.empty:
        calidad.to_csv(out_dir / f"09_calidad_por_tipo{suffix}.csv", encoding="utf-8-sig")

    report = build_text_report(df, general, por_tipo, eco_clase_pivot, eco_tipo_pivot, crit)
    report_path = out_dir / f"REVISION_COMPLETA{suffix}.txt"
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\nArchivos en: {out_dir}")


def discover_inputs(glob_pat: str, utm_filter: list[str] | None) -> list[Path]:
    if "/" in glob_pat or "\\" in glob_pat:
        base = Path(glob_pat).parent
        pattern = Path(glob_pat).name
    else:
        base = FINALES_DIR
        pattern = glob_pat
    paths = sorted(base.glob(pattern))
    if utm_filter:
        utm_set = {u.upper().replace("UTM", "UTM") for u in utm_filter}
        paths = [p for p in paths if any(u in p.stem.upper() for u in utm_set)]
    return paths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Revision completa de seleccion de rectangulos.")
    p.add_argument("--input", nargs="*", type=Path, default=None,
                   help="Archivos GPKG/CSV/GeoJSON de seleccion.")
    p.add_argument("--glob", default=DEFAULT_GLOB,
                   help=f"Patron si no se pasa --input (defecto: {DEFAULT_GLOB})")
    p.add_argument("--utm", nargs="*", choices=["18", "19", "UTM18", "UTM19"],
                   help="Filtrar husos al autodetectar.")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.input:
        paths = [p if p.is_absolute() else ROOT / p for p in args.input]
    else:
        paths = discover_inputs(args.glob, args.utm)

    paths = [p for p in paths if p.exists()]
    if not paths:
        print("No se encontraron selecciones. Rutas buscadas:")
        print(f"  {ROOT / args.glob}")
        return 1

    print("Fuentes:")
    for p in paths:
        print(f"  {p}")

    df = prepare_columns(load_selections(paths))

    run_revision(df, args.output_dir, tag="")

    for utm in sorted(df["utm"].unique()):
        sub = df[df["utm"] == utm]
        run_revision(sub, args.output_dir, tag=utm)

    return 0


if __name__ == "__main__":
    sys.exit(main())
