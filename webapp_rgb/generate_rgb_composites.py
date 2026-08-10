#!/usr/bin/env python3
"""
Genera GeoTIFF RGB por rectángulo etiquetado, con pirámides internas.

Composiciones (R/G/B):
  true_color:    red_median / green_median / blue_median
  swir1-nir-red: swir1_median / nir_median / red_median
  nir-red-green: nir_median / red_median / green_median

Uso:
  /home/lserey/.conda/envs/mb_labels/bin/python generate_rgb_composites.py
  /home/lserey/.conda/envs/mb_labels/bin/python generate_rgb_composites.py \\
      --year 2015 --mosaic-kind 184
  /home/lserey/.conda/envs/mb_labels/bin/python generate_rgb_composites.py \\
      --year 2009 --mosaic-kind 11b --force
  /home/lserey/.conda/envs/mb_labels/bin/python generate_rgb_composites.py \\
      --grid-id SI-19-Y-A_2x2_c000_r001 --force
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

# ═══ parámetros ═══════════════════════════════════════════════════════════════
MAPBIOMAS_ROOT = Path("/home/lserey/mapbiomas_land")
YEAR = 2015
MOSAIC_KIND = "184"  # 184 | 11b
OUTPUT_DTYPE = "float32"

# Índices rasterio 1-based por layout de mosaico
BAND_IDX_184 = {
    "blue_median": 3,
    "green_median": 46,
    "red_median": 128,
    "nir_median": 107,
    "swir1_median": 164,
}
BAND_IDX_11B = {
    "blue_median": 1,
    "green_median": 2,
    "red_median": 3,
    "nir_median": 4,
    "swir1_median": 5,
}

COMPOSITES = {
    "true_color": ("red_median", "green_median", "blue_median"),
    "swir1-nir-red": ("swir1_median", "nir_median", "red_median"),
    "nir-red-green": ("nir_median", "red_median", "green_median"),
}

MOSAIC_NODATA = -9999.0
STRETCH_P_LOW = 2.0
STRETCH_P_HIGH = 98.0
# Pirámides hasta ~32 px (más zoom out que el umbral previo de 64)
OVERVIEW_MIN_SIZE = 32
COMPRESS = "deflate"

# Globals reasignados en main()
LABELING_ROOT = MAPBIOMAS_ROOT / "prod" / "04_labeling_cim" / str(YEAR)
SEGMENTATION_ROOT = MAPBIOMAS_ROOT / "prod" / "03_segmentation_cim" / str(YEAR)
MOSAIC_ROOT = MAPBIOMAS_ROOT / "mosaic_184bands_mask_water" / str(YEAR)
BAND_IDX = dict(BAND_IDX_184)
# ═════════════════════════════════════════════════════════════════════════════


def normalize_mosaic_kind(kind: str) -> str:
    raw = kind.strip().lower()
    aliases = {
        "184": "184",
        "184b": "184",
        "184_mask": "184",
        "184_mask_water": "184",
        "mask_water": "184",
        "11": "11b",
        "11b": "11b",
        "11bands": "11b",
        "11b_mask": "11b",
        "11b_mask_water": "11b",
        "mosaic_11bands": "11b",
        "mosaic_11bands_mask_water": "11b",
    }
    out = aliases.get(raw, raw)
    if out not in ("184", "11b"):
        raise ValueError(f"mosaic-kind inválido: {kind!r} (use 184 o 11b)")
    return out


def mosaic_root_for_kind(kind: str, year: int) -> Path:
    k = normalize_mosaic_kind(kind)
    if k == "11b":
        return MAPBIOMAS_ROOT / "mosaic_11bands_mask_water" / str(year)
    return MAPBIOMAS_ROOT / "mosaic_184bands_mask_water" / str(year)


def band_idx_for_kind(kind: str) -> dict[str, int]:
    k = normalize_mosaic_kind(kind)
    return dict(BAND_IDX_11B if k == "11b" else BAND_IDX_184)


def resolve_mosaic_path(mosaic_root: Path, tile: str, year: int, kind: str) -> Path | None:
    """Resuelve mosaico masked para (tile, year, kind)."""
    tile_u = tile.upper()
    k = normalize_mosaic_kind(kind)
    search_roots = [mosaic_root]
    year_dir = mosaic_root / str(year)
    if year_dir.is_dir() and year_dir != mosaic_root:
        search_roots.append(year_dir)

    matches: list[Path] = []
    for base in search_roots:
        if k == "11b":
            matches.extend(sorted(base.glob(f"CHILE-{tile_u}-{year}-*-11B*_masked.tif")))
            if not matches:
                matches.extend(sorted(base.glob(f"CHILE-{tile_u}-{year}-*-11B.tif")))
        else:
            # Preferir 184 masked (evitar *11B*)
            all_masked = sorted(base.glob(f"CHILE-{tile_u}-{year}-*_masked.tif"))
            matches.extend([p for p in all_masked if "11B" not in p.name])
            if not matches:
                matches.extend(all_masked)
    if not matches:
        return None
    prefer = [p for p in matches if "184F-HARM" in p.name]
    return prefer[0] if prefer else matches[0]


def overview_factors(width: int, height: int, min_size: int = OVERVIEW_MIN_SIZE) -> list[int]:
    """Factores de pirámide hasta que el overview quede ~min_size px."""
    factors: list[int] = []
    f = 2
    max_dim = max(width, height)
    while max_dim // f >= min_size:
        factors.append(f)
        f *= 2
    return factors or [2]


def descubrir_rectangulos(
    labeling_root: Path,
    year: int,
    *,
    mosaic_kind: str,
) -> list[dict]:
    """Inventario de rectángulos desde labeling_summary.json."""
    rects: list[dict] = []
    for summary in sorted(labeling_root.glob("*/*/*_labeling_summary.json")):
        grid_id = summary.parent.name
        tile = summary.parent.parent.name
        labels = sorted(
            (SEGMENTATION_ROOT / tile / grid_id).glob(f"{grid_id}_{year}_*_labels.tif")
        )
        mosaic = resolve_mosaic_path(MOSAIC_ROOT, tile, year, mosaic_kind)
        rects.append(
            {
                "grid_id": grid_id,
                "tile": tile.upper(),
                "year": year,
                "summary": summary,
                "labels": labels[0] if labels else None,
                "mosaic": mosaic,
            }
        )
    return rects


def stretch_to_uint8(
    stack: np.ndarray,
    valid: np.ndarray,
    p_low: float = STRETCH_P_LOW,
    p_high: float = STRETCH_P_HIGH,
) -> np.ndarray:
    """Stretch percentil por banda → uint8 (H, W, 3). Nodata → 0."""
    out = np.zeros(stack.shape, dtype=np.uint8)
    for c in range(stack.shape[-1]):
        canal = stack[..., c]
        mascara = valid & np.isfinite(canal)
        if not np.any(mascara):
            continue
        lo, hi = np.nanpercentile(canal[mascara], [p_low, p_high])
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            hi = (float(lo) if np.isfinite(lo) else 0.0) + 1.0
            lo = float(lo) if np.isfinite(lo) else 0.0
        norm = np.zeros(canal.shape, dtype=np.float32)
        norm[mascara] = np.clip((canal[mascara] - lo) / (hi - lo), 0.0, 1.0)
        out[..., c] = (norm * 255.0).astype(np.uint8)
    return out


def to_uint16(stack: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Copia valores del mosaico a uint16 (rango 0–65535). Nodata → 0."""
    out = np.zeros(stack.shape, dtype=np.uint16)
    safe = valid & np.isfinite(stack).all(axis=-1)
    clipped = np.clip(stack, 0, 65535)
    out[safe] = clipped[safe].astype(np.uint16)
    return out


