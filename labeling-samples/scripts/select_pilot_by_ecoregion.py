#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selecciona rectángulos anuales: al menos uno por ecorregión continental."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mb_labels.sample_paths import DEFAULT_SAMPLES_DIR, resolve_plan_path  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description="Selecciona 1 rectángulo anual por ecorregión.")
    p.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)
    p.add_argument("--include-grid-ids", nargs="*", default=None, help="grid_id a incluir siempre.")
    p.add_argument("--out-csv", type=Path, required=True)
    return p.parse_args()


def load_annual_pool(samples_dir: Path) -> pd.DataFrame:
    plan = pd.read_csv(resolve_plan_path(samples_dir), encoding="utf-8-sig")
    anu = plan[plan["dim_temporal"].astype(str).str.lower().eq("anual")].copy()
    sel_files = sorted(
        p
        for p in samples_dir.glob("final_samples/UTM*/**/seleccion_*.csv")
        if p.is_file() and "taxonomia" not in p.name.lower()
    )
    if not sel_files:
        raise FileNotFoundError(f"No hay seleccion_*.csv en {samples_dir / 'final_samples'}")
    sel = pd.concat([pd.read_csv(f, encoding="utf-8-sig") for f in sel_files]).drop_duplicates("grid_id")
    merged = anu.merge(sel, on="grid_id", how="inner", suffixes=("_plan", "_sel"))
    eco_col = "eco_dom_name_sel" if "eco_dom_name_sel" in merged.columns else "eco_dom_name"
    if eco_col not in merged.columns:
        raise ValueError("No se encontró columna de ecorregión en seleccion_*.csv")
    merged = merged.rename(columns={eco_col: "ecorregion"})
    return merged


def main() -> int:
    args = parse_args()
    pool = load_annual_pool(args.samples_dir)
    picks: list[pd.Series] = []
    seen_ecos: set[str] = set()
    seen_ids: set[str] = set()

    if args.include_grid_ids:
        for gid in args.include_grid_ids:
            sub = pool[pool["grid_id"].astype(str) == str(gid)]
            if sub.empty:
                print(f"ADVERTENCIA: grid_id no encontrado en pool anual: {gid}")
                continue
            row = sub.iloc[0]
            picks.append(row)
            seen_ids.add(str(row["grid_id"]))
            seen_ecos.add(str(row["ecorregion"]))

    for eco, sub in pool.groupby("ecorregion", sort=True):
        if eco in seen_ecos:
            continue
        row = sub.sort_values("grid_id").iloc[0]
        picks.append(row)
        seen_ids.add(str(row["grid_id"]))
        seen_ecos.add(str(eco))

    out = pd.DataFrame(picks)
    out_cols = ["grid_id", "ecorregion", "review_years", "dim_temporal"]
    for c in ("utm_zone", "utm_zone_sel", "grid_mode", "grid_mode_sel"):
        if c in out.columns:
            out_cols.append(c)
    out = out[[c for c in out_cols if c in out.columns]].drop_duplicates("grid_id")
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out_csv, index=False, encoding="utf-8-sig")

    print(f"Ecorregiones cubiertas: {len(seen_ecos)}")
    print(f"Rectángulos seleccionados: {len(out)}")
    print(out.to_string(index=False))
    print(f"\nGuardado: {args.out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
