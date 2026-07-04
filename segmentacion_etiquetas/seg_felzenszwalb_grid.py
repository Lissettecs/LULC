#!/usr/bin/env python3
"""
Segmentación Felzenszwalb sobre mosaico multibanda (prueba de calibración visual).

Ejecuta un grid de parámetros (scale × sigma) sobre un tile/año y exporta:
  - GeoTIFF de etiquetas por combinación
  - PNG de quick-look con polígonos coloreados sobre RGB + contorno
  - CSV resumen con estadísticas de tamaño de segmentos

Uso:
  python seg_felzenszwalb_grid.py --tile 18HYD
  python seg_felzenszwalb_grid.py --tile 19KDU --year 2010
  python seg_felzenszwalb_grid.py --list-tiles

Dependencias (cluster):
  python -m pip install rasterio scikit-image matplotlib

Alcance futuro (NO implementado):
  - Atribución de clase por voto mayoritario vs MapBiomas Colección 2
  - Índices espectrales (NDVI, MNDWI, NDSI, BSI) con z-score
  - Reemplazo por OTB Large-Scale Mean-Shift a escala nacional
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from skimage.color import label2rgb
from skimage.segmentation import felzenszwalb, mark_boundaries

# ── BLOQUE DE PARÁMETROS (editable) ──────────────────────────────────────────
_REPO = Path(__file__).resolve().parent
DEFAULT_TILE = "18HYD"
DEFAULT_YEAR = 2010
# Datos y salidas en mapbiomas_land (mosaicos no están en este repo)
_DATA_ROOT = Path("/home/lserey/mapbiomas_land/test/image_segmentation")
MOSAIC_DIR = _DATA_ROOT / "nir_swir1_red_normalized_mosaics"
OUTPUT_DIR = _DATA_ROOT / "seg_felzenszwalb"

SCALE_LIST = [25, 50, 100, 150, 200]
SIGMA_LIST = [0.1, 0.5, 0.8]
MIN_SIZE = 20

STANDARDIZE = False
NORMALIZE_01 = False  # mosaicos ya están en escala 0–1
NODATA = None

# Orden de bandas en {tile}_{year}_nir_swir1_red_0-1.tif: 0=nir, 1=swir1, 2=red
# Visualización RGB: red, swir1, nir
DISPLAY_BANDS = [2, 1, 0]

PIXEL_HA = 0.09  # 30 m → 900 m² → 0.09 ha/px

# Alias de compatibilidad para scripts que importan TILE/YEAR/MOSAIC_FILE
TILE = DEFAULT_TILE
YEAR = DEFAULT_YEAR
# ─────────────────────────────────────────────────────────────────────────────


MOSAIC_PATTERN = re.compile(r"^(?P<tile>[A-Z0-9]+)_(?P<year>\d+)_nir_swir1_red_0-1\.tif$")


def nombre_mosaico(tile: str, year: int) -> str:
    """Nombre del GeoTIFF nir/swir1/red normalizado (0–1)."""
    return f"{tile}_{year}_nir_swir1_red_0-1.tif"


MOSAIC_FILE = nombre_mosaico(DEFAULT_TILE, DEFAULT_YEAR)


def listar_tiles(mosaic_dir: Path, year: int | None = None) -> list[str]:
    """Tiles con GeoTIFF nir/swir1/red en el directorio de mosaicos."""
    if not mosaic_dir.is_dir():
        return []
    tiles: list[str] = []
    for ruta in sorted(mosaic_dir.glob("*.tif")):
        match = MOSAIC_PATTERN.match(ruta.name)
        if not match:
            continue
        if year is not None and int(match.group("year")) != year:
            continue
        tiles.append(match.group("tile"))
    return sorted(set(tiles))


def localizar_mosaico_tile(mosaic_dir: Path, tile: str, year: int) -> Path:
    """Localiza el GeoTIFF nir/swir1/red del tile/año."""
    ruta = mosaic_dir / nombre_mosaico(tile, year)
    if ruta.is_file():
        return ruta
    print(f"[ERROR] No se encontró '{ruta.name}' en {mosaic_dir}")
    sys.exit(1)


def localizar_mosaico(mosaic_dir: Path, nombre_archivo: str) -> Path:
    """Busca el GeoTIFF por nombre exacto dentro de MOSAIC_DIR (recursivo)."""
    coincidencias = sorted(mosaic_dir.rglob(nombre_archivo))
    if len(coincidencias) == 0:
        print(f"[ERROR] No se encontró '{nombre_archivo}' en {mosaic_dir}")
        sys.exit(1)
    if len(coincidencias) > 1:
        print(f"[ERROR] Se encontraron {len(coincidencias)} archivos con ese nombre; se esperaba 1:")
        for ruta in coincidencias:
            print(f"  - {ruta}")
        sys.exit(1)
    return coincidencias[0]


def resolver_nodata(src: rasterio.io.DatasetReader, nodata_param: float | None) -> float | None:
    """Determina el valor nodata efectivo."""
    if nodata_param is not None:
        return float(nodata_param)
    if src.nodata is not None:
        return float(src.nodata)
    return None


def construir_mascara_nodata(
    datos: np.ndarray,
    nodata_valor: float | None,
) -> np.ndarray:
    """
    Máscara booleana True = píxel válido.

    Si no hay nodata explícito, trata 0 simultáneo en todas las bandas como nodata.
    """
    if nodata_valor is not None:
        return np.all(datos != nodata_valor, axis=-1)

    finitos = np.all(np.isfinite(datos), axis=-1)
    return finitos & ~np.all(datos == 0, axis=-1)


def rellenar_nodata_mediana(datos: np.ndarray, validos: np.ndarray) -> np.ndarray:
    """Rellena nodata con la mediana por banda (solo para ejecutar Felzenszwalb)."""
    salida = datos.copy()
    for canal in range(datos.shape[-1]):
        banda = salida[..., canal]
        if np.any(validos):
            mediana = float(np.median(banda[validos]))
        else:
            mediana = 0.0
        banda[~validos] = mediana
        salida[..., canal] = banda
    return salida


def estandarizar_zscore(datos: np.ndarray, validos: np.ndarray) -> np.ndarray:
    """Z-score por banda usando solo píxeles válidos."""
    salida = datos.copy()
    for canal in range(datos.shape[-1]):
        banda = datos[..., canal]
        valores = banda[validos]
        media = float(np.mean(valores))
        std = float(np.std(valores))
        if std == 0:
            std = 1.0
        salida[..., canal] = (banda - media) / std
    return salida.astype(np.float32)


def diagnosticar_mosaico(
    src: rasterio.io.DatasetReader,
    datos: np.ndarray,
    validos: np.ndarray,
    nodata_valor: float | None,
) -> None:
    """Imprime diagnóstico espectral antes de segmentar."""
    n_bandas = src.count
    h, w = src.height, src.width

    print("\n=== DIAGNÓSTICO DEL MOSAICO ===")
    print(f"Archivo      : {src.name}")
    print(f"Bandas       : {n_bandas}")
    print(f"Dtype        : {src.dtypes[0]}")
    print(f"CRS          : {src.crs}")
    print(f"Transform    : {src.transform}")
    print(f"Shape (H,W)  : ({h}, {w})")
    print(f"NoData config: parámetro={NODATA!r}, metadata={src.nodata!r}, efectivo={nodata_valor!r}")
    if nodata_valor is None:
        print("Regla nodata : 0 en TODAS las bandas simultáneamente")
    print(f"Píxeles válidos: {validos.sum():,} / {validos.size:,} ({100 * validos.mean():.2f}%)")

    descripciones = src.descriptions or [f"banda_{i + 1}" for i in range(n_bandas)]
    print("\nEstadísticas por banda (solo píxeles válidos):")
    print(f"{'Banda':>5}  {'Nombre':<28}  {'Min':>10}  {'Max':>10}  {'Media':>10}  {'%NoData':>8}")
    print("-" * 80)
    for i in range(n_bandas):
        banda = datos[..., i]
        pct_nodata = 100.0 * (~validos).mean()
        if np.any(validos):
            vals = banda[validos]
            vmin, vmax, vmean = float(vals.min()), float(vals.max()), float(vals.mean())
        else:
            vmin = vmax = vmean = float("nan")
        nombre = descripciones[i] or f"banda_{i + 1}"
        print(f"{i + 1:>5}  {nombre:<28}  {vmin:10.3f}  {vmax:10.3f}  {vmean:10.3f}  {pct_nodata:7.2f}")


def estadisticas_segmentos(labels: np.ndarray, validos: np.ndarray) -> dict:
    """Calcula métricas de tamaño excluyendo label 0 (nodata)."""
    labels_validos = labels.copy()
    labels_validos[~validos] = 0

    ids, counts = np.unique(labels_validos, return_counts=True)
    mask = ids != 0
    ids = ids[mask]
    counts = counts[mask]

    if counts.size == 0:
        return {
            "n_segmentos": 0,
            "tam_medio_px": 0.0,
            "tam_mediano_px": 0.0,
            "tam_min_px": 0,
            "tam_max_px": 0,
            "tam_medio_ha": 0.0,
        }

    return {
        "n_segmentos": int(counts.size),
        "tam_medio_px": float(np.mean(counts)),
        "tam_mediano_px": float(np.median(counts)),
        "tam_min_px": int(counts.min()),
        "tam_max_px": int(counts.max()),
        "tam_medio_ha": float(np.mean(counts) * PIXEL_HA),
    }


def componer_rgb(
    datos: np.ndarray,
    indices: list[int],
    validos: np.ndarray,
    p_low: float = 2.0,
    p_high: float = 98.0,
) -> np.ndarray:
    """Composición falso color con stretch por percentil 2–98."""
    n_canales = datos.shape[-1]
    for idx in indices:
        if idx < 0 or idx >= n_canales:
            raise ValueError(
                f"DISPLAY_BANDS contiene índice {idx} fuera de rango [0, {n_canales - 1}]"
            )

    rgb = np.stack([datos[..., i] for i in indices], axis=-1).astype(np.float32)
    rgb_out = np.zeros_like(rgb)

    for c in range(rgb.shape[-1]):
        canal = rgb[..., c]
        mascara = validos & np.isfinite(canal)
        if np.any(mascara):
            lo, hi = np.nanpercentile(canal[mascara], [p_low, p_high])
        elif np.any(np.isfinite(canal)):
            finitos = canal[np.isfinite(canal)]
            lo, hi = float(finitos.min()), float(finitos.max())
        else:
            lo, hi = 0.0, 1.0
        if hi <= lo:
            hi = lo + 1.0
        canal_norm = np.clip((canal - lo) / (hi - lo), 0.0, 1.0)
        canal_norm[~np.isfinite(canal)] = 0.0
        canal_norm[~validos] = 0.0
        rgb_out[..., c] = canal_norm

    return rgb_out


def verificar_sobrescritura(rutas: list[Path]) -> None:
    """Aborta si algún archivo de salida ya existe."""
    existentes = [r for r in rutas if r.exists()]
    if existentes:
        print("[ERROR] Los siguientes archivos ya existen (no se sobrescriben):")
        for ruta in existentes:
            print(f"  - {ruta}")
        print("Elimínalos o cambia OUTPUT_DIR antes de volver a ejecutar.")
        sys.exit(1)


def guardar_geotiff_labels(
    labels: np.ndarray,
    perfil: dict,
    ruta: Path,
) -> None:
    """Exporta etiquetas como GeoTIFF INT32 con nodata=0."""
    meta = perfil.copy()
    meta.update(
        {
            "count": 1,
            "dtype": "int32",
            "nodata": 0,
            "compress": "lzw",
        }
    )
    with rasterio.open(ruta, "w", **meta) as dst:
        dst.write(labels.astype(np.int32), 1)


def reducir_para_quicklook(
    rgb: np.ndarray,
    labels: np.ndarray,
    validos: np.ndarray,
    max_lado: int = 1200,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Reduce resolución para el PNG de calibración.

    Sobre ~3700 px, un borde de 1–2 px se convierte en puntos sueltos al guardar
    la figura; bajar resolución mantiene polígonos visibles.
    """
    h, w = labels.shape
    factor = max(1, int(np.ceil(max(h, w) / max_lado)))
    if factor == 1:
        return rgb, labels, validos

    rgb_out = rgb[::factor, ::factor]
    labels_out = labels[::factor, ::factor]
    validos_out = validos[::factor, ::factor]
    return rgb_out, labels_out, validos_out