def leer_composicion(
    mosaic_path: Path,
    labels_path: Path,
    band_names: tuple[str, str, str],
    *,
    dtype: str = OUTPUT_DTYPE,
    band_idx: dict[str, int] | None = None,
) -> tuple[np.ndarray, dict]:
    """Lee bandas del mosaico alineadas a la ventana del labels.tif."""
    idx_map = band_idx or BAND_IDX
    indices = [idx_map[n] for n in band_names]
    with rasterio.open(labels_path) as ref, rasterio.open(mosaic_path) as src:
        if ref.crs != src.crs:
            raise ValueError(
                f"CRS distinto: labels={ref.crs} mosaic={src.crs} ({labels_path.name})"
            )
        win = from_bounds(*ref.bounds, transform=src.transform)
        win = win.round_offsets().round_lengths()
        data = np.stack(
            [src.read(i, window=win).astype(np.float32) for i in indices],
            axis=-1,
        )
        h, w = ref.height, ref.width
        if data.shape[0] != h or data.shape[1] != w:
            data = data[:h, :w, ...]
            if data.shape[0] < h or data.shape[1] < w:
                pad = np.full((h, w, data.shape[-1]), MOSAIC_NODATA, dtype=np.float32)
                pad[: data.shape[0], : data.shape[1]] = data
                data = pad
        valid = np.all(np.isfinite(data), axis=-1) & (data != MOSAIC_NODATA).all(axis=-1)

        if dtype == "float32":
            out = data.copy()
            out[~valid] = MOSAIC_NODATA
            nodata: float | int = MOSAIC_NODATA
        elif dtype == "uint16":
            out = to_uint16(data, valid)
            nodata = 0
        elif dtype == "uint8":
            out = stretch_to_uint8(data, valid)
            nodata = 0
        else:
            raise ValueError(f"dtype no soportado: {dtype!r} (use float32|uint16|uint8)")

        profile = {
            "driver": "GTiff",
            "dtype": dtype,
            "count": 3,
            "width": w,
            "height": h,
            "crs": ref.crs,
            "transform": ref.transform,
            "nodata": nodata,
            "compress": COMPRESS,
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256,
            "interleave": "pixel",
        }
    return out, profile


