#!/usr/bin/env python3
"""
Anade columnas de taxonomia N1/N2/N3 a grillas ya caracterizadas.

IMPORTANTE: Solo es fiel si mode_id / lulc_mode_id son IDs nativos C2 (class_level=n3).
Las grillas scale300 actuales (_general) deben re-caracterizarse con:
  python caracterizacion_grillas_gee.py --class-level n3 ...

Ejemplo:
  python scripts/04_anotar_taxonomia_grillas.py -i muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM19_scale300.csv
  python scripts/04_anotar_taxonomia_grillas.py -i "muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM*_scale300.csv"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from taxonomia_clases import annotate_dataframe

ROOT = Path(__file__).resolve().parent


def resolve_input_paths(pattern: Path) -> list[Path]:
    """Expande globs (*, ?) en Windows/Linux."""
    raw = str(pattern)
    if any(ch in raw for ch in "*?[]"):
        base = pattern.parent if pattern.is_absolute() else (ROOT / pattern.parent)
        if not base.is_absolute():
            base = (ROOT / pattern.parent).resolve()
        matches = sorted(base.glob(pattern.name))
        if not matches:
            # Intentar relativo al cwd por si el usuario paso ruta mixta
            matches = sorted(Path.cwd().glob(raw))
    else:
        path = pattern if pattern.is_absolute() else (ROOT / pattern)
        matches = [path.resolve()] if path.exists() else [pattern.resolve()]
    return [p for p in matches if p.is_file()]


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    import geopandas as gpd
    if path.suffix.lower() == ".zip":
        return gpd.read_file(path)
    return gpd.read_file(path)


def write_table(df, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        out = df.drop(columns="geometry", errors="ignore")
        out.to_csv(path, index=False)
        return
    import geopandas as gpd
    if isinstance(df, gpd.GeoDataFrame):
        df.to_file(path, driver="GPKG" if path.suffix.lower() == ".gpkg" else "GeoJSON")
    else:
        gpd.GeoDataFrame(df).to_file(path, driver="GPKG")


def resolve_id_columns(df: pd.DataFrame) -> list[tuple[str, str]]:
    pairs = []
    if "lulc_mode_id" in df.columns:
        pairs.append(("lulc_mode_id", ""))
    elif "mode_id" in df.columns:
        pairs.append(("mode_id", ""))
    if "lulc_last_id" in df.columns:
        pairs.append(("lulc_last_id", "last"))
    elif "last_id" in df.columns:
        pairs.append(("last_id", "last"))
    return pairs


def _summary_series(df: pd.DataFrame, col: str) -> pd.Series | None:
    if col not in df.columns:
        return None
    s = df[col]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    return s


def annotate_file(input_path: Path, output_path: Path | None) -> int:
    df = read_table(input_path)
    if "cls_lvl" in df.columns and (df["cls_lvl"] == "general").any():
        print(
            f"AVISO [{input_path.name}]: cls_lvl=general detectado. Los IDs pueden ser agregados; "
            "re-caracteriza con --class-level n3 para taxonomia fiel.",
            file=sys.stderr,
        )

    pairs = resolve_id_columns(df)
    if not pairs:
        print(f"Error [{input_path}]: no hay columnas mode_id / lulc_mode_id.", file=sys.stderr)
        return 1

    out = df
    for id_col, prefix in pairs:
        out = annotate_dataframe(out, id_col=id_col, prefix=prefix)

    dest = output_path or input_path.with_stem(input_path.stem + "_taxonomia_n3")
    write_table(out, dest)
    print(f"Anotado: {dest}")
    n3 = _summary_series(out, "n3_nm")
    if n3 is not None:
        print(n3.value_counts().head(10).to_string())
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Anota taxonomia N1/N2/N3 en tablas de grilla.")
    p.add_argument(
        "--input", "-i", type=Path, required=True,
        help="Archivo CSV/GPKG o patron glob (ej. seleccion_*_UTM*_scale300.csv)",
    )
    p.add_argument("--output", "-o", type=Path, default=None,
                   help="Salida unica (solo valido con un unico archivo de entrada).")
    args = p.parse_args(argv)

    inputs = resolve_input_paths(args.input)
    if not inputs:
        print(f"Error: no se encontraron archivos para: {args.input}", file=sys.stderr)
        return 1
    if args.output and len(inputs) > 1:
        print("Error: --output solo admite un unico archivo de entrada.", file=sys.stderr)
        return 1

    rc = 0
    for path in inputs:
        if annotate_file(path, args.output) != 0:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