def componer_quicklook(
    rgb: np.ndarray,
    labels: np.ndarray,
    validos: np.ndarray,
    alpha_etiquetas: float = 0.42,
) -> np.ndarray:
    """
    Quick-look con polígonos coloreados + contorno.

    El GeoTIFF muestra regiones por ID; el PNG anterior solo pintaba bordes
    píxel a píxel y parecía ruido disperso.
    """
    labels_vis = labels.copy()
    labels_vis[~validos] = 0

    rgb_base = rgb.copy()
    rgb_base[~validos] = 0.0

    coloreada = label2rgb(
        labels_vis,
        image=rgb_base,
        bg_label=0,
        kind="overlay",
        alpha=alpha_etiquetas,
    ).astype(np.float32)

    return mark_boundaries(
        coloreada,
        labels_vis,
        color=(1.0, 1.0, 1.0),
        mode="inner",
    )


def guardar_rgba_png(ruta: Path, rgba: np.ndarray) -> None:
    """Guarda array float RGBA (0–1) como PNG."""
    from PIL import Image

    img = (np.clip(rgba, 0.0, 1.0) * 255).astype(np.uint8)
    Image.fromarray(img, mode="RGBA").save(ruta)


def overlay_rgba_desde_labels(labels: np.ndarray, validos: np.ndarray) -> np.ndarray:
    """Capa RGBA con polígonos coloreados por ID de segmento."""
    labels_vis = labels.copy()
    labels_vis[~validos] = 0
    max_id = int(labels_vis.max())
    rng = np.random.default_rng(42)
    palette = rng.random((max_id + 1, 3), dtype=np.float32)
    palette[0] = 0.0
    rgb = palette[labels_vis]
    alpha = np.where((labels_vis > 0) & validos, 0.62, 0.0).astype(np.float32)
    return np.dstack([rgb, alpha])


