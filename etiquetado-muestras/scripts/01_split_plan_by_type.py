#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
import sys
from pathlib import Path
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mb_labels.sample_paths import resolve_plan_path  # noqa: E402

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
    plan_path = resolve_plan_path(samples)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(plan_path, encoding="utf-8-sig")
    df["grid_id"] = df["grid_id"].astype(str)
    mapping = {"anual": "anuales", "estable": "estables", "transicion": "transiciones"}
    print(f"Plan base: {plan_path}")
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
    from mb_labels.taxonomy import is_transversal_rectangle
    trans = df[df.apply(is_transversal_rectangle, axis=1)].copy()
    if not trans.empty:
        out = out_dir / "plan_clases_transversales.csv"
        trans.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"clases_transversales: {len(trans)} rectángulos -> {out}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
