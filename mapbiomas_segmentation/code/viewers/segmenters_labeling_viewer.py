#!/usr/bin/env python3
"""
Unified segmenters + Col2 labeling viewer.

Extends segmenters_viewer.py with:
  - All segmenter × parameter combinations (Felzenszwalb, RF_N, SLIC, Pipeline B, ablación, RF_N podado)
  - Col2 2015 label overlays per combination (ok / mixed / no_data)
  - Landcover reference layer and class legend

Prerequisites:
  python segmentation_labels/export_label_overlays.py --tile 18HYD --resume

Usage:
  cd labeling/image_segmentation
  python segmenters_labeling_viewer.py --skip-layers --skip-export
  python segmenters_labeling_viewer.py --html /path/segmenters_labeling_viewer.html

Serve:
  cd /home/lserey/mapbiomas_land/test/image_segmentation
  python3 -m http.server 8765 --bind 0.0.0.0
  → http://localhost:8765/segmenters_labeling_viewer.html
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from html import escape
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_SCRIPT_DIR / "segmentation_labels") not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR / "segmentation_labels"))

import segmenters_viewer as sv  # noqa: E402
from col2_palette import CLASES_VALIDAS, COL2_NAMES, COL2_RGB  # noqa: E402

_DATA_ROOT = Path("/home/lserey/mapbiomas_land/test/image_segmentation")
_RFN_OUTPUT = _DATA_ROOT / "seg_felzenszwalb_rfn"
_ABL_OUTPUT = _DATA_ROOT / "seg_felzenszwalb_ablacion"
_DEFAULT_HTML = _DATA_ROOT / "segmenters_labeling_viewer.html"

EXTENDED_SEGMENTADORES: dict[str, dict] = {
    **sv.SEGMENTADORES,
    "felzenszwalb_rfn_podado": {
        "label": "Felzenszwalb RF_N podado",
        "output_dir": _RFN_OUTPUT,
        "color": "#9333ea",
        "rfn_podado": True,
    },
    "ablacion": {
        "label": "Ablación medianas",
        "output_dir": _ABL_OUTPUT,
        "color": "#b45309",
        "ablacion": True,
    },
}


def buscar_resumen_rfn(output_dir: Path) -> Path | None:
    candidatos = sorted(output_dir.glob("resumen_rfn_*.csv"))
    return candidatos[0] if candidatos else None


def cargar_resumen_rfn(ruta_csv: Path) -> tuple[list[dict], str, str]:
    filas: list[dict] = []
    tile = ""
    year = ""
    match = re.match(r"^resumen_rfn_(?P<tile>[^_]+)_(?P<year>\d+)\.csv$", ruta_csv.name)
    if match:
        tile = match.group("tile")
        year = match.group("year")
    with ruta_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            filas.append(
                {
                    "scale": int(float(row["scale"])),
                    "sigma": float(row["sigma"]),
                    "min_size": int(float(row["min_size"])),
                    "n_segmentos": int(float(row["n_segmentos"])),
                    "tam_medio_px": float(row["tam_medio_px"]),
                    "tam_mediano_px": float(row["tam_mediano_px"]),
                    "tam_min_px": int(float(row["tam_min_px"])),
                    "tam_max_px": int(float(row["tam_max_px"])),
                    "tam_medio_ha": float(row["tam_medio_ha"]),
                }
            )
    return filas, tile, year


def buscar_resumen_ablacion(output_dir: Path) -> Path | None:
    candidatos = sorted(output_dir.glob("resumen_ablacion_*.csv"))
    return candidatos[0] if candidatos else None


def corrida_a_variant(corrida: str) -> str:
    if corrida == "medianas":
        return "medianas"
    return "medianas_mas_" + corrida.split("+", 1)[1]


def cargar_resumen_ablacion(ruta_csv: Path) -> tuple[list[dict], str, str]:
    filas: list[dict] = []
    tile = ""
    year = ""
    match = re.match(r"^resumen_ablacion_(?P<tile>[^_]+)_(?P<year>\d+)\.csv$", ruta_csv.name)
    if match:
        tile = match.group("tile")
        year = match.group("year")
    with ruta_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            corrida = row["corrida"].strip()
            variant = corrida_a_variant(corrida)
            filas.append(
                {
                    "variant": variant,
                    "corrida": corrida,
                    "clave": f"abl_{variant}",
                    "scale": 200,
                    "sigma": 0.1,
                    "min_size": 20,
                    "n_segmentos": int(float(row["n_segmentos"])),
                    "tam_medio_px": float(row["tam_medio_px"]),
                    "tam_mediano_px": float(row["tam_mediano_px"]),
                    "tam_min_px": int(float(row["tam_min_px"])),
                    "tam_max_px": int(float(row["tam_max_px"])),
                    "tam_medio_ha": float(row["tam_medio_ha"]),
                    "n_bandas": int(float(row["n_bandas"])),
                    "ratio_vs_3bandas": float(row["ratio_vs_3bandas"]),
                }
            )
    filas.sort(key=lambda r: r["n_segmentos"])
    return filas, tile, year


def descubrir_combinaciones_ablacion(
    output_dir: Path,
    html_dir: Path,
    tile: str,
    year: str,
) -> list[dict]:
    capas_dir = output_dir / sv.CAPAS_SUBDIR
    entradas: list[dict] = []
    for ruta_tif in sorted(output_dir.glob(f"seg_abl_{tile}_{year}_*.tif")):
        match = re.match(rf"^seg_abl_{tile}_{year}_(?P<variant>.+)\.tif$", ruta_tif.name)
        if not match:
            continue
        variant = match.group("variant")
        clave = f"abl_{variant}"
        base = ruta_tif.stem
        ruta_png = ruta_tif.with_suffix(".png")
        entradas.append(
            {
                "tile": tile,
                "year": year,
                "scale": 200,
                "sigma": 0.1,
                "variant": variant,
                "clave": clave,
                "tif": sv.viz.ruta_publica(html_dir, ruta_tif),
                "png": sv.viz.ruta_publica(html_dir, ruta_png) if ruta_png.is_file() else "",
                "overlay_tiers": sv.viz.descubrir_tiers_capa(html_dir, capas_dir, base, "overlay"),
                "boundaries_tiers": sv.viz.descubrir_tiers_capa(html_dir, capas_dir, base, "boundaries"),
            }
        )
    return entradas


def descubrir_combinaciones_rfn_podado(
    output_dir: Path,
    html_dir: Path,
) -> list[dict]:
    capas_dir = output_dir / sv.CAPAS_SUBDIR
    entradas: list[dict] = []
    for ruta_tif in sorted(output_dir.glob("seg_rfn_*.tif")):
        match = re.match(
            r"^seg_rfn_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+)_sig(?P<sigma>[\d.]+)\.tif$",
            ruta_tif.name,
        )
        if not match:
            continue
        scale = int(match.group("scale"))
        sigma = float(match.group("sigma"))
        clave = sv.viz.clave_desde_params(scale, sigma)
        base = ruta_tif.stem
        ruta_png = ruta_tif.with_suffix(".png")
        entradas.append(
            {
                "tile": match.group("tile"),
                "year": match.group("year"),
                "scale": scale,
                "sigma": sigma,
                "clave": clave,
                "tif": sv.viz.ruta_publica(html_dir, ruta_tif),
                "png": sv.viz.ruta_publica(html_dir, ruta_png) if ruta_png.is_file() else "",
                "overlay_tiers": sv.viz.descubrir_tiers_capa(html_dir, capas_dir, base, "overlay"),
                "boundaries_tiers": sv.viz.descubrir_tiers_capa(html_dir, capas_dir, base, "boundaries"),
            }
        )
    return entradas


def cargar_segmentador_extendido(
    seg_id: str,
    config: dict,
    html_dir: Path,
    mosaic_dir: Path,
    skip_layers: bool,
    mosaic_tiers_ref: dict[str, str] | None,
) -> tuple[dict, dict[str, str] | None]:
    if config.get("ablacion"):
        return _cargar_ablacion(seg_id, config, html_dir, mosaic_dir, skip_layers, mosaic_tiers_ref)
    if config.get("rfn_podado"):
        return _cargar_rfn_podado(seg_id, config, html_dir, mosaic_dir, skip_layers, mosaic_tiers_ref)
    return sv.cargar_segmentador(seg_id, config, html_dir, mosaic_dir, skip_layers, mosaic_tiers_ref)


def _cargar_rfn_podado(
    seg_id: str,
    config: dict,
    html_dir: Path,
    mosaic_dir: Path,
    skip_layers: bool,
    mosaic_tiers_ref: dict[str, str] | None,
) -> tuple[dict, dict[str, str] | None]:
    output_dir = Path(config["output_dir"]).resolve()
    ruta_csv = buscar_resumen_rfn(output_dir)
    if ruta_csv is None:
        print(f"[ERROR] No resumen_rfn_*.csv en {output_dir}")
        sys.exit(1)
    filas, tile, year = cargar_resumen_rfn(ruta_csv)
    capas_dir = output_dir / sv.CAPAS_SUBDIR
    mosaic_tiers: dict[str, str] = {}
    if not skip_layers:
        rel_tiers = sv.viz.exportar_capas(output_dir, mosaic_dir, tile, year)
        if rel_tiers:
            mosaic_tiers = {k: sv.viz.ruta_publica(html_dir, output_dir / v) for k, v in rel_tiers.items()}
    elif mosaic_tiers_ref:
        mosaic_tiers = dict(mosaic_tiers_ref)
    else:
        mosaic_tiers = sv.viz.descubrir_mosaic_tiers(html_dir, capas_dir, tile, year)

    combinaciones = descubrir_combinaciones_rfn_podado(output_dir, html_dir)
    datos = {
        "label": config["label"],
        "color": config["color"],
        "output_dir": str(output_dir),
        "filas": filas,
        "combinaciones": combinaciones,
        "capas_por_clave": {c["clave"]: c for c in combinaciones},
        "stats": sv.stats_desde_filas(filas),
        "incluir_rag": False,
        "rag_percentiles": [],
        "tile": tile,
        "year": year,
        "mosaic_tiers": mosaic_tiers,
    }
    return datos, mosaic_tiers or None


def _cargar_ablacion(
    seg_id: str,
    config: dict,
    html_dir: Path,
    mosaic_dir: Path,
    skip_layers: bool,
    mosaic_tiers_ref: dict[str, str] | None,
) -> tuple[dict, dict[str, str] | None]:
    output_dir = Path(config["output_dir"]).resolve()
    ruta_csv = buscar_resumen_ablacion(output_dir)
    if ruta_csv is None:
        print(f"[ERROR] No resumen_ablacion_*.csv en {output_dir}")
        sys.exit(1)
    filas, tile, year = cargar_resumen_ablacion(ruta_csv)
    capas_dir = output_dir / sv.CAPAS_SUBDIR
    mosaic_tiers: dict[str, str] = {}
    if not skip_layers:
        rel_tiers = sv.viz.exportar_capas(output_dir, mosaic_dir, tile, year)
        if rel_tiers:
            mosaic_tiers = {k: sv.viz.ruta_publica(html_dir, output_dir / v) for k, v in rel_tiers.items()}
    elif mosaic_tiers_ref:
        mosaic_tiers = dict(mosaic_tiers_ref)
    else:
        mosaic_tiers = sv.viz.descubrir_mosaic_tiers(html_dir, capas_dir, tile, year)

    combinaciones = descubrir_combinaciones_ablacion(output_dir, html_dir, tile, year)
    for fila in filas:
        variant = fila["variant"]
        stem = f"seg_abl_{tile}_{year}_{variant}"
        match = next((c for c in combinaciones if c.get("variant") == variant), None)
        if match:
            fila["clave"] = match["clave"]
        else:
            fila["clave"] = f"abl_{variant}"

    datos = {
        "label": config["label"],
        "color": config["color"],
        "output_dir": str(output_dir),
        "filas": filas,
        "combinaciones": combinaciones,
        "capas_por_clave": {c["clave"]: c for c in combinaciones},
        "stats": sv.stats_desde_filas(filas),
        "incluir_rag": False,
        "rag_percentiles": [],
        "ablacion": True,
        "tile": tile,
        "year": year,
        "mosaic_tiers": mosaic_tiers,
    }
    return datos, mosaic_tiers or None


def labeling_root(tile: str, seg_year: str, lc_year: int) -> Path:
    return _DATA_ROOT / "labeling_overlays" / f"tile_{tile}_{seg_year}_lc{lc_year}"


# Extra label overlay dirs merged into a segmenter dashboard (e.g. SLIC raw + RAG p).
EXTRA_LABEL_DIRS: dict[str, list[str]] = {
    "slic": ["slic_rag"],
}


def _label_subdir_for_stem(seg_id: str, stem: str, label_root: Path) -> str:
    """Return overlay subdir that contains assignment JSON for stem."""
    for sub in [seg_id, *EXTRA_LABEL_DIRS.get(seg_id, [])]:
        if (label_root / sub / f"{stem}_assignment.json").is_file():
            return sub
    return seg_id


def merge_labeling(
    segmentadores: dict[str, dict],
    html_dir: Path,
    label_root: Path,
    lc_year: int,
) -> dict[str, str]:
    """Attach label overlay tiers and ok/mixed stats to each combination."""
    landcover_tiers: dict[str, str] = {}
    lc_json = label_root / "landcover_tiers.json"
    if lc_json.is_file():
        payload = json.loads(lc_json.read_text(encoding="utf-8"))
        landcover_tiers = {
            k: sv.viz.ruta_publica(html_dir, label_root / v) for k, v in payload.get("tiers", {}).items()
        }

    for seg_id, datos in segmentadores.items():
        label_dirs = [seg_id, *EXTRA_LABEL_DIRS.get(seg_id, [])]
        summaries: dict[str, Path] = {}
        for sub in label_dirs:
            seg_label_dir = label_root / sub
            if not seg_label_dir.is_dir():
                continue
            for p in seg_label_dir.glob("*_assignment.json"):
                summaries[p.stem.replace("_assignment", "")] = p
        if not summaries:
            continue
        for clave, capa in datos["capas_por_clave"].items():
            stem = _stem_from_capa(capa)
            summary_path = summaries.get(stem)
            if not summary_path:
                continue
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            label_tiers = {
                tier: sv.viz.ruta_publica(
                    html_dir, label_root / _label_subdir_for_stem(seg_id, stem, label_root) / rel
                )
                for tier, rel in summary.get("label_tiers", {}).items()
            }
            purity_tiers = {
                tier: sv.viz.ruta_publica(
                    html_dir, label_root / _label_subdir_for_stem(seg_id, stem, label_root) / rel
                )
                for tier, rel in summary.get("purity_tiers", {}).items()
            }
            capa["label_tiers"] = label_tiers
            capa["purity_tiers"] = purity_tiers
            capa["label_stats"] = {
                "ok_pct": summary.get("ok_pct", 0),
                "mixed_pct": summary.get("mixed_pct", 0),
                "tau": summary.get("tau_purity"),
                "n_segments": summary.get("n_segments"),
            }
        for fila in datos["filas"]:
            clave = fila.get("clave") or sv.viz.fila_a_clave(fila)
            capa = datos["capas_por_clave"].get(clave)
            if capa and capa.get("label_stats"):
                fila.update(capa["label_stats"])
    return landcover_tiers


def _stem_from_capa(capa: dict) -> str:
    tif = capa.get("tif", "")
    if tif:
        return Path(tif).stem
    png = capa.get("png", "")
    if png:
        return Path(png).stem
    return ""


def construir_tabla_labeling(filas: list[dict], seg_id: str, incluir_rag: bool = False) -> str:
    columnas = [
        ("scale", "scale"),
        ("sigma", "σ"),
        ("min_size", "min_size"),
    ]
    if any(f.get("variant") for f in filas):
        columnas.insert(0, ("variant", "variante"))
    if incluir_rag:
        columnas.append(("rag_percentil", "RAG p"))
        columnas.append(("rag_thresh_abs", "thr abs"))
    columnas.extend(
        [
            ("n_segmentos", "n segmentos"),
            ("tam_medio_px", "tam. medio (px)"),
            ("tam_mediano_px", "tam. mediano (px)"),
            ("tam_min_px", "tam. min (px)"),
            ("tam_max_px", "tam. max (px)"),
            ("tam_medio_ha", "tam. medio (ha)"),
            ("ok_pct", "ok %"),
            ("mixed_pct", "mixed %"),
        ]
    )
    thead = "".join(f"<th>{escape(titulo)}</th>" for _, titulo in columnas)
    cuerpo: list[str] = []
    for fila in filas:
        celdas: list[str] = []
        for clave, _ in columnas:
            valor = fila.get(clave, "")
            if clave == "variant":
                texto = str(valor) if valor else "—"
            elif clave == "rag_percentil":
                texto = "—" if valor in (None, "") else str(int(valor))
            elif clave == "rag_thresh_abs":
                texto = "—" if valor in (None, "") else f"{float(valor):.6f}"
            elif clave in {"ok_pct", "mixed_pct"}:
                texto = f"{float(valor):.1f}" if valor not in (None, "") else "—"
            elif clave in {"scale", "min_size", "n_segmentos", "tam_min_px", "tam_max_px"}:
                texto = sv.viz.fmt_num(int(valor), 0) if valor not in (None, "") else "—"
            elif clave == "sigma":
                texto = f"{valor:g}" if valor not in (None, "") else "—"
            else:
                texto = sv.viz.fmt_num(float(valor)) if valor not in (None, "") else "—"
            celdas.append(f"<td>{texto}</td>")
        clave_row = fila.get("clave") or sv.viz.fila_a_clave(fila)
        rag_attr = "" if fila.get("rag_percentil") in (None, "") else str(int(fila["rag_percentil"]))
        cuerpo.append(
            f'<tr data-key="{escape(clave_row)}" data-seg="{escape(seg_id)}" '
            f'data-rag="{escape(rag_attr)}" class="fila-resumen">'
            + "".join(celdas)
            + "</tr>"
        )
    return (
        f"<table class='data resumen-table' id='tabla-{escape(seg_id)}'>"
        f"<thead><tr>{thead}</tr></thead><tbody>{''.join(cuerpo)}</tbody></table>"
    )


def leyenda_col2_html() -> str:
    items = []
    seen: set[int] = set()
    for cls_id in CLASES_VALIDAS:
        if cls_id in seen:
            continue
        seen.add(cls_id)
        r, g, b = COL2_RGB[cls_id]
        nombre = COL2_NAMES.get(cls_id, f"Clase {cls_id}")
        items.append(
            f'<span class="legend-item"><i style="background:rgb({r},{g},{b})"></i>'
            f"{escape(nombre)} <small>({cls_id})</small></span>"
        )
    for cls_id in (254, 255):
        r, g, b = COL2_RGB[cls_id]
        nombre = COL2_NAMES[cls_id]
        items.append(
            f'<span class="legend-item"><i style="background:rgb({r},{g},{b})"></i>'
            f"{escape(nombre)} <small>({cls_id})</small></span>"
        )
    return f'<div class="legend-col2">{"".join(items)}</div>'


def panel_landcover_html(lc_year: int) -> str:
    return f"""
      <div class="panel panel-landcover" id="panel-lc">
        <header id="title-lc">Landcover Col2 {lc_year}</header>
        <div class="zoom-bar">
          <button type="button" class="zoom-btn" data-panel="lc" data-action="in" title="Acercar">+</button>
          <button type="button" class="zoom-btn" data-panel="lc" data-action="out" title="Alejar">−</button>
          <button type="button" class="zoom-btn" data-panel="lc" data-action="reset" title="Restablecer">100%</button>
          <span class="zoom-label" id="zoom-label-lc">100%</span>
          <span class="zoom-hint">Referencia · zoom sincronizado</span>
        </div>
        <div class="zoom-viewport" id="viewport-lc">
          <div class="zoom-stage" id="stage-lc">
            <div class="layer-stack" id="stack-lc">
              <img class="layer" id="layer-landcover-lc" alt="Landcover Col2" loading="lazy">
            </div>
          </div>
        </div>
        <div class="layer-meta" id="meta-lc">MapBiomas Col2 {lc_year} · paleta oficial</div>
      </div>"""


def inyectar_labeling_en_html(html: str, landcover_tiers: dict[str, str], lc_year: int) -> str:
    html = html.replace(
        "Felzenszwalb vs Felzenszwalb RF_N vs SLIC vs Pipeline B",
        f"Segmentadores + etiquetas Col2 {lc_year}",
    )
    html = html.replace(
        '<label class="row"><input type="checkbox" id="chk-quicklook"> Quick-look PNG</label>',
        '<label class="row"><input type="checkbox" id="chk-labels" checked> Col2 labels</label>\n'
        '      <label>Label opacity\n'
        '        <input type="range" id="opacity-labels" min="0" max="100" value="72">\n'
        '      </label>\n'
        '      <label class="row"><input type="checkbox" id="chk-purity"> Purity raster</label>\n'
        '      <label>Purity opacity\n'
        '        <input type="range" id="opacity-purity" min="0" max="100" value="78">\n'
        '      </label>\n'
        '      <label class="row"><input type="checkbox" id="chk-quicklook"> Quick-look PNG</label>',
    )
    html = html.replace(
        '<div class="viewer" id="viewer">',
        f'<div class="viewer with-landcover" id="viewer">{panel_landcover_html(lc_year)}',
    )
    html = html.replace(
        '<img class="layer layer-quicklook" id="layer-quicklook-a"',
        '<img class="layer layer-purity" id="layer-purity-a" alt="Purity raster" loading="lazy">\n'
        '              <img class="layer layer-labels" id="layer-labels-a" alt="Col2 labels" loading="lazy">\n'
        '              <img class="layer layer-quicklook" id="layer-quicklook-a"',
    )
    html = html.replace(
        '<img class="layer layer-quicklook" id="layer-quicklook-b"',
        '<img class="layer layer-purity" id="layer-purity-b" alt="Purity raster" loading="lazy">\n'
        '              <img class="layer layer-labels" id="layer-labels-b" alt="Col2 labels" loading="lazy">\n'
        '              <img class="layer layer-quicklook" id="layer-quicklook-b"',
    )
    legend_section = f"""
  <section class="section">
    <h2>Col2 {lc_year} legend</h2>
    <p class="note">Overlay: clase mayoritaria por segmento (misma paleta Col2 que landcover). ok%/mixed% en tabla miden pureza vs τ.</p>
    {leyenda_col2_html()}
    <h3 style="margin-top:18px;font-size:0.95rem;">Pureza (clase mayoritaria)</h3>
    <p class="note">Fracción de píxeles del segmento que coinciden con la clase elegida para la etiqueta. Segmentos no_data quedan transparentes.</p>
    <div class="legend-purity">
      <span>0%</span>
      <i class="purity-gradient"></i>
      <span>50%</span>
      <span>100%</span>
    </div>
  </section>
