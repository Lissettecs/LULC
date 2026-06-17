#!/usr/bin/env python3
"""
Auditoria de balanceo nacional (piloto v2) contra metas de la tabla de falencias.

Uso:
  python scripts/06_auditoria_balanceo.py
  python scripts/06_auditoria_balanceo.py --input muestras_finales/seleccion_*_scale300.geojson
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd

from balanceo_seleccion import OTRA_SIN_VEG_ID, PASTIZAL_MODE_ID
from clases_criticas import CRITICAL_CLASS_NAMES, annotate_critical_classes

from rutas_proyecto import FINALES_DIR, GRILLAS_ROOT, REVISION_DIR

ROOT = GRILLAS_ROOT
DEFAULT_GLOB = str(FINALES_DIR / "seleccion_grilla_ssl4eo_muestras_UTM*_scale300.geojson")

ARENA_ID = 23
SALAR_ID = 61
BOSQUE_NORTE_ID = 3
ARID_ECOS = {1, 2, 3, 4, 5}
PRIORITY_ECOS = {7, 8, 9, 12, 15}


def infer_utm(path: Path) -> str:
    name = path.stem.upper()
    if "UTM18" in name:
        return "UTM18"
    if "UTM19" in name:
        return "UTM19"
    return "UTM"


def load(paths: list[Path]) -> pd.DataFrame:
    frames = []
    for p in paths:
        gdf = gpd.read_file(p)
        df = pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))
        df["utm"] = infer_utm(p)
        frames.append(df)
    if not frames:
        raise FileNotFoundError("No hay archivos de seleccion.")
    out = pd.concat(frames, ignore_index=True)
    return annotate_critical_classes(out)


def pct_split(df: pd.DataFrame) -> dict[str, int]:
    return df["split"].value_counts().to_dict() if "split" in df.columns else {}


def status(ok: bool) -> str:
    return "OK" if ok else "REVISAR"


def count_cross_zone_overlaps(paths: list[Path], tol_deg2: float = 1e-11) -> tuple[int, int]:
    """Pares con solape geometrico entre husos UTM distintos (WGS84)."""
    by_utm: dict[str, gpd.GeoDataFrame] = {}
    for path in paths:
        gdf = gpd.read_file(path).to_crs(4326)
        by_utm[infer_utm(path)] = gdf.reset_index(drop=True)
    if len(by_utm) < 2:
        return 0, 0
    keys = sorted(by_utm)
    pairs = 0
    involved: set[str] = set()
    for i, left_key in enumerate(keys):
        left = by_utm[left_key]
        for right_key in keys[i + 1:]:
            right = by_utm[right_key]
            for _, row_a in left.iterrows():
                geom_a = row_a.geometry
                area_a = geom_a.area
                if area_a <= 0:
                    continue
                hits = right[right.intersects(geom_a)]
                for _, row_b in hits.iterrows():
                    inter = geom_a.intersection(row_b.geometry)
                    if inter.is_empty or inter.area <= tol_deg2:
                        continue
                    pairs += 1
                    involved.add(str(row_a.get("grid_id", "")))
                    involved.add(str(row_b.get("grid_id", "")))
    return pairs, len(involved)


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditoria balanceo seleccion nacional.")
    parser.add_argument("--input", nargs="*", type=Path, default=None)
    args = parser.parse_args()

    if args.input:
        paths = args.input
    else:
        paths = sorted(FINALES_DIR.glob("seleccion_grilla_ssl4eo_muestras_UTM*_scale300.geojson"))

    df = load(paths)
    n = len(df)
    utm18 = df[df["utm"] == "UTM18"]
    utm19 = df[df["utm"] == "UTM19"]
    cross_pairs, cross_ids = count_cross_zone_overlaps(paths)

    mode = pd.to_numeric(df.get("lulc_mode_id", -9999), errors="coerce").fillna(-9999).astype(int)
    otra_n = int((mode == OTRA_SIN_VEG_ID).sum())
    past_n = int((mode == PASTIZAL_MODE_ID).sum())
    t_h = df[df["sample_type"] == "transicion_homogenea"]
    split = pct_split(df)

    crit = df.get("target_rare_class", pd.Series("", index=df.index)).astype(str).str.strip()
    arena_n = int(crit.eq(CRITICAL_CLASS_NAMES[ARENA_ID]).sum())
    salar_n = int(crit.eq(CRITICAL_CLASS_NAMES[SALAR_ID]).sum())
    past_dedicated = int(crit.eq("Pastizal").sum())
    bosque = df[
        df.get("target_rare_class", pd.Series("", index=df.index)).astype(str).str.contains(
            "Formacion_boscosa|Bosque", case=False, regex=True, na=False
        )
        | (pd.to_numeric(df.get("target_rare_class_id", -9999), errors="coerce") == BOSQUE_NORTE_ID)
    ]

    eco_counts = df.groupby("eco_dom_id").size()
    deficit_ecos = {e: int(eco_counts.get(e, 0)) for e in PRIORITY_ECOS}

    arid_trans = df[
        df["sample_type"].astype(str).str.startswith("transicion")
        & df["eco_dom_id"].astype(int).isin(ARID_ECOS)
    ]

    lines = [
        "=== AUDITORIA BALANCEO NACIONAL ===",
        f"Archivos: {len(paths)}  Muestras: {n}",
        "",
        f"[1] Total nacional     {n:4d}   meta 300-350        {status(300 <= n <= 350)}",
        f"[2] UTM18 / UTM19      {len(utm18):4d} / {len(utm19):4d}   meta ~120 / ~140-175   "
        f"{status(100 <= len(utm18) <= 130 and 140 <= len(utm19) <= 180)}",
        f"[3] Estables UTM18     "
        f"e_h={(utm18['sample_type'] == 'estable_homogenea').sum():2d}  "
        f"e_s={(utm18['sample_type'] == 'estable_simple_media').sum():2d}   "
        f"meta e_h>=8 e_s>=10    {status((utm18['sample_type'] == 'estable_homogenea').sum() >= 8)}",
        f"[4] transicion_homog.  {len(t_h):4d}   meta 20-30           {status(20 <= len(t_h) <= 35)}",
        f"    UTM19 t_h          {(utm19['sample_type'] == 'transicion_homogenea').sum():4d}   meta >=10           "
        f"{status((utm19['sample_type'] == 'transicion_homogenea').sum() >= 10)}",
        f"[5] Trans aridas E1-E5 {len(arid_trans):4d}   meta >0 por eco      {status(len(arid_trans) >= 5)}",
        f"[6] Ecos prioritarias  {deficit_ecos}  meta >=6 c/u",
        f"[7] Otra_sin_vegetacion {otra_n:3d}   meta cap ~40           {status(otra_n <= 45)}",
        f"[8] Pastizal modal     {past_n:3d}   dedicadas={past_dedicated:2d}  meta >=6  "
        f"{status(past_n >= 6 or past_dedicated >= 6)}",
        f"[9] Salar criticas     {salar_n:3d}   meta 8-12              {status(8 <= salar_n <= 14)}",
        f"[10] Arena criticas    {arena_n:3d}   meta 8-12              {status(8 <= arena_n <= 14)}",
        f"[11] Bosque norte n    {len(bosque):3d}   split val/test     ",
    ]

    if not bosque.empty and "split" in bosque.columns:
        bs = bosque["split"].value_counts().to_dict()
        lines[-1] += f" train={bs.get('train',0)} val={bs.get('val',0)} test={bs.get('test',0)}  " + status(
            bs.get("val", 0) >= 1 and bs.get("test", 0) >= 1
        )
    else:
        lines[-1] += status(False)

    train = split.get("train", 0)
    val = split.get("val", 0)
    test = split.get("test", 0)
    lines.extend([
        f"[12] Split 70/15/15     train={train} val={val} test={test}  "
        f"{status(abs(train / max(n, 1) - 0.70) < 0.08 and val >= 25)}",
        f"[13] Tier 0 auto          {(df.get('review_tier', 99) == 0).sum():3d}   UTM18/19 "
        f"{(utm18.get('review_tier', pd.Series()) == 0).sum()}/{(utm19.get('review_tier', pd.Series()) == 0).sum()}",
        f"[14] Solape UTM18/19      pares={cross_pairs:3d} ids={cross_ids:3d}   meta 0   "
        f"{status(cross_pairs == 0)}",
        "",
        "-- Por tipo --",
        df["sample_type"].value_counts().to_string(),
        "",
        "-- Por UTM x tipo (transicion_homogenea) --",
        df.groupby(["utm", "sample_type"]).size().unstack(fill_value=0).get(
            "transicion_homogenea", pd.Series(dtype=int)
        ).to_string()
        if "transicion_homogenea" in df["sample_type"].values
        else "(sin transicion_homogenea)",
    ])

    report = "\n".join(lines)
    print(report)

    out = REVISION_DIR / "AUDITORIA_BALANCEO.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report + "\n", encoding="utf-8")
    print(f"\nGuardado: {out}")


if __name__ == "__main__":
    main()