def contornos_rgba_desde_labels(
    labels: np.ndarray,
    validos: np.ndarray,
    *,
    labels_ref: np.ndarray | None = None,
    validos_ref: np.ndarray | None = None,
) -> np.ndarray:
    """Capa RGBA con contornos blancos de 1 px sobre fondo transparente."""
    from skimage.segmentation import find_boundaries

    ref_labels = labels_ref if labels_ref is not None else labels
    ref_validos = validos_ref if validos_ref is not None else validos
    labels_vis = ref_labels.copy()
    labels_vis[~ref_validos] = 0
    bordes_ref = find_boundaries(labels_vis, mode="inner", connectivity=1)

    if labels_ref is not None and bordes_ref.shape != labels.shape:
        from skimage.transform import resize

        bordes = resize(
            bordes_ref.astype(np.float32),
            labels.shape,
            order=0,
            preserve_range=True,
            anti_aliasing=False,
        ).astype(bool)
    else:
        bordes = bordes_ref

    rgba = np.zeros((*labels.shape, 4), dtype=np.float32)
    rgba[bordes] = (1.0, 1.0, 1.0, 1.0)
    return rgba


def guardar_quicklook(
    rgb: np.ndarray,
    labels: np.ndarray,
    validos: np.ndarray,
    ruta: Path,
    titulo: str,
) -> None:
    """PNG con polígonos coloreados y contorno blanco (legible a escala de pantalla)."""
    rgb_q, labels_q, validos_q = reducir_para_quicklook(rgb, labels, validos)
    marcada = componer_quicklook(rgb_q, labels_q, validos_q)

    alto, ancho = marcada.shape[:2]
    dpi = 150
    fig, ax = plt.subplots(
        figsize=(ancho / dpi, alto / dpi),
        dpi=dpi,
    )
    ax.imshow(marcada, interpolation="nearest")
    ax.set_title(titulo, fontsize=11)
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=0.96, bottom=0)
    fig.savefig(ruta, dpi=dpi, pad_inches=0)
    plt.close(fig)