"""
    html = html.replace('<section class="section">\n    <h2>Summary table</h2>', legend_section + '\n  <section class="section">\n    <h2>Summary table</h2>')

    extra_css = """
.viewer.with-landcover { grid-template-columns: 1fr 1fr; }
.viewer.with-landcover.compare { grid-template-columns: 1fr 1fr 1fr; }
.panel-landcover header { background: #6b4c9a; }
.legend-col2 { display: flex; flex-wrap: wrap; gap: 8px 14px; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; font-size: 0.82rem; color: #334e68; }
.legend-item i { width: 14px; height: 14px; border-radius: 3px; display: inline-block; border: 1px solid rgba(0,0,0,.12); }
.legend-purity { display: flex; align-items: center; gap: 10px; margin-top: 8px; font-size: 0.82rem; color: #334e68; }
.legend-purity .purity-gradient {
  flex: 1; max-width: 280px; height: 14px; border-radius: 4px; border: 1px solid rgba(0,0,0,.12);
  background: linear-gradient(90deg, #d73027 0%, #fee08b 50%, #1a9850 100%);
}
.layer-purity { mix-blend-mode: normal; }
@media (max-width: 1200px) {
  .viewer.with-landcover, .viewer.with-landcover.compare { grid-template-columns: 1fr; }
}
"""
    html = html.replace("</style>", extra_css + "</style>")

    patch_js = f"""
<script>
(function() {{
  const LC_TIERS = {json.dumps(landcover_tiers, ensure_ascii=False)};
  DATA.landcover_tiers = LC_TIERS;
  DATA.lc_year = {lc_year};

  PANEL.lc = {{
    tier: RES_TIERS[0], userZoom: 1, panX: 0, panY: 0, fit: 1,
    imgW: 100, imgH: 100, loading: false,
  }};

  const _statsHtml = statsHtml;
  statsHtml = function(fila) {{
    let html = _statsHtml(fila);
    if (fila && fila.ok_pct != null) {{
      html += `<div class="stat-chip"><div class="k">ok %</div><div class="v">${{fila.ok_pct.toFixed(1)}}%</div></div>`;
      html += `<div class="stat-chip"><div class="k">mixed %</div><div class="v">${{fila.mixed_pct.toFixed(1)}}%</div></div>`;
      if (fila.tau != null) html += `<div class="stat-chip"><div class="k">τ pureza</div><div class="v">${{fila.tau}}</div></div>`;
    }}
    return html;
  }};

  async function loadLandcoverTier(tier, preserveView) {{
    const st = PANEL.lc;
    if (st.loading) return;
    const lcSrc = tierSrc(DATA.landcover_tiers, tier);
    if (!lcSrc) return;
    const center = preserveView ? getViewCenter('lc') : null;
    st.loading = true;
    const img = document.getElementById('layer-landcover-lc');
    const loaded = await loadImageEl(img, lcSrc);
    const stage = document.getElementById('stage-lc');
    if (loaded) {{
      st.imgW = loaded.naturalWidth;
      st.imgH = loaded.naturalHeight;
      stage.style.width = `${{st.imgW}}px`;
      stage.style.height = `${{st.imgH}}px`;
    }}
    st.tier = tier;
    st.loading = false;
    if (!recalcFit('lc')) {{
      await new Promise(r => requestAnimationFrame(r));
      recalcFit('lc');
    }}
    if (!preserveView) {{ st.userZoom = 1; st.panX = 0; st.panY = 0; }}
    else if (center) setViewCenter('lc', center.cx, center.cy);
    aplicarZoomTransform('lc', true);
  }}

  function capaLabelTiers(sufijo) {{
    const st = PANEL[sufijo];
    const capa = capaPorClave(st.clave, st.segId);
    return capa && capa.label_tiers ? capa.label_tiers : null;
  }}

  function capaPurityTiers(sufijo) {{
    const st = PANEL[sufijo];
    const capa = capaPorClave(st.clave, st.segId);
    return capa && capa.purity_tiers ? capa.purity_tiers : null;
  }}

  function hasMosaicTiers(sufijo) {{
    const st = PANEL[sufijo];
    const tiers = st && st.segId ? mosaicTiersFor(st.segId) : DATA.mosaic_tiers;
    return !!(tiers && Object.keys(tiers).length);
  }}

  function labelOnlyMode(sufijo) {{
    return !hasMosaicTiers(sufijo) && !!capaLabelTiers(sufijo);
  }}

  async function setStageFromImage(sufijo, img, tier) {{
    const st = PANEL[sufijo];
    const stage = document.getElementById(`stage-${{sufijo}}`);
    if (img && img.naturalWidth) {{
      st.imgW = img.naturalWidth;
      st.imgH = img.naturalHeight;
      stage.style.width = `${{st.imgW}}px`;
      stage.style.height = `${{st.imgH}}px`;
    }} else if (PANEL.lc && PANEL.lc.imgW > 100) {{
      st.imgW = PANEL.lc.imgW;
      st.imgH = PANEL.lc.imgH;
      stage.style.width = `${{st.imgW}}px`;
      stage.style.height = `${{st.imgH}}px`;
    }}
    st.tier = tier;
  }}

  const _aplicarVis = aplicarVisibilidadCapas;
  aplicarVisibilidadCapas = function(sufijo) {{
    if (sufijo === 'lc') return;
    _aplicarVis(sufijo);
    const showLabels = document.getElementById('chk-labels').checked;
    const opacityLabels = document.getElementById('opacity-labels').value / 100;
    const labels = document.getElementById(`layer-labels-${{sufijo}}`);
    if (!labels) return;
    labels.classList.toggle('hidden-layer', !showLabels || !labels.getAttribute('src'));
    labels.style.opacity = showLabels ? opacityLabels : 0;
    const showPurity = document.getElementById('chk-purity').checked;
    const opacityPurity = document.getElementById('opacity-purity').value / 100;
    const purity = document.getElementById(`layer-purity-${{sufijo}}`);
    if (purity) {{
      purity.classList.toggle('hidden-layer', !showPurity || !purity.getAttribute('src'));
      purity.style.opacity = showPurity ? opacityPurity : 0;
    }}
  }};

  const _aplicarZoomTransform = aplicarZoomTransform;
  aplicarZoomTransform = function(sufijo, noSync) {{
    if (sufijo === 'lc') {{
      const st = PANEL.lc;
      const stage = document.getElementById('stage-lc');
      const total = st.userZoom * st.fit;
      stage.style.transform = `translate(${{st.panX}}px, ${{st.panY}}px) scale(${{total}})`;
      document.getElementById('zoom-label-lc').textContent =
        `${{Math.round(st.userZoom * 100)}}% · ${{st.tier}}px`;
      const needed = tierForZoom(st.userZoom);
      if (needed > st.tier && tierSrc(DATA.landcover_tiers, needed) && !st.loading) {{
        loadLandcoverTier(needed, true);
        return;
      }}
      if (!noSync) syncAllViews('lc');
      return;
    }}
    if (sufijo === 'a' || sufijo === 'b') {{
      const st = PANEL[sufijo];
      const stage = document.getElementById(`stage-${{sufijo}}`);
      const total = st.userZoom * st.fit;
      stage.style.transform = `translate(${{st.panX}}px, ${{st.panY}}px) scale(${{total}})`;
      document.getElementById(`zoom-label-${{sufijo}}`).textContent =
        `${{Math.round(st.userZoom * 100)}}% · ${{st.tier}}px`;
      const needed = tierForZoom(st.userZoom);
      const tiers = labelOnlyMode(sufijo) ? capaLabelTiers(sufijo) : mosaicTiersFor(st.segId);
      if (needed > st.tier && tierSrc(tiers, needed) && !st.loading) {{
        loadPanelTier(sufijo, needed, true);
        return;
      }}
      if (!noSync) syncPeerView(sufijo);
      return;
    }}
    _aplicarZoomTransform(sufijo, noSync);
  }};

  const _applyViewState = applyViewState;
  applyViewState = async function(sufijo, view) {{
    if (sufijo === 'lc') {{
      const st = PANEL.lc;
      const needed = tierForZoom(view.userZoom);
      if (needed > st.tier && tierSrc(DATA.landcover_tiers, needed) && !st.loading) {{
        await loadLandcoverTier(needed, true);
      }}
      st.userZoom = view.userZoom;
      recalcFit('lc');
      if (view.userZoom === 1) {{ st.panX = 0; st.panY = 0; }}
      else setViewCenter('lc', view.cx, view.cy);
      aplicarZoomTransform('lc', true);
      return;
    }}
    if ((sufijo === 'a' || sufijo === 'b') && labelOnlyMode(sufijo)) {{
      const st = PANEL[sufijo];
      const needed = tierForZoom(view.userZoom);
      const tiers = capaLabelTiers(sufijo);
      if (needed > st.tier && tierSrc(tiers, needed) && !st.loading) {{
        await loadPanelTier(sufijo, needed, true);
      }}
      st.userZoom = view.userZoom;
      recalcFit(sufijo);
      if (view.userZoom === 1) {{ st.panX = 0; st.panY = 0; }}
      else setViewCenter(sufijo, view.cx, view.cy);
      aplicarZoomTransform(sufijo, true);
      return;
    }}
    return _applyViewState(sufijo, view);
  }};

  function syncAllViews(source) {{
    if (SYNC_LOCK) return;
    SYNC_LOCK = true;
    const view = getViewState(source);
    const tasks = [applyViewState('lc', view)];
    if (source !== 'a') tasks.push(applyViewState('a', view));
    if (isCompareMode() && source !== 'b') tasks.push(applyViewState('b', view));
    Promise.all(tasks).finally(() => {{ SYNC_LOCK = false; }});
  }}

  const _syncPeerView = syncPeerView;
  syncPeerView = function(source) {{
    if (SYNC_LOCK) return;
    if (source === 'lc') {{
      syncAllViews('lc');
      return;
    }}
    SYNC_LOCK = true;
    const view = getViewState(source);
    Promise.all([
      applyViewState('lc', view),
      source === 'a' && isCompareMode() ? applyViewState('b', view) : Promise.resolve(),
      source === 'b' && isCompareMode() ? applyViewState('a', view) : Promise.resolve(),
    ]).then(() => {{
      if (isCompareMode() && (source === 'a' || source === 'b')) {{
        return _syncPeerView(source);
      }}
    }}).finally(() => {{ SYNC_LOCK = false; }});
  }};

  const _loadPanelTier = loadPanelTier;
  loadPanelTier = async function(sufijo, tier, preserveView) {{
    const st = PANEL[sufijo];
    const capa = capaPorClave(st.clave, st.segId);
    const labels = document.getElementById(`layer-labels-${{sufijo}}`);
    const purity = document.getElementById(`layer-purity-${{sufijo}}`);
    const labelSrc = capa && capa.label_tiers ? tierSrc(capa.label_tiers, tier) : null;
    const puritySrc = capa && capa.purity_tiers ? tierSrc(capa.purity_tiers, tier) : null;

    if (labelOnlyMode(sufijo)) {{
      if (st.loading) return;
      const center = preserveView ? getViewCenter(sufijo) : null;
      st.loading = true;
      const loaded = await loadImageEl(labels, labelSrc);
      await loadImageEl(purity, puritySrc);
      await setStageFromImage(sufijo, loaded, tier);
      st.loading = false;
      if (!recalcFit(sufijo)) {{
        await new Promise(r => requestAnimationFrame(r));
        recalcFit(sufijo);
      }}
      if (!preserveView) {{ st.userZoom = 1; st.panX = 0; st.panY = 0; }}
      else if (center) setViewCenter(sufijo, center.cx, center.cy);
      aplicarZoomTransform(sufijo, true);
      aplicarVisibilidadCapas(sufijo);
      return true;
    }}

    await _loadPanelTier(sufijo, tier, preserveView);
    const loadedLabel = await loadImageEl(labels, labelSrc);
    await loadImageEl(purity, puritySrc);
    if (loadedLabel && loadedLabel.naturalWidth && (!hasMosaicTiers(sufijo) || st.imgW <= 100)) {{
      await setStageFromImage(sufijo, loadedLabel, st.tier);
      recalcFit(sufijo);
      aplicarZoomTransform(sufijo, true);
    }}
    aplicarVisibilidadCapas(sufijo);
  }};

  const _resetZoom = resetZoom;
  resetZoom = function(sufijo) {{
    if (sufijo === 'lc') {{
      const st = PANEL.lc;
      st.userZoom = 1; st.panX = 0; st.panY = 0;
      if (st.tier !== RES_TIERS[0]) loadLandcoverTier(RES_TIERS[0], false);
      else aplicarZoomTransform('lc');
      return;
    }}
    _resetZoom(sufijo);
  }};

  const _init = init;
  init = function() {{
    _init();
    initZoom('lc');
    loadLandcoverTier(RES_TIERS[0], false).then(() => {{
      const clave = PANEL.a.clave;
      if (clave) {{
        loadPanelTier('a', RES_TIERS[0], false).then(() => syncAllViews('a'));
      }} else {{
        syncAllViews('a');
      }}
    }});
    if (typeof ResizeObserver !== 'undefined') {{
      const vp = document.getElementById('viewport-lc');
      if (vp) new ResizeObserver(() => {{
        if (recalcFit('lc')) aplicarZoomTransform('lc', true);
      }}).observe(vp);
    }}
  }};

  ['chk-labels','opacity-labels','chk-purity','opacity-purity'].forEach(id => {{
    document.getElementById(id).addEventListener('input', () => {{
      aplicarVisibilidadCapas('a');
      if (!document.getElementById('panel-b').classList.contains('hidden')) aplicarVisibilidadCapas('b');
    }});
  }});
}})();
</script>
"""
    html = html.replace("</body>", patch_js + "\n</body>")
    return html


def reemplazar_tablas(html: str, segmentadores: dict[str, dict]) -> str:
    for seg_id, datos in segmentadores.items():
        old = sv.construir_tabla_html_seg(datos["filas"], seg_id, incluir_rag=datos.get("incluir_rag", False))
        new = construir_tabla_labeling(datos["filas"], seg_id, incluir_rag=datos.get("incluir_rag", False))
        if old in html:
            html = html.replace(old, new)
    return html


def run_export(
    tile: str,
    seg_year: int,
    lc_year: int,
    resume: bool,
    purity_only: bool = False,
    segmenters: list[str] | None = None,
) -> None:
    script = _SCRIPT_DIR / "segmentation_labels/export_label_overlays.py"
    cmd = [
        sys.executable,
        str(script),
        "--tile",
        tile,
        "--seg-year",
        str(seg_year),
        "--lc-year",
        str(lc_year),
    ]
    if resume:
        cmd.append("--resume")
    if purity_only:
        cmd.append("--purity-only")
    for seg_id in segmenters or []:
        cmd.extend(["--segmenter", seg_id])
    print(f"[INFO] Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Segmenters + Col2 labeling dashboard.")
    parser.add_argument("--mosaic-dir", type=Path, default=Path(sv.MOSAIC_DIR))
    parser.add_argument("--html", type=Path, default=_DEFAULT_HTML)
    parser.add_argument("--skip-layers", action="store_true")
    parser.add_argument("--only-segmenter", choices=tuple(EXTENDED_SEGMENTADORES.keys()))
    parser.add_argument("--segmenters", default=None)
    parser.add_argument("--tile", default="18HYD")
    parser.add_argument("--seg-year", default="2010")
    parser.add_argument("--lc-year", type=int, default=2010)
    parser.add_argument("--skip-export", action="store_true", help="Do not run export_label_overlays.py")
    parser.add_argument("--resume-export", action="store_true")
    parser.add_argument(
        "--purity-only",
        action="store_true",
        help="Only export missing purity raster tiers before building the viewer.",
    )
    args = parser.parse_args()

    seg_ids = (
        [s.strip() for s in args.segmenters.split(",") if s.strip()]
        if args.segmenters
        else list(EXTENDED_SEGMENTADORES.keys())
    )

    if not args.skip_export:
        export_seg_ids = list(seg_ids)
        if args.purity_only and "slic" in export_seg_ids and "slic_rag" not in export_seg_ids:
            export_seg_ids.append("slic_rag")
        run_export(
            args.tile,
            int(args.seg_year),
            args.lc_year,
            args.resume_export,
            args.purity_only,
            export_seg_ids if args.purity_only else None,
        )

    html_path = args.html.resolve()
    html_dir = html_path.parent
    html_dir.mkdir(parents=True, exist_ok=True)

    segmentadores: dict[str, dict] = {}
    mosaic_tiers: dict[str, str] = {}
    tile = args.tile
    year = args.seg_year

    for seg_id in seg_ids:
        config = EXTENDED_SEGMENTADORES[seg_id]
        skip_layers_seg = args.skip_layers or (
            args.only_segmenter is not None and seg_id != args.only_segmenter
        )
        datos, tiers = cargar_segmentador_extendido(
            seg_id,
            config,
            html_dir,
            args.mosaic_dir,
            skip_layers_seg,
            None,
        )
        segmentadores[seg_id] = datos
        if tiers and not mosaic_tiers:
            mosaic_tiers = tiers

    label_root = labeling_root(tile, year, args.lc_year)
    landcover_tiers = merge_labeling(segmentadores, html_dir, label_root, args.lc_year)

    contenido = sv.generar_html(html_dir, segmentadores, mosaic_tiers, tile, year)
    contenido = reemplazar_tablas(contenido, segmentadores)
    contenido = inyectar_labeling_en_html(contenido, landcover_tiers, args.lc_year)

    try:
        html_path.write_text(contenido, encoding="utf-8")
    except OSError as exc:
        fallback = _SCRIPT_DIR / "segmenters_labeling_viewer.html"
        print(f"[ADVERTENCIA] No se pudo escribir en {html_path}: {exc}")
        html_path = fallback
        html_path.write_text(contenido, encoding="utf-8")

    print(f"[OK] Dashboard: {html_path}")
    n_label = sum(
        1
        for d in segmentadores.values()
        for c in d["capas_por_clave"].values()
        if c.get("label_tiers")
    )
    n_purity = sum(
        1
        for d in segmentadores.values()
        for c in d["capas_por_clave"].values()
        if c.get("purity_tiers")
    )
    print(f"[OK] Combinaciones con etiquetas: {n_label}")
    print(f"[OK] Combinaciones con pureza: {n_purity}")
    print(f"[INFO] Servir: cd {html_dir} && python3 -m http.server 8765 --bind 0.0.0.0")
    print(f"[INFO] URL: http://localhost:8765/{html_path.name}")


if __name__ == "__main__":
    main()