def escribir_con_piramides(
    path: Path,
    rgb: np.ndarray,
    profile: dict,
    band_names: tuple[str, str, str],
    composite: str,
    grid_id: str,
    year: int,
    *,
    mosaic_kind: str,
) -> None:
    """Escribe GeoTIFF RGB e inserta overviews internas."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    stretch_tag = (
        f"percentile_{STRETCH_P_LOW:g}_{STRETCH_P_HIGH:g}"
        if profile["dtype"] == "uint8"
        else "none_raw_mosaic_values"
    )
    factors = overview_factors(profile["width"], profile["height"])
    with rasterio.open(tmp, "w", **profile) as dst:
        for i in range(3):
            dst.write(rgb[..., i], i + 1)
            dst.set_band_description(i + 1, band_names[i])
        dst.update_tags(
            composite=composite,
            grid_id=grid_id,
            year=str(year),
            mosaic_kind=mosaic_kind,
            dtype_out=str(profile["dtype"]),
            stretch=stretch_tag,
            overview_factors=",".join(str(f) for f in factors),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        dst.build_overviews(factors, Resampling.average)
        dst.update_tags(ns="rio_overview", resampling="average")
    tmp.replace(path)


def procesar_rectangulo(
    rect: dict,
    out_root: Path,
    *,
    force: bool = False,
    dtype: str = OUTPUT_DTYPE,
    mosaic_kind: str = MOSAIC_KIND,
    band_idx: dict[str, int] | None = None,
) -> dict:
    """Genera las composiciones RGB definidas en COMPOSITES."""
    grid_id = rect["grid_id"]
    year = int(rect["year"])
    result = {
        "grid_id": grid_id,
        "tile": rect["tile"],
        "year": year,
        "dtype": dtype,
        "mosaic_kind": mosaic_kind,
        "status": "ok",
        "outputs": {},
    }
    if rect["labels"] is None:
        result["status"] = "error"
        result["error"] = "labels.tif ausente en segmentación"
        return result
    if rect["mosaic"] is None:
        result["status"] = "error"
        result["error"] = f"mosaico {mosaic_kind} ausente"
        return result

    for composite, bands in COMPOSITES.items():
        out_path = out_root / f"{grid_id}_{year}_{composite}.tif"
        result["outputs"][composite] = str(out_path)
        if out_path.exists() and not force:
            result.setdefault("skipped", []).append(composite)
            continue
        rgb, profile = leer_composicion(
            rect["mosaic"],
            rect["labels"],
            bands,
            dtype=dtype,
            band_idx=band_idx,
        )
        escribir_con_piramides(
            out_path,
            rgb,
            profile,
            bands,
            composite,
            grid_id,
            year,
            mosaic_kind=mosaic_kind,
        )
    if result.get("skipped") and len(result["skipped"]) == len(COMPOSITES):
        result["status"] = "skip"
    return result


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="GeoTIFF RGB / falso color por rectángulo (con pirámides)"
    )
    p.add_argument(
        "--year",
        type=int,
        default=YEAR,
        help="Año del mosaico / labeling / segmentación (default: 2015)",
    )
    p.add_argument(
        "--mosaic-kind",
        default=MOSAIC_KIND,
        help="Layout de mosaico: 184 | 11b (default: 184)",
    )
    p.add_argument("--labeling-root", type=Path, default=None)
    p.add_argument("--segmentation-root", type=Path, default=None)
    p.add_argument("--mosaic-root", type=Path, default=None)
    p.add_argument("--output-root", type=Path, default=None)
    p.add_argument("--grid-id", type=str, default=None, help="Procesar un solo grid_id")
    p.add_argument(
        "--dtype",
        choices=("float32", "uint16", "uint8"),
        default=OUTPUT_DTYPE,
        help="Tipo de salida (default float32 = valores crudos del mosaico)",
    )
    p.add_argument(
        "--overview-min-size",
        type=int,
        default=OVERVIEW_MIN_SIZE,
        help="Tamaño mínimo aprox. del overview más chico (default: 32)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Sobrescribir GeoTIFF existentes",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    year = args.year
    mosaic_kind = normalize_mosaic_kind(args.mosaic_kind)
    band_idx = band_idx_for_kind(mosaic_kind)

    global LABELING_ROOT, SEGMENTATION_ROOT, MOSAIC_ROOT, BAND_IDX, OVERVIEW_MIN_SIZE
    OVERVIEW_MIN_SIZE = int(args.overview_min_size)
    BAND_IDX = band_idx

    labeling_root = args.labeling_root or (
        MAPBIOMAS_ROOT / "prod" / "04_labeling_cim" / str(year)
    )
    segmentation_root = args.segmentation_root or (
        MAPBIOMAS_ROOT / "prod" / "03_segmentation_cim" / str(year)
    )
    mosaic_root = args.mosaic_root or mosaic_root_for_kind(mosaic_kind, year)
    output_root = args.output_root or (
        MAPBIOMAS_ROOT / "prod" / "webapp" / "rgb" / str(year)
    )

    LABELING_ROOT = labeling_root.resolve()
    SEGMENTATION_ROOT = segmentation_root.resolve()
    MOSAIC_ROOT = mosaic_root.resolve()
    output_root = output_root.resolve()

    if not LABELING_ROOT.is_dir():
        print(f"[ERROR] labeling-root no existe: {LABELING_ROOT}", file=sys.stderr)
        return 1
    if not SEGMENTATION_ROOT.is_dir():
        print(
            f"[ERROR] segmentation-root no existe: {SEGMENTATION_ROOT}",
            file=sys.stderr,
        )
        return 1
    if not MOSAIC_ROOT.is_dir():
        print(f"[ERROR] mosaic-root no existe: {MOSAIC_ROOT}", file=sys.stderr)
        return 1

    output_root.mkdir(parents=True, exist_ok=True)

    rects = descubrir_rectangulos(LABELING_ROOT, year, mosaic_kind=mosaic_kind)
    if args.grid_id:
        rects = [r for r in rects if r["grid_id"] == args.grid_id]
        if not rects:
            print(f"[ERROR] grid_id no encontrado: {args.grid_id}", file=sys.stderr)
            return 1

    sample_factors = overview_factors(529, 529)
    print(f"Año {year} · mosaic_kind={mosaic_kind} · {len(rects)} rectángulos → {output_root}")
    print(f"  dtype:        {args.dtype}")
    print(f"  overviews:    min_size={OVERVIEW_MIN_SIZE} (ej. 529px → {sample_factors})")
    print(f"  labeling:     {LABELING_ROOT}")
    print(f"  segmentation: {SEGMENTATION_ROOT}")
    print(f"  mosaic:       {MOSAIC_ROOT}")
    print(f"  band_idx:     {band_idx}")

    results = []
    n_ok = n_skip = n_err = 0
    for i, rect in enumerate(rects, 1):
        print(f"[{i}/{len(rects)}] {rect['grid_id']} …", flush=True)
        try:
            res = procesar_rectangulo(
                rect,
                output_root,
                force=args.force,
                dtype=args.dtype,
                mosaic_kind=mosaic_kind,
                band_idx=band_idx,
            )
        except Exception as exc:  # noqa: BLE001
            res = {
                "grid_id": rect["grid_id"],
                "tile": rect["tile"],
                "year": year,
                "status": "error",
                "error": str(exc),
            }
        results.append(res)
        st = res["status"]
        if st == "ok":
            n_ok += 1
            print("  ok")
        elif st == "skip":
            n_skip += 1
            print("  skip (ya existe; use --force)")
        else:
            n_err += 1
            print(f"  ERROR: {res.get('error')}")

    run_summary = {
        "year": year,
        "mosaic_kind": mosaic_kind,
        "dtype": args.dtype,
        "overview_min_size": OVERVIEW_MIN_SIZE,
        "n_total": len(rects),
        "n_ok": n_ok,
        "n_skip": n_skip,
        "n_error": n_err,
        "composites": {
            k: {"bands": list(v), "meaning": "R/G/B"} for k, v in COMPOSITES.items()
        },
        "stretch": (
            [STRETCH_P_LOW, STRETCH_P_HIGH] if args.dtype == "uint8" else None
        ),
        "band_indices": band_idx,
        "labeling_root": str(LABELING_ROOT),
        "segmentation_root": str(SEGMENTATION_ROOT),
        "mosaic_root": str(MOSAIC_ROOT),
        "output_root": str(output_root),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    summary_path = output_root / f"run_rgb_{year}_{mosaic_kind}.json"
    summary_path.write_text(json.dumps(run_summary, indent=2, ensure_ascii=False) + "\n")
    print(f"Listo: ok={n_ok} skip={n_skip} error={n_err} · resumen {summary_path}")
    return 0 if n_err == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
