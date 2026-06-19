#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
DEFAULT_SAMPLES_DIR = Path("/home/lserey/mapbiomas_land/prod/samples")

def parse_args():
    p = argparse.ArgumentParser(description="Divide listado_revision_manual.csv por tipo de revisión.")
    p.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)
    p.add_argument("--out-dir", type=Path, default=None)
    return p.parse_args()

def main() -> int:
    args = parse_args()
    samples = args.samples_dir
    out_dir = args.out_dir or (samples / "planes_por_tipo")
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(samples / "listado_revision_manual.csv", encoding="utf-8-sig")
    df["grid_id"] = df["grid_id"].astype(str)
    mapping = {"anual": "anuales", "estable": "estables", "transicion": "transiciones"}
    print(f"Plan base: {samples / 'listado_revision_manual.csv'}")
    print(f"Rectángulos: {len(df)}")
    for dim, folder in mapping.items():
        sub = df[df["dim_temporal"].astype(str).str.lower().eq(dim)].copy()
        out = out_dir / f"plan_{folder}.csv"
        sub.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"{folder}: {len(sub)} rectángulos -> {out}")
    if "target_rare_class" in df.columns:
        rare = df[df["target_rare_class"].fillna("").astype(str).str.strip().ne("")].copy()
        out = out_dir / "plan_clases_raras.csv"
        rare.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"clases_raras: {len(rare)} rectángulos -> {out}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
