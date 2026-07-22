#!/usr/bin/env python3
"""
Visualizador de los dos últimos experimentos Lv3:
  - seg_felzenszwalb_rf_lv3     (34 bandas REPORT, 1 combo)
  - seg_felzenszwalb_ablacion_lv3 (medianas + medianas+dura, 24 corridas)

Uso:
  cd labeling/image_segmentation
  python lv3_results_viewer.py
  python lv3_results_viewer.py --skip-layers

Servir:
  cd /home/lserey/mapbiomas_land/test/image_segmentation
  python3 -m http.server 8765
  → http://localhost:8765/lv3_results_viewer.html
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from html import escape
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_FELZ_DIR = _SCRIPT_DIR / "seg_felzenszwalb"
_RF_N_DIR = _SCRIPT_DIR / "seg_felzenszwalb_rf_n"
for _p in (_SCRIPT_DIR, _FELZ_DIR, _RF_N_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import segmenters_viewer as sv  # noqa: E402
from seg_felzenszwalb_rf_n_grid import localizar_mosaico_184  # noqa: E402

_DATA_ROOT = Path("/home/lserey/mapbiomas_land/test/image_segmentation")
_LV3_RF_DIR = _DATA_ROOT / "seg_felzenszwalb_rf_lv3"
_ABL_LV3_DIR = _DATA_ROOT / "seg_felzenszwalb_ablacion_lv3"
_MOSAIC_184 = Path("/home/lserey/mapbiomas_land/test/mosaics/mosaics_184bands")
_LABEL_ROOT = None  # resolved at runtime via labeling_root()
_DEFAULT_HTML = _DATA_ROOT / "lv3_results_viewer.html"

CAPAS = sv.CAPAS_SUBDIR
RES_TIERS = sv.RES_TIERS
REF_3B = 16732
REF_LV3 = 168723
SCALE = 200
SIGMA = 0.1


def etiqueta_slug(corrida: str) -> str:
    s = corrida.replace("+", "_mas_")
    return re.sub(r"[^\w.\-]", "_", s)


def cargar_lv3_rf(output_dir: Path) -> tuple[list[dict], list[dict], str, str]:
    candidatos = sorted(output_dir.glob("resumen_*_lv3_rf.csv"))
    if not candidatos:
        return [], [], "", ""
    ruta = candidatos[0]
    m = re.match(r"resumen_(?P<tile>[^_]+)_(?P<year>\d+)_lv3_rf\.csv$", ruta.name)
    tile = m.group("tile") if m else ""
    year = m.group("year") if m else ""
    filas: list[dict] = []
    with ruta.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            filas.append(
                {
                    "clave": f"s{int(float(row['scale']))}_sig{row['sigma']}",
                    "corrida": "lv3_completo",
                    "label": "Lv3 completo (34 bandas)",
                    "scale": int(float(row["scale"])),
                    "sigma": float(row["sigma"]),
                    "n_bandas": int(float(row["n_bands_usadas"])),
                    "n_segmentos": int(float(row["n_segmentos"])),
                    "tam_medio_px": float(row["tam_medio_px"]),
                    "tam_mediano_px": float(row["tam_mediano_px"]),
                    "tam_medio_ha": float(row["tam_medio_ha"]),
                    "ratio_vs_3bandas": round(int(float(row["n_segmentos"])) / REF_3B, 3),
                }
            )
    return filas, [], tile, year


def cargar_ablacion_lv3(output_dir: Path) -> tuple[list[dict], list[dict], str, str]:
    candidatos = sorted(output_dir.glob("resumen_ablacion_lv3_*.csv"))
    if not candidatos:
        return [], [], "", ""
    ruta = candidatos[0]
    m = re.match(r"resumen_ablacion_lv3_(?P<tile>[^_]+)_(?P<year>\d+)\.csv$", ruta.name)
    tile = m.group("tile") if m else ""
    year = m.group("year") if m else ""
    filas: list[dict] = []
    with ruta.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            corrida = row["corrida"].strip()
            slug = etiqueta_slug(corrida)
            filas.append(
                {
                    "clave": slug,
                    "corrida": corrida,
                    "label": corrida,
                    "scale": SCALE,
                    "sigma": SIGMA,
                    "n_bandas": int(float(row["n_bandas"])),
                    "n_segmentos": int(float(row["n_segmentos"])),
                    "tam_medio_px": float(row["tam_medio_px"]),
                    "tam_mediano_px": float(row["tam_mediano_px"]),
                    "tam_medio_ha": float(row["tam_medio_ha"]),
                    "ratio_vs_3bandas": float(row["ratio_vs_3bandas"]),
                    "ratio_vs_lv3_completo": float(row["ratio_vs_lv3_completo"]),
                    "delta_vs_medianas": int(float(row["delta_vs_medianas"])),
                }
            )
    filas.sort(key=lambda r: r["n_segmentos"])
    return filas, [], tile, year


def descubrir_capas(
    output_dir: Path,
    html_dir: Path,
    tile: str,
    year: str,
    *,
    prefijo: str,
) -> dict[str, dict]:
    capas_dir = output_dir / CAPAS
    out: dict[str, dict] = {}
    for ruta_tif in sorted(output_dir.glob(f"{prefijo}*.tif")):
        base = ruta_tif.stem
        if prefijo == "seg_abl_lv3_":
            slug = base.replace(f"seg_abl_lv3_{tile}_{year}_", "")
            clave = slug
        else:
            m = re.search(r"_s(\d+)_sig([\d.]+)$", base)
            clave = f"s{m.group(1)}_sig{m.group(2)}" if m else base
        ruta_png = ruta_tif.with_suffix(".png")
        out[clave] = {
            "clave": clave,
            "tile": tile,
            "year": year,
            "scale": SCALE,
            "sigma": SIGMA,
            "tif": sv.viz.ruta_publica(html_dir, ruta_tif),
            "png": sv.viz.ruta_publica(html_dir, ruta_png) if ruta_png.is_file() else "",
            "overlay_tiers": sv.viz.descubrir_tiers_capa(html_dir, capas_dir, base, "overlay"),
            "boundaries_tiers": sv.viz.descubrir_tiers_capa(html_dir, capas_dir, base, "boundaries"),
        }
    return out


def exportar_capas_generico(
    output_dir: Path,
    mosaic_184_dir: Path,
    tile: str,
    year: str,
    glob_tif: str = "seg_*.tif",
) -> dict[str, str] | None:
    """Exporta mosaico RGB + overlays para todos los TIF del directorio."""
    try:
        import numpy as np
        import rasterio
        from rf_selected_bands import resolver_rgb_desde_descriptions
        from seg_felzenszwalb_grid import (
            NODATA,
            componer_rgb,
            construir_mascara_nodata,
            contornos_rgba_desde_labels,
            guardar_rgba_png,
            overlay_rgba_desde_labels,
            reducir_para_quicklook,
            resolver_nodata,
        )
        from PIL import Image
    except ImportError as exc:
        print(f"[ADVERTENCIA] Sin export capas: {exc}")
        return None

    capas_dir = output_dir / CAPAS
    capas_dir.mkdir(parents=True, exist_ok=True)
    ruta_mosaico = localizar_mosaico_184(mosaic_184_dir, tile, int(year))
    mosaic_stem = f"mosaic_{tile}_{year}_rgb"
    mosaic_tiers: dict[str, str] = {}

    print(f"[INFO] Capas → {capas_dir}")

    with rasterio.open(ruta_mosaico) as src:
        descriptions = list(src.descriptions or [])
        if len(descriptions) != src.count:
            descriptions = [descriptions[i] if i < len(descriptions) else "" for i in range(src.count)]
        rgb_positions = resolver_rgb_desde_descriptions(descriptions)
        rgb_stack = np.stack(
            [src.read(pos + 1).astype(np.float32) for pos in rgb_positions],
            axis=-1,
        )
        nodata_valor = resolver_nodata(src, NODATA)
        validos = construir_mascara_nodata(rgb_stack, nodata_valor)
        rgb = componer_rgb(rgb_stack, [0, 1, 2], validos)
        rgb = np.nan_to_num(rgb, nan=0.0, posinf=1.0, neginf=0.0)

    labels_vacio = np.zeros(validos.shape, dtype=np.int32)
    for lado in RES_TIERS:
        rgb_q, _, _ = reducir_para_quicklook(rgb, labels_vacio, validos, lado)
        fname = f"{mosaic_stem}_l{lado}.png"
        Image.fromarray((np.clip(rgb_q, 0, 1) * 255).astype(np.uint8), mode="RGB").save(capas_dir / fname)
        mosaic_tiers[str(lado)] = f"{CAPAS}/{fname}"

    for ruta_tif in sorted(output_dir.glob(glob_tif)):
        with rasterio.open(ruta_tif) as seg:
            labels = seg.read(1).astype(np.int32)
        if labels.shape != validos.shape:
            print(f"[ERROR] Shape distinta: {ruta_tif.name}")
            sys.exit(1)
        base = ruta_tif.stem
        for lado in RES_TIERS:
            rgb_q, labels_q, validos_q = reducir_para_quicklook(rgb, labels, validos, lado)
            guardar_rgba_png(capas_dir / f"{base}_overlay_l{lado}.png", overlay_rgba_desde_labels(labels_q, validos_q))
            guardar_rgba_png(
                capas_dir / f"{base}_boundaries_l{lado}.png",
                contornos_rgba_desde_labels(labels_q, validos_q, labels_ref=labels, validos_ref=validos),
            )
        print(f"  → {base}_overlay/boundaries_l*.png")

    return mosaic_tiers


def labeling_root(tile: str, seg_year: str, lc_year: int) -> Path:
    return _DATA_ROOT / "labeling_overlays" / f"tile_{tile}_{seg_year}_lc{lc_year}"


def _stem_from_capa(capa: dict) -> str:
    tif = capa.get("tif", "")
    if tif:
        return Path(tif).name.rsplit("/", 1)[-1].replace(".tif", "")
    png = capa.get("png", "")
    if png:
        return Path(png).name.rsplit("/", 1)[-1].replace(".png", "")
    return ""


def merge_labeling(
    pipelines: dict[str, dict],
    html_dir: Path,
    label_root: Path,
) -> None:
    """Attach Col2 label overlay tiers and ok/mixed stats to each combination."""
    mapping = {"lv3_rf": "lv3_rf", "ablacion_lv3": "ablacion_lv3"}
    for pipe_id, seg_id in mapping.items():
        datos = pipelines.get(pipe_id)
        if not datos:
            continue
        seg_label_dir = label_root / seg_id
        if not seg_label_dir.is_dir():
            continue
        summaries = {
            p.stem.replace("_assignment", ""): p for p in seg_label_dir.glob("*_assignment.json")
        }
        for clave, capa in datos["capas_por_clave"].items():
            stem = _stem_from_capa(capa)
            summary_path = summaries.get(stem)
            if not summary_path:
                continue
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            capa["label_tiers"] = {
                tier: sv.viz.ruta_publica(html_dir, label_root / seg_id / rel)
                for tier, rel in summary.get("label_tiers", {}).items()
            }
            capa["label_stats"] = {
                "ok_pct": summary.get("ok_pct", 0),
                "mixed_pct": summary.get("mixed_pct", 0),
                "tau": summary.get("tau_purity"),
                "n_segments": summary.get("n_segments"),
            }
        for fila in datos["filas"]:
            capa = datos["capas_por_clave"].get(fila.get("clave", ""))
            if capa and capa.get("label_stats"):
                fila.update(capa["label_stats"])


def cargar_landcover_tiers(html_dir: Path, label_root: Path, tile: str, lc_year: int) -> dict[str, str]:
    lc_json = label_root / "landcover_tiers.json"
    if lc_json.is_file():
        payload = json.loads(lc_json.read_text(encoding="utf-8"))
        return {k: sv.viz.ruta_publica(html_dir, label_root / v) for k, v in payload.get("tiers", {}).items()}
    capas = label_root / CAPAS
    tiers = {}
    for lado in RES_TIERS:
        fname = f"{tile}_classification_{lc_year}_lc_l{lado}.png"
        if (capas / fname).is_file():
            tiers[str(lado)] = sv.viz.ruta_publica(html_dir, capas / fname)
    return tiers


def generar_html(
    tile: str,
    year: str,
    lc_year: int,
    lv3_rf: dict,
    abl_lv3: dict,
    mosaic_tiers: dict[str, str],
    landcover_tiers: dict[str, str],
) -> str:
    payload = {
        "tile": tile,
        "year": year,
        "lc_year": lc_year,
        "scale": SCALE,
        "sigma": SIGMA,
        "ref_3b": REF_3B,
        "ref_lv3": REF_LV3,
        "mosaic_tiers": mosaic_tiers,
        "landcover_tiers": landcover_tiers,
        "res_tiers": RES_TIERS,
        "lv3_rf": lv3_rf,
        "ablacion_lv3": abl_lv3,
    }

    lv3_n = lv3_rf["filas"][0]["n_segmentos"] if lv3_rf["filas"] else 0
    abl_filas = abl_lv3["filas"]
    mejor = abl_filas[0] if abl_filas else None
    peor = abl_filas[-1] if abl_filas else None

    tabla_rows = ""
    for f in sorted(abl_filas, key=lambda r: r["n_segmentos"]):
        ok = f"{f['ok_pct']:.1f}" if f.get("ok_pct") is not None else "—"
        mix = f"{f['mixed_pct']:.1f}" if f.get("mixed_pct") is not None else "—"
        tabla_rows += (
            f"<tr data-key='{escape(f['clave'])}' data-pipe='ablacion_lv3' class='fila-corrida'>"
            f"<td>{escape(f['corrida'])}</td>"
            f"<td>{f['n_bandas']}</td>"
            f"<td>{f['n_segmentos']:,}</td>"
            f"<td>{f['ratio_vs_3bandas']:.2f}</td>"
            f"<td>{f['ratio_vs_lv3_completo']:.3f}</td>"
            f"<td>{f['delta_vs_medianas']:,}</td>"
            f"<td>{f['tam_mediano_px']:.0f}</td>"
            f"<td>{ok}</td><td>{mix}</td></tr>"
        )
    if lv3_rf["filas"]:
        f = lv3_rf["filas"][0]
        ok = f"{f['ok_pct']:.1f}" if f.get("ok_pct") is not None else "—"
        mix = f"{f['mixed_pct']:.1f}" if f.get("mixed_pct") is not None else "—"
        tabla_rows = (
            f"<tr data-key='{escape(f['clave'])}' data-pipe='lv3_rf' class='fila-corrida selected'>"
            f"<td><strong>Lv3 completo</strong></td>"
            f"<td>{f['n_bandas']}</td>"
            f"<td>{f['n_segmentos']:,}</td>"
            f"<td>{f['ratio_vs_3bandas']:.2f}</td>"
            f"<td>1.000</td><td>—</td>"
            f"<td>{f['tam_mediano_px']:.0f}</td>"
            f"<td>{ok}</td><td>{mix}</td></tr>"
        ) + tabla_rows

    opts_abl = "".join(
        f"<option value='{escape(f['clave'])}'>{escape(f['corrida'])} ({f['n_segmentos']:,} seg)</option>"
        for f in abl_filas
    )
    mejor_n_seg = f"{mejor['n_segmentos']:,}" if mejor else "—"
    peor_culpable = (
        peor["corrida"].replace("medianas+", "")
        if peor and "+" in peor["corrida"]
        else "—"
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lv3 RF + Ablación Lv3 — {escape(tile)} {year}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root {{ --bg:#f4f6f8; --card:#fff; --line:#d9e2ec; --text:#1f2933; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:"Segoe UI",Arial,sans-serif; background:var(--bg); color:var(--text); }}
.wrap {{ max-width:1440px; margin:0 auto; padding:24px; }}
.hero {{ background:linear-gradient(135deg,#5b21b6,#7c3aed 45%,#b45309); color:#fff; padding:28px 32px; border-radius:12px; margin-bottom:20px; }}
.hero h1 {{ margin:0 0 8px; font-size:1.7rem; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-bottom:20px; }}
.kpi {{ background:var(--card); border-radius:10px; padding:14px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
.kpi .label {{ font-size:.82rem; color:#627d98; }}
.kpi .value {{ font-size:1.2rem; font-weight:700; }}
.section {{ background:var(--card); border-radius:12px; padding:20px; margin-bottom:20px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
.section h2 {{ margin:0 0 14px; font-size:1.1rem; border-bottom:2px solid var(--line); padding-bottom:8px; }}
.controls {{ display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin-bottom:14px; }}
.controls label {{ display:flex; flex-direction:column; gap:4px; font-size:.88rem; color:#486581; }}
.controls select {{ min-width:200px; padding:8px; border:1px solid var(--line); border-radius:8px; }}
.viewer {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; }}
.viewer.compare-2 {{ grid-template-columns:1fr 1fr 1fr; }}
.panel {{ border:1px solid var(--line); border-radius:10px; overflow:hidden; background:#0b0b0b; }}
.panel header {{ color:#fff; padding:10px 14px; font-size:.9rem; }}
.panel-lc header {{ background:#6b4c9a; }}
.panel-a header {{ background:#7c3aed; }}
.panel-b header {{ background:#b45309; }}
.zoom-bar {{ display:flex; gap:8px; padding:8px 12px; background:#edf2f7; align-items:center; flex-wrap:wrap; }}
.zoom-btn {{ padding:4px 10px; border:1px solid var(--line); border-radius:6px; background:#fff; cursor:pointer; }}
.zoom-viewport {{ position:relative; width:100%; aspect-ratio:1; overflow:hidden; background:#111; cursor:grab; }}
.zoom-stage {{ transform-origin:0 0; position:relative; }}
.layer-stack {{ position:relative; width:100%; height:100%; }}
.layer-stack img {{ position:absolute; inset:0; width:100%; height:100%; object-fit:fill; }}
.hidden-layer {{ visibility:hidden; opacity:0; }}
.hidden {{ display:none !important; }}
.layer-meta {{ padding:8px 12px; background:#f7fafc; font-size:.8rem; color:#486581; }}
.stats-inline {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(110px,1fr)); gap:6px; padding:10px; background:#fff; }}
.stat-chip {{ background:#f0f4f8; border-radius:8px; padding:8px; }}
.stat-chip .k {{ font-size:.75rem; color:#627d98; }}
.stat-chip .v {{ font-weight:600; font-size:.92rem; }}
table.data {{ width:100%; border-collapse:collapse; font-size:.88rem; }}
table.data th, table.data td {{ border:1px solid var(--line); padding:7px 9px; text-align:right; }}
table.data thead th {{ background:#ede9fe; }}
table.data tbody tr {{ cursor:pointer; }}
table.data tbody tr:hover {{ background:#faf5ff; }}
table.data tbody tr.selected {{ background:#ddd6fe; }}
.chart {{ min-height:420px; }}
@media(max-width:1100px) {{ .viewer {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <h1>Lv3 RF + Ablación Lv3 — {escape(tile)} {year}</h1>
    <p>Felzenszwalb s={SCALE}, σ={SIGMA}, min_size=20 · z-score por banda · etiquetas Col2 {lc_year}</p>
  </header>

  <div class="kpis">
    <div class="kpi"><div class="label">Lv3 completo (34b)</div><div class="value">{lv3_n:,} seg</div></div>
    <div class="kpi"><div class="label">Ref. 3 bandas</div><div class="value">{REF_3B:,}</div></div>
    <div class="kpi"><div class="label">Ratio Lv3 / 3b</div><div class="value">{lv3_n/REF_3B:.1f}×</div></div>
    <div class="kpi"><div class="label">Mejor ablación</div><div class="value">{mejor['corrida'] if mejor else '—'}</div></div>
    <div class="kpi"><div class="label">Mejor n_seg</div><div class="value">{mejor_n_seg}</div></div>
    <div class="kpi"><div class="label">Peor culpable</div><div class="value">{peor_culpable}</div></div>
  </div>

  <section class="section">
    <h2>Explorador de capas</h2>
    <div class="controls">
      <label class="row"><input type="checkbox" id="chk-mosaic" checked> Mosaico RGB</label>
      <label class="row"><input type="checkbox" id="chk-seg" checked> Segmentos</label>
      <label class="row"><input type="checkbox" id="chk-bnd" checked> Contornos</label>
      <label class="row"><input type="checkbox" id="chk-labels" checked> Etiquetas Col2</label>
      <label>Opacidad seg <input type="range" id="opacity-seg" min="0" max="100" value="60"></label>
      <label>Ablación Lv3 <select id="sel-abl">{opts_abl}</select></label>
      <button type="button" id="btn-compare" class="active">Vista simple</button>
    </div>
    <div class="viewer" id="viewer">
      {panel_html('lc', f'Landcover Col2 {lc_year}', 'panel-lc')}
      {panel_html('a', 'Lv3 RF completo', 'panel-a', with_labels=True)}
      {panel_html('b', 'Ablación Lv3', 'panel-b', hidden=False, with_labels=True)}
    </div>
  </section>

  <section class="section">
    <h2>Segmentos por corrida</h2>
    <div id="chart-seg" class="chart"></div>
  </section>

  <section class="section">
    <h2>Tabla comparativa (ablación + Lv3 completo)</h2>
    <table class="data" id="tabla">
      <thead><tr>
        <th>corrida</th><th>n_bandas</th><th>n_segmentos</th>
        <th>ratio 3b</th><th>ratio lv3</th><th>Δ medianas</th><th>tam_mediano</th>
        <th>ok %</th><th>mixed %</th>
      </tr></thead>
      <tbody>{tabla_rows}</tbody>
    </table>
  </section>
</div>

<script>
const DATA = {json.dumps(payload, ensure_ascii=False)};
const RES_TIERS = DATA.res_tiers;
const PANEL = {{
  lc: {{ tier:RES_TIERS[0], userZoom:1, panX:0, panY:0, fit:1, imgW:100, imgH:100, loading:false }},
  a:  {{ pipe:'lv3_rf', clave: DATA.lv3_rf.filas[0]?.clave, tier:RES_TIERS[0], userZoom:1, panX:0, panY:0, fit:1, imgW:100, imgH:100, loading:false }},
  b:  {{ pipe:'ablacion_lv3', clave: DATA.ablacion_lv3.filas[0]?.clave, tier:RES_TIERS[0], userZoom:1, panX:0, panY:0, fit:1, imgW:100, imgH:100, loading:false }},
}};
let SYNC_LOCK = false;

function pipeData(id) {{ return DATA[id]; }}
function capa(pipe, clave) {{ return pipeData(pipe).capas_por_clave[clave] || null; }}

function tierSrc(tiers, tier) {{
  if (!tiers) return null;
  return tiers[String(tier)] || tiers[String(RES_TIERS[0])] || Object.values(tiers)[0];
}}

function recalcFit(suf) {{
  const st = PANEL[suf];
  const vp = document.getElementById('viewport-'+suf);
  if (!vp || st.imgW<=0) return false;
  const r = vp.getBoundingClientRect();
  st.fit = Math.min(r.width/st.imgW, r.height/st.imgH);
  return true;
}}

function aplicarZoom(suf, noSync) {{
  const st = PANEL[suf];
  const stage = document.getElementById('stage-'+suf);
  const total = st.userZoom * st.fit;
  stage.style.transform = `translate(${{st.panX}}px,${{st.panY}}px) scale(${{total}})`;
  document.getElementById('zoom-label-'+suf).textContent = Math.round(st.userZoom*100)+'% · '+st.tier+'px';
  if (!noSync) syncPeers(suf);
}}

function getCenter(suf) {{
  const st = PANEL[suf];
  const vp = document.getElementById('viewport-'+suf).getBoundingClientRect();
  const t = st.userZoom*st.fit;
  return {{ cx:(vp.width/2-st.panX)/(st.imgW*t), cy:(vp.height/2-st.panY)/(st.imgH*t) }};
}}

function setCenter(suf, cx, cy) {{
  const st = PANEL[suf];
  const vp = document.getElementById('viewport-'+suf).getBoundingClientRect();
  const t = st.userZoom*st.fit;
  st.panX = vp.width/2 - cx*st.imgW*t;
  st.panY = vp.height/2 - cy*st.imgH*t;
}}

function syncPeers(src) {{
  if (SYNC_LOCK) return;
  SYNC_LOCK = true;
  const v = {{ ...getCenter(src), userZoom:PANEL[src].userZoom, tier:PANEL[src].tier }};
  ['lc','a','b'].forEach(s => {{
    if (s===src || (s==='b' && document.getElementById('panel-b').classList.contains('hidden'))) return;
    applyView(s, v);
  }});
  SYNC_LOCK = false;
}}

async function loadImg(el, src) {{
  return new Promise(res => {{
    if (!src) {{ el.removeAttribute('src'); res(null); return; }}
    if (el.src===src && el.complete) {{ res(el); return; }}
    el.onload = () => res(el);
    el.onerror = () => res(null);
    el.src = src;
  }});
}}

async function applyView(suf, v) {{
  const st = PANEL[suf];
  st.userZoom = v.userZoom;
  if (v.tier > st.tier) await loadPanel(suf, v.tier, true);
  recalcFit(suf);
  if (v.userZoom===1) {{ st.panX=0; st.panY=0; }}
  else setCenter(suf, v.cx, v.cy);
  aplicarZoom(suf, true);
}}

async function loadPanel(suf, tier, preserve) {{
  const st = PANEL[suf];
  const center = preserve ? getCenter(suf) : null;
  st.loading = true;
  let mosaicSrc, segSrc, bndSrc, labelSrc;
  if (suf==='lc') {{
    mosaicSrc = null; segSrc = tierSrc(DATA.landcover_tiers, tier); bndSrc = null; labelSrc = null;
  }} else {{
    const c = capa(st.pipe, st.clave);
    mosaicSrc = tierSrc(DATA.mosaic_tiers, tier);
    segSrc = c ? tierSrc(c.overlay_tiers, tier) : null;
    bndSrc = c ? tierSrc(c.boundaries_tiers, tier) : null;
    labelSrc = c ? tierSrc(c.label_tiers, tier) : null;
  }}
  const mosaic = document.getElementById('layer-mosaic-'+suf);
  const seg = document.getElementById('layer-seg-'+suf);
  const bnd = document.getElementById('layer-bnd-'+suf);
  const label = document.getElementById('layer-label-'+suf);
  const loaded = await loadImg(suf==='lc' ? seg : mosaic, suf==='lc' ? segSrc : mosaicSrc);
  if (suf!=='lc') await Promise.all([loadImg(seg, segSrc), loadImg(bnd, bndSrc), loadImg(label, labelSrc)]);
  const ref = loaded || seg;
  if (ref && ref.naturalWidth) {{
    st.imgW = ref.naturalWidth; st.imgH = ref.naturalHeight;
    const stage = document.getElementById('stage-'+suf);
    stage.style.width = st.imgW+'px'; stage.style.height = st.imgH+'px';
  }}
  st.tier = tier; st.loading = false;
  recalcFit(suf);
  if (!preserve) {{ st.userZoom=1; st.panX=0; st.panY=0; }}
  else if (center) setCenter(suf, center.cx, center.cy);
  aplicarZoom(suf, true);
  visCapas(suf);
  updateHeader(suf);
}}

function visCapas(suf) {{
  if (suf==='lc') return;
  const showM = document.getElementById('chk-mosaic').checked;
  const showS = document.getElementById('chk-seg').checked;
  const showB = document.getElementById('chk-bnd').checked;
  const showL = document.getElementById('chk-labels').checked;
  const op = document.getElementById('opacity-seg').value/100;
  ['mosaic','seg','bnd','label'].forEach(l => {{
    const el = document.getElementById('layer-'+l+'-'+suf);
    if (!el) return;
    const show = l==='mosaic' ? showM : l==='seg' ? showS : l==='bnd' ? showB : showL;
    el.classList.toggle('hidden-layer', !show || !el.src);
  }});
  document.getElementById('layer-seg-'+suf).style.opacity = showS ? op : 0;
  const lbl = document.getElementById('layer-label-'+suf);
  if (lbl) lbl.style.opacity = showL ? 0.85 : 0;
}}

function updateHeader(suf) {{
  const hdr = document.getElementById('title-'+suf);
  const st = PANEL[suf];
  if (suf==='lc') {{ hdr.textContent = 'Landcover Col2 '+DATA.lc_year; return; }}
  const filas = pipeData(st.pipe).filas;
  const fila = filas.find(f => f.clave===st.clave);
  const lbl = st.pipe==='lv3_rf' ? 'Lv3 completo' : fila?.corrida || st.clave;
  const n = fila ? fila.n_segmentos.toLocaleString('es-CL')+' seg' : '';
  hdr.textContent = lbl + (n ? ' · '+n : '');
  if (!fila) return;
  const chips = [
    ['Bandas', fila.n_bandas], ['Segmentos', fila.n_segmentos.toLocaleString('es-CL')],
    ['Ratio 3b', fila.ratio_vs_3bandas+'×'], ['Tam. mediano', fila.tam_mediano_px+' px'],
  ];
  if (fila.ok_pct != null) chips.push(['ok %', fila.ok_pct.toFixed(1)]);
  if (fila.mixed_pct != null) chips.push(['mixed %', fila.mixed_pct.toFixed(1)]);
  document.getElementById('stats-'+suf).innerHTML = chips.map(([k,v]) => `<div class="stat-chip"><div class="k">${{k}}</div><div class="v">${{v}}</div></div>`).join('');
}}

function initZoom(suf) {{
  const vp = document.getElementById('viewport-'+suf);
  let drag=false, sx,sy, px,py;
  vp.addEventListener('wheel', e => {{
    e.preventDefault();
    const f = e.deltaY<0 ? 1.15 : 1/1.15;
    const st = PANEL[suf];
    const r = vp.getBoundingClientRect();
    const mx = e.clientX-r.left, my = e.clientY-r.top;
    const t0 = st.userZoom*st.fit, t1 = Math.min(24,Math.max(1,st.userZoom*f))*st.fit;
    st.userZoom = Math.min(24,Math.max(1,st.userZoom*f));
    st.panX = mx-(mx-st.panX)*(t1/t0); st.panY = my-(my-st.panY)*(t1/t0);
    if (st.userZoom===1) {{ st.panX=0; st.panY=0; }}
    aplicarZoom(suf);
  }}, {{passive:false}});
  vp.addEventListener('mousedown', e => {{ if(e.button!==0)return; drag=true; sx=e.clientX; sy=e.clientY; px=PANEL[suf].panX; py=PANEL[suf].panY; }});
  window.addEventListener('mousemove', e => {{ if(!drag)return; PANEL[suf].panX=px+e.clientX-sx; PANEL[suf].panY=py+e.clientY-sy; aplicarZoom(suf); }});
  window.addEventListener('mouseup', () => drag=false);
  document.querySelectorAll(`.zoom-btn[data-panel="${{suf}}"]`).forEach(btn => {{
    btn.onclick = () => {{
      const st = PANEL[suf];
      if (btn.dataset.action==='reset') {{ st.userZoom=1; st.panX=0; st.panY=0; }}
      else if (btn.dataset.action==='in') st.userZoom = Math.min(24, st.userZoom*1.25);
      else st.userZoom = Math.max(1, st.userZoom/1.25);
      aplicarZoom(suf);
    }};
  }});
}}

function seleccion(clave, pipe) {{
  document.querySelectorAll('.fila-corrida').forEach(r => {{
    r.classList.toggle('selected', r.dataset.key===clave && r.dataset.pipe===pipe);
  }});
  if (pipe==='lv3_rf') {{ PANEL.a.clave = clave; loadPanel('a', PANEL.a.tier, false); }}
  else {{ PANEL.b.clave = clave; document.getElementById('sel-abl').value = clave; if (!document.getElementById('panel-b').classList.contains('hidden')) loadPanel('b', PANEL.b.tier, false); }}
}}

function renderChart() {{
  const filas = [...DATA.ablacion_lv3.filas].sort((a,b)=>a.n_segmentos-b.n_segmentos);
  const lv3 = DATA.lv3_rf.filas[0];
  const labels = filas.map(f => f.corrida);
  const vals = filas.map(f => f.n_segmentos);
  if (lv3) {{ labels.push('Lv3 completo'); vals.push(lv3.n_segmentos); }}
  Plotly.newPlot('chart-seg', [{{
    x: vals, y: labels, type:'bar', orientation:'h',
    marker:{{ color: labels.map(l => l==='Lv3 completo' ? '#7c3aed' : l==='medianas' ? '#059669' : '#d97706') }},
  }}], {{
    title:'Segmentos por corrida',
    shapes:[
      {{ type:'line', x0:DATA.ref_3b, x1:DATA.ref_3b, y0:-0.5, y1:labels.length-0.5, line:{{color:'#2563eb',dash:'dash'}} }},
      {{ type:'line', x0:DATA.ref_lv3, x1:DATA.ref_lv3, y0:-0.5, y1:labels.length-0.5, line:{{color:'#7c3aed',dash:'dot'}} }},
    ],
    margin:{{l:200,r:20,t:40,b:50}},
  }}, {{responsive:true}});
}}

document.addEventListener('DOMContentLoaded', () => {{
  ['lc','a','b'].forEach(initZoom);
  loadPanel('lc', RES_TIERS[0], false);
  loadPanel('a', RES_TIERS[0], false);
  loadPanel('b', RES_TIERS[0], false);
  document.getElementById('sel-abl').addEventListener('change', e => {{
    PANEL.b.clave = e.target.value;
    if (!document.getElementById('panel-b').classList.contains('hidden')) loadPanel('b', PANEL.b.tier, false);
    seleccion(e.target.value, 'ablacion_lv3');
  }});
  document.getElementById('btn-compare').addEventListener('click', () => {{
    const btn = document.getElementById('btn-compare');
    const show = btn.classList.toggle('active');
    document.getElementById('panel-b').classList.toggle('hidden', !show);
    btn.textContent = show ? 'Vista simple' : 'Comparar Lv3 vs ablación';
    if (show) {{ PANEL.b.clave = document.getElementById('sel-abl').value; loadPanel('b', PANEL.b.tier, false).then(() => syncPeers('a')); }}
  }});
  ['chk-mosaic','chk-seg','chk-bnd','chk-labels','opacity-seg'].forEach(id => {{
    document.getElementById(id).addEventListener('input', () => {{ visCapas('a'); visCapas('b'); }});
  }});
  document.querySelectorAll('.fila-corrida').forEach(r => {{
    r.addEventListener('click', () => seleccion(r.dataset.key, r.dataset.pipe));
  }});
  renderChart();
}});
</script>
</body>
</html>"""