def imprimir_tabla(filas: list[dict]) -> None:
    """Imprime la tabla resumen en consola."""
    if not filas:
        print("\n[INFO] No hay filas en la tabla resumen.")
        return

    columnas = [
        "scale",
        "sigma",
        "min_size",
        "n_segmentos",
        "tam_medio_px",
        "tam_mediano_px",
        "tam_min_px",
        "tam_max_px",
        "tam_medio_ha",
    ]
    print("\n=== TABLA RESUMEN ===")
    print("  ".join(f"{c:>14}" for c in columnas))
    print("-" * (15 * len(columnas)))
    for fila in filas:
        print(
            "  ".join(
                f"{fila[c]:>14.3f}" if isinstance(fila[c], float) else f"{fila[c]:>14}"
                for c in columnas
            )
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Segmentación Felzenszwalb (grid scale × sigma) sobre mosaico multibanda.",
    )
    parser.add_argument(
        "--tile",
        default=DEFAULT_TILE,
        help=f"Tile MGRS a procesar (default: {DEFAULT_TILE})",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=DEFAULT_YEAR,
        help=f"Año del mosaico (default: {DEFAULT_YEAR})",
    )
    parser.add_argument(
        "--mosaic-dir",
        type=Path,
        default=MOSAIC_DIR,
        help="Directorio con mosaicos {tile}_{year}_nir_swir1_red_0-1.tif",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directorio de salida para TIF, PNG y CSV",
    )
    parser.add_argument(
        "--list-tiles",
        action="store_true",
        help="Lista tiles disponibles en --mosaic-dir y termina",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mosaic_dir = args.mosaic_dir.resolve()
    output_dir = args.output_dir.resolve()
    tile = args.tile.upper()
    year = args.year

    if args.list_tiles:
        tiles = listar_tiles(mosaic_dir, year)
        if not tiles:
            print(f"[INFO] No hay tiles con GeoTIFF en {mosaic_dir}")
        else:
            print(f"[INFO] Tiles en {mosaic_dir}:")
            for nombre in tiles:
                print(f"  - {nombre}  →  {nombre_mosaico(nombre, year)}")
        return

    if not mosaic_dir.is_dir():
        print(f"[ERROR] MOSAIC_DIR no existe: {mosaic_dir}")
        sys.exit(1)

    tiles_disponibles = listar_tiles(mosaic_dir, year)
    if tile not in tiles_disponibles:
        print(f"[ERROR] Tile '{tile}' no encontrado en {mosaic_dir}")
        if tiles_disponibles:
            print(f"[INFO] Tiles disponibles: {', '.join(tiles_disponibles)}")
        sys.exit(1)

    if STANDARDIZE and NORMALIZE_01:
        print(
            "[ERROR] STANDARDIZE y NORMALIZE_01 son excluyentes. "
            "NORMALIZE_01 divide por 10000 (peso relativo entre bandas); "
            "STANDARDIZE aplica z-score (iguala varianza). Elija solo uno."
        )
        sys.exit(1)

    mosaic_file = nombre_mosaico(tile, year)
    ruta_mosaico = localizar_mosaico_tile(mosaic_dir, tile, year)
    print(f"[OK] Tile={tile} · año={year} · mosaico={mosaic_file}")
    print(f"[OK] Mosaico localizado: {ruta_mosaico}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"[ERROR] Sin permiso para crear OUTPUT_DIR: {output_dir}")
        sys.exit(1)

    if output_dir.exists() and not output_dir.is_dir():
        print(f"[ERROR] OUTPUT_DIR existe pero no es un directorio: {output_dir}")
        sys.exit(1)

    if not output_dir.exists():
        print(f"[ERROR] No se pudo crear OUTPUT_DIR: {output_dir}")
        sys.exit(1)

    if not output_dir.stat().st_mode & 0o200:
        print(f"[ERROR] OUTPUT_DIR no es escribible: {output_dir}")
        sys.exit(1)

    rutas_previstas: list[Path] = []
    for scale in SCALE_LIST:
        for sigma in SIGMA_LIST:
            base = f"seg_{tile}_{year}_s{scale}_sig{sigma}"
            rutas_previstas.append(output_dir / f"{base}.tif")
            rutas_previstas.append(output_dir / f"{base}.png")
    rutas_previstas.append(output_dir / f"resumen_{tile}_{year}.csv")
    verificar_sobrescritura(rutas_previstas)

    with rasterio.open(ruta_mosaico) as src:
        perfil = src.profile
        n_bandas = src.count
        datos = np.stack([src.read(i + 1) for i in range(n_bandas)], axis=-1).astype(np.float32)
        nodata_valor = resolver_nodata(src, NODATA)
        validos = construir_mascara_nodata(datos, nodata_valor)

        diagnosticar_mosaico(src, datos, validos, nodata_valor)

        img = rellenar_nodata_mediana(datos, validos)

        if STANDARDIZE:
            print(
                "\n[ADVERTENCIA] STANDARDIZE=True: se aplica z-score por banda. "
                "Recalibrar SCALE_LIST a valores mucho menores (p. ej. 0.1–10)."
            )
            img = estandarizar_zscore(img, validos)
        elif NORMALIZE_01:
            print("\n[INFO] NORMALIZE_01=True: img = img / 10000.0 (reflectancia aprox. 0–1).")
            img = (img / 10000.0).astype(np.float32)
        else:
            print("\n[INFO] Mosaico ya normalizado 0–1; sin división por 10000.")

        print(f"\n[VERIFICACIÓN] img.shape = {img.shape}  (esperado: H, W, C={n_bandas})")
        if img.shape[-1] != n_bandas:
            print("[ERROR] La última dimensión no coincide con el número de bandas.")
            sys.exit(1)
        print("[OK] Felzenszwalb usará distancia euclidiana en todas las bandas (channel_axis=-1).")

        rgb_base = componer_rgb(datos, DISPLAY_BANDS, validos)
        filas_resumen: list[dict] = []

        total = len(SCALE_LIST) * len(SIGMA_LIST)
        paso = 0
        print(f"\n=== SEGMENTACIÓN ({total} combinaciones) ===")

        for scale in SCALE_LIST:
            for sigma in SIGMA_LIST:
                paso += 1
                print(f"\n[{paso}/{total}] scale={scale}, sigma={sigma}, min_size={MIN_SIZE} ...")

                labels = felzenszwalb(
                    img,
                    scale=scale,
                    sigma=sigma,
                    min_size=MIN_SIZE,
                    channel_axis=-1,
                )
                labels = labels.astype(np.int32)
                labels[~validos] = 0

                stats = estadisticas_segmentos(labels, validos)
                print(
                    f"  → segmentos={stats['n_segmentos']:,}, "
                    f"tamaño medio={stats['tam_medio_px']:.1f} px "
                    f"({stats['tam_medio_ha']:.4f} ha)"
                )

                base = f"seg_{tile}_{year}_s{scale}_sig{sigma}"
                ruta_tif = output_dir / f"{base}.tif"
                ruta_png = output_dir / f"{base}.png"
                titulo = f"Felzenszwalb — {tile} {year} — s={scale}, σ={sigma}"

                guardar_geotiff_labels(labels, perfil, ruta_tif)
                guardar_quicklook(rgb_base, labels, validos, ruta_png, titulo)
                print(f"  → guardado: {ruta_tif.name}, {ruta_png.name}")

                fila = {
                    "scale": scale,
                    "sigma": sigma,
                    "min_size": MIN_SIZE,
                    **stats,
                }
                filas_resumen.append(fila)

    ruta_csv = output_dir / f"resumen_{tile}_{year}.csv"
    columnas = [
        "scale",
        "sigma",
        "min_size",
        "n_segmentos",
        "tam_medio_px",
        "tam_mediano_px",
        "tam_min_px",
        "tam_max_px",
        "tam_medio_ha",
    ]
    with ruta_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columnas)
        writer.writeheader()
        writer.writerows(filas_resumen)

    imprimir_tabla(filas_resumen)
    print(f"\n[OK] CSV resumen: {ruta_csv}")
    print(f"[OK] Salidas en: {output_dir}")


if __name__ == "__main__":
    main()
