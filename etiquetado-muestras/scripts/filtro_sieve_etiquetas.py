"""
====================================================================
FILTRO ESPACIAL (SIEVE) — limpieza de speckle en etiquetas raster
====================================================================
Elimina parches pequeños por clase (MMU en píxeles, conectividad 8) y
reasigna esos píxeles a la clase mayoritaria de la vecindad válida.

Requisitos: numpy, rasterio, scipy, pandas
====================================================================
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage

# ── PARÁMETROS ──────────────────────────────────────────────────────
INPUT_DIR = Path(r"/home/lserey/mapbiomas_land/tmp/labels_pilot_ecoregion")
OUTPUT_DIR = Path(r"/home/lserey/mapbiomas_land/tmp/labels_pilot_ecoregion/sieved")

NODATA = 0
CONNECTIVITY = 8
MAX_ITER = 50
OUTPUT_SUFFIX = "_sieve.tif"
OUT_REPORT_CSV = OUTPUT_DIR / "reporte_sieve.csv"

# Umbral = tamaño mínimo de parche en píxeles (conect-8).
# Se eliminan parches con tamaño < umbral; sus píxeles se reasignan
# a la clase mayoritaria vecina. 1 px = 900 m² = 0.09 ha.
MMU_PX = {
    # ── Estándar (6 px ≈ 0.54 ha): clases abundantes ──
    59: 6,  # Bosque Primario
    60: 6,  # Bosque Secundario
    3: 6,  # Bosque
    12: 6,  # Pastizal
    63: 6,  # Estepa
    66: 6,  # Matorral
    29: 6,  # Afloramiento Rocoso
    25: 6,  # Otra área sin vegetación
    9: 6,  # Silvicultura (transversal)
    18: 6,  # Agricultura (transversal)
    15: 6,  # Pastura
    # ── Protegida (2 px ≈ 0.18 ha): rara/crítica o pequeña por naturaleza ──
    11: 2,  # Humedal
    33: 2,  # Río, lago u océano
    34: 2,  # Hielo y nieve
    23: 2,  # Arena, Playa y Duna
    67: 2,  # Bosque Achaparrado
    61: 2,  # Salar
    24: 2,  # Infraestructura
}
DEFAULT_MMU_PX = 6
# ────────────────────────────────────────────────────────────────────

if CONNECTIVITY == 8:
    STRUCT = ndimage.generate_binary_structure(2, 2)
elif CONNECTIVITY == 4:
    STRUCT = ndimage.generate_binary_structure(2, 1)
else:
    raise ValueError(f"CONNECTIVITY no soportada: {CONNECTIVITY}")

OFFSETS_8 = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]


def find_input_rasters(input_dir: Path) -> list[Path]:
    """Busca *_classes.tif recursivamente; si no hay, todos los .tif planos."""
    classes = sorted(input_dir.rglob("*_classes.tif"))
    if classes:
        return classes
    return sorted(input_dir.glob("*.tif"))


def output_path(input_path: Path, input_root: Path, output_root: Path) -> Path:
    rel = input_path.relative_to(input_root)
    stem = input_path.stem
    if stem.endswith("_classes"):
        out_stem = f"{stem}_sieve"
    else:
        out_stem = f"{stem}_sieve"
    return output_root / rel.parent / f"{out_stem}.tif"


def mmu_for_class(class_id: int) -> int:
    return int(MMU_PX.get(int(class_id), DEFAULT_MMU_PX))


def mark_small_components(arr: np.ndarray, nodata: int) -> np.ndarray:
    """Devuelve máscara bool de píxeles a reasignar (parches < MMU por clase)."""
    to_remove = np.zeros(arr.shape, dtype=bool)
    present = sorted(int(v) for v in np.unique(arr) if int(v) != nodata)
    for cls in present:
        thresh = mmu_for_class(cls)
        class_mask = arr == cls
        labeled, n = ndimage.label(class_mask, structure=STRUCT)
        if n == 0:
            continue
        sizes = np.bincount(labeled.ravel())
        for lab in range(1, len(sizes)):
            if sizes[lab] < thresh:
                to_remove |= labeled == lab
    return to_remove


def reassign_pixels(arr: np.ndarray, to_remove: np.ndarray, nodata: int) -> np.ndarray:
    """
    Reasigna píxeles marcados propagando moda local 8-vecinos desde píxeles
    válidos; fallback a vecino más cercano (EDT) si quedan pendientes.
    """
    result = arr.copy()
    pending = to_remove.copy()

    for _ in range(MAX_ITER):
        if not pending.any():
            break
        py, px = np.nonzero(pending)
        assign_y: list[int] = []
        assign_x: list[int] = []
        assign_val: list[int] = []

        for y, x in zip(py, px):
            votes: list[int] = []
            for dy, dx in OFFSETS_8:
                ny, nx = y + dy, x + dx
                if 0 <= ny < arr.shape[0] and 0 <= nx < arr.shape[1]:
                    if not pending[ny, nx] and result[ny, nx] != nodata:
                        votes.append(int(result[ny, nx]))
            if votes:
                bc = np.bincount(votes)
                assign_y.append(int(y))
                assign_x.append(int(x))
                assign_val.append(int(bc.argmax()))

        if not assign_y:
            break
        ay = np.asarray(assign_y)
        ax = np.asarray(assign_x)
        av = np.asarray(assign_val)
        result[ay, ax] = av
        pending[ay, ax] = False

    if pending.any():
        valid = (~pending) & (result != nodata)
        if valid.any():
            _, (iy, ix) = ndimage.distance_transform_edt(
                ~valid, return_distances=True, return_indices=True
            )
            result[pending] = result[iy[pending], ix[pending]]
        else:
            print("  ADVERTENCIA: píxeles pendientes sin vecinos válidos; se dejan sin cambiar.")

    return result


def class_change_stats(before: np.ndarray, after: np.ndarray, nodata: int) -> pd.DataFrame:
    """Estadísticas por clase: píxeles reasignados y % de área que cambió."""
    rows = []
    present = sorted(int(v) for v in np.unique(before) if int(v) != nodata)
    for cls in present:
        mask_cls = before == cls
        n_total = int(mask_cls.sum())
        if n_total == 0:
            continue
        changed = mask_cls & (after != before)
        n_changed = int(changed.sum())
        rows.append(
            {
                "clase": cls,
                "pixeles_clase": n_total,
                "pixeles_reasignados": n_changed,
                "pct_area_cambiada": round(n_changed / n_total * 100.0, 3),
            }
        )
    return pd.DataFrame(rows)


def sieve_raster(path: Path, nodata: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with rasterio.open(path) as src:
        arr = src.read(1)
        nd = src.nodata if src.nodata is not None else nodata
    before = arr.copy()
    to_remove = mark_small_components(before, nd)
    # NODATA nunca se toca
    to_remove &= before != nd
    after = before.copy()
    if to_remove.any():
        after = reassign_pixels(before, to_remove, nd)
    return before, after, to_remove


def main() -> int:
    files = find_input_rasters(INPUT_DIR)
    if not files:
        raise FileNotFoundError(f"No hay .tif en {INPUT_DIR}")

    print("=== FILTRO SIEVE DE ETIQUETAS ===")
    print(f"Entrada:       {INPUT_DIR}")
    print(f"Salida:        {OUTPUT_DIR}")
    print(f"Conectividad:  {CONNECTIVITY}")
    print(f"MAX_ITER:      {MAX_ITER}")
    print(f"Archivos:      {len(files)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_rows: list[dict] = []
    totals: dict[int, dict[str, float]] = {}

    for path in files:
        print(f"\n── {path.name} ──")
        before, after, to_remove = sieve_raster(path, NODATA)
        n_reassigned = int(to_remove.sum())
        print(f"  Píxeles marcados (speckle): {n_reassigned}")

        out_path = output_path(path, INPUT_DIR, OUTPUT_DIR)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(path) as src:
            profile = src.profile.copy()
            profile.update(dtype=rasterio.int32, nodata=NODATA, compress="deflate")
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(after.astype(np.int32), 1)
        print(f"  Guardado: {out_path}")

        stats = class_change_stats(before, after, NODATA)
        if not stats.empty:
            print("  Cambios por clase:")
            for _, row in stats.iterrows():
                if row["pixeles_reasignados"] > 0:
                    print(
                        f"    clase {int(row['clase']):>2}: "
                        f"{int(row['pixeles_reasignados']):>6} px reasignados "
                        f"({row['pct_area_cambiada']:.2f}% del área de la clase)"
                    )
                cls = int(row["clase"])
                acc = totals.setdefault(cls, {"pixeles_clase": 0.0, "pixeles_reasignados": 0.0})
                acc["pixeles_clase"] += row["pixeles_clase"]
                acc["pixeles_reasignados"] += row["pixeles_reasignados"]
                report_rows.append(
                    {
                        "archivo": path.name,
                        "clase": cls,
                        "pixeles_clase": row["pixeles_clase"],
                        "pixeles_reasignados": row["pixeles_reasignados"],
                        "pct_area_cambiada": row["pct_area_cambiada"],
                        "mmu_px": mmu_for_class(cls),
                    }
                )

    df = pd.DataFrame(report_rows)
    if not df.empty:
        total_rows = []
        for cls, acc in sorted(totals.items()):
            n_cls = acc["pixeles_clase"]
            n_chg = acc["pixeles_reasignados"]
            pct = round(n_chg / n_cls * 100.0, 3) if n_cls else 0.0
            total_rows.append(
                {
                    "archivo": "__TOTAL__",
                    "clase": cls,
                    "pixeles_clase": int(n_cls),
                    "pixeles_reasignados": int(n_chg),
                    "pct_area_cambiada": pct,
                    "mmu_px": mmu_for_class(cls),
                }
            )
        df = pd.concat([df, pd.DataFrame(total_rows)], ignore_index=True)
        df.to_csv(OUT_REPORT_CSV, index=False, encoding="utf-8-sig")
        print(f"\nReporte CSV: {OUT_REPORT_CSV}")

        print("\n── Resumen total por clase ──")
        tot = df[df["archivo"] == "__TOTAL__"].sort_values("clase")
        print(tot.to_string(index=False))

        protected = {11, 33, 34, 23, 67, 61, 24}
        print("\n── Clases protegidas (MMU=2 px) — verificar pérdida de área ──")
        for cls in sorted(protected):
            sub = tot[tot["clase"] == cls]
            if sub.empty:
                print(f"  clase {cls:>2}: no presente en la muestra")
            else:
                r = sub.iloc[0]
                print(
                    f"  clase {cls:>2}: {r['pct_area_cambiada']:.3f}% área reasignada "
                    f"({int(r['pixeles_reasignados'])} px)"
                )

    print("\nListo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