def panel_html(
    pid: str,
    titulo: str,
    cls: str,
    hidden: bool = False,
    *,
    with_labels: bool = False,
) -> str:
    h = " hidden" if hidden else ""
    label_img = (
        f'<img class="layer" id="layer-label-{pid}" alt="labels" loading="lazy">'
        if with_labels
        else ""
    )
    return f"""
      <div class="panel {cls}{h}" id="panel-{pid}">
        <header id="title-{pid}">{escape(titulo)}</header>
        <div class="zoom-bar">
          <button type="button" class="zoom-btn" data-panel="{pid}" data-action="in">+</button>
          <button type="button" class="zoom-btn" data-panel="{pid}" data-action="out">−</button>
          <button type="button" class="zoom-btn" data-panel="{pid}" data-action="reset">100%</button>
          <span id="zoom-label-{pid}">100%</span>
        </div>
        <div class="zoom-viewport" id="viewport-{pid}">
          <div class="zoom-stage" id="stage-{pid}">
            <div class="layer-stack">
              <img class="layer" id="layer-mosaic-{pid}" alt="mosaic" loading="lazy">
              <img class="layer" id="layer-seg-{pid}" alt="seg" loading="lazy">
              {label_img}
              <img class="layer" id="layer-bnd-{pid}" alt="bnd" loading="lazy">
            </div>
          </div>
        </div>
        <div class="layer-meta" id="meta-{pid}"></div>
        <div class="stats-inline" id="stats-{pid}"></div>
      </div>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Visualizador Lv3 RF + ablación Lv3.")
    parser.add_argument("--tile", default="18HYD")
    parser.add_argument("--year", type=int, default=2010)
    parser.add_argument("--html", type=Path, default=_DEFAULT_HTML)
    parser.add_argument("--lc-year", type=int, default=None, help="Landcover year (default: same as --year)")
    parser.add_argument("--skip-layers", action="store_true")
    args = parser.parse_args()

    tile = args.tile.upper()
    year = str(args.year)
    html_path = args.html.resolve()
    html_dir = html_path.parent

    filas_rf, _, tile_rf, year_rf = cargar_lv3_rf(_LV3_RF_DIR)
    filas_abl, _, tile_abl, year_abl = cargar_ablacion_lv3(_ABL_LV3_DIR)
    if not filas_rf and not filas_abl:
        print("[ERROR] Sin CSV en lv3_rf ni ablacion_lv3")
        return 1
    tile = tile_rf or tile_abl or tile
    year = year_rf or year_abl or year
    lc_year = args.lc_year if args.lc_year is not None else int(year)

    mosaic_tiers: dict[str, str] = {}
    if not args.skip_layers:
        for out_dir, glob_pat in (
            (_LV3_RF_DIR, "seg_*_lv3_rf_*.tif"),
            (_ABL_LV3_DIR, "seg_abl_lv3_*.tif"),
        ):
            tiers = exportar_capas_generico(out_dir, _MOSAIC_184, tile, year, glob_pat)
            if tiers and not mosaic_tiers:
                mosaic_tiers = {k: sv.viz.ruta_publica(html_dir, out_dir / v) for k, v in tiers.items()}
    else:
        for out_dir in (_LV3_RF_DIR, _ABL_LV3_DIR):
            capas_dir = out_dir / CAPAS
            mosaic_tiers = sv.viz.descubrir_mosaic_tiers(html_dir, capas_dir, tile, year)
            if mosaic_tiers:
                break

    capas_rf = descubrir_capas(_LV3_RF_DIR, html_dir, tile, year, prefijo="seg_")
    capas_abl = descubrir_capas(_ABL_LV3_DIR, html_dir, tile, year, prefijo="seg_abl_lv3_")

    label_root = labeling_root(tile, year, lc_year)
    landcover_tiers = cargar_landcover_tiers(html_dir, label_root, tile, lc_year)

    lv3_rf = {
        "label": "Lv3 RF completo",
        "color": "#7c3aed",
        "filas": filas_rf,
        "capas_por_clave": capas_rf,
    }
    abl_lv3 = {
        "label": "Ablación Lv3",
        "color": "#b45309",
        "filas": filas_abl,
        "capas_por_clave": capas_abl,
    }
    merge_labeling({"lv3_rf": lv3_rf, "ablacion_lv3": abl_lv3}, html_dir, label_root)

    html = generar_html(tile, year, lc_year, lv3_rf, abl_lv3, mosaic_tiers, landcover_tiers)
    html_path.write_text(html, encoding="utf-8")
    print(f"[OK] Dashboard: {html_path}")
    print(f"[OK] Lv3 RF: {len(filas_rf)} combo(s), {len(capas_rf)} capa(s)")
    print(f"[OK] Etiquetas: {label_root} (Col2 {lc_year})")
    print(f"[OK] Ablación Lv3: {len(filas_abl)} corrida(s), {len(capas_abl)} capa(s)")
    print(f"[INFO] Servir: cd {html_dir} && python3 -m http.server 8765")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
