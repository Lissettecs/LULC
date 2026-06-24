"""
====================================================================
DIAGNÓSTICO DE PARCHES POR CLASE (RÁSTER) — base empírica para MMU
====================================================================
Para cada clase calcula la distribución de tamaños de parche
(componentes conexos) y compara conectividad 4 vs 8, sobre los
ráster ya generados.

AUTODETECTA la estructura de cada .tif:
  · multiclase   → la clase se lee del valor de píxel
  · 1 archivo/clase, valores {0, id} → usa ese id
  · 1 archivo/clase, binario {0, 1}  → la clase sale del NOMBRE del archivo
Imprime lo que interpretó por archivo para que lo verifiques.

Métrica que decide el MMU por clase:
  · pct_parches_<= Npx → cuánto del CONTEO es speckle
  · pct_area_en_<= Npx → cuánta ÁREA real representa
    (muchos parches + poca área → filtrar; mucha área → proteger)

Requisitos:  numpy, rasterio, scipy, pandas
====================================================================
"""

from pathlib import Path
import re
import numpy as np
import rasterio
from scipy import ndimage
import pandas as pd

# ── PARÁMETROS ──────────────────────────────────────────────────────
INPUT_DIR = Path(
    r"/home/lserey/mapbiomas_land/tmp/labels_pilot_ecoregion"
)
# Tabla de selección opcional (CSV o directorio con seleccion_*.csv) para join por ecorregión.
# Ejemplo: Path("/home/lserey/mapbiomas_land/prod/samples/final_samples")
SELECTION_TABLE = Path("/home/lserey/mapbiomas_land/prod/samples/final_samples")

NODATA = 0
PIXEL_SIZE_M = 30
SPECKLE_PX = 5
MIN_PARCHES_CONFIABLE = 200
# Tiles/años con menos rectángulos que este umbral se marcan como poca representación.
MIN_RECTANGULOS_COBERTURA = 3

OUT_CSV = INPUT_DIR / "distribucion_parches_por_clase.csv"
OUT_MISSING_CSV = INPUT_DIR / "clases_ausentes.csv"
OUT_COVERAGE_TILE_CSV = INPUT_DIR / "cobertura_por_tile_mgrs.csv"
OUT_COVERAGE_YEAR_CSV = INPUT_DIR / "cobertura_por_anio.csv"
OUT_COVERAGE_ECO_CSV = INPUT_DIR / "cobertura_por_ecorregion.csv"

# Leyenda MapBiomas Chile Colección 2 (id → nombre)
CLASS_NAMES = {
    1: "Formación boscosa",
    3: "Bosque",
    59: "Bosque Primario",
    60: "Bosque Secundario",
    67: "Bosque Achaparrado",
    10: "Formación natural no boscosa",
    11: "Humedal",
    12: "Pastizal",
    63: "Estepa",
    66: "Matorral",
    29: "Afloramiento Rocoso",
    14: "Agropecuaria y Silvicultura",
    9: "Silvicultura",
    18: "Agricultura",
    15: "Pastura",
    22: "Área sin vegetación",
    24: "Infraestructura",
    23: "Arena, Playa y Duna",
    61: "Salar",
    25: "Otra área sin vegetación",
    26: "Cuerpo de agua",
    33: "Río, lago u océano",
    34: "Hielo y nieve",
    27: "No observado",
}
# ────────────────────────────────────────────────────────────────────

PX_AREA_HA = (PIXEL_SIZE_M ** 2) / 10_000.0
STRUCT = {
    4: ndimage.generate_binary_structure(2, 1),
    8: ndimage.generate_binary_structure(2, 2),
}

RASTER_NAME_RE = re.compile(
    r"^(?P<mgrs>\d{2}[A-Z]{3})_(?P<modo>homogeneo|mixto)_(?P<size>\d+x\d)"
    r"_(?P<col>C\d{3})_(?P<row>R\d{3})_(?P<year>\d{4})(?:_(?:classes|labels))?$"
)


def class_from_name(stem: str):
    """Último grupo de dígitos del nombre; si no hay, el nombre completo."""
    m = re.findall(r"\d+", stem)
    return int(m[-1]) if m else stem


def parse_raster_metadata(path: Path) -> dict | None:
    """Extrae tile MGRS, modo, año y grid_id desde el nombre del archivo."""
    stem = path.stem
    if stem.endswith("_classes"):
        stem = stem[: -len("_classes")]
    elif stem.endswith("_labels"):
        stem = stem[: -len("_labels")]
    m = RASTER_NAME_RE.match(stem)
    if not m:
        return None
    d = m.groupdict()
    grid_id = f"{d['mgrs']}_{d['modo']}_{d['size']}_{d['col']}_{d['row']}"
    return {
        "archivo": path.name,
        "grid_id": grid_id,
        "tile_mgrs": d["mgrs"],
        "modo": d["modo"],
        "tamano": d["size"],
        "col": d["col"],
        "row": d["row"],
        "anio": int(d["year"]),
    }


def find_raster_files(input_dir: Path) -> list[Path]:
    """Busca rásters de clases; admite carpeta plana o estructura UTM/**/raster/classes/."""
    classes = sorted(input_dir.rglob("*_classes.tif"))
    if classes:
        return classes
    flat = sorted(input_dir.glob("*.tif")) + sorted(input_dir.glob("*.tiff"))
    return flat


def load_selection_table(path: Path | None) -> pd.DataFrame | None:
    """Carga seleccion_*.csv (uno o varios) para join por grid_id / ecorregión."""
    if path is None:
        return None
    path = Path(path)
    if not path.exists():
        print(f"  AVISO: SELECTION_TABLE no existe: {path}")
        return None

    frames: list[pd.DataFrame] = []
    if path.is_dir():
        csvs = sorted(
            p for p in path.rglob("seleccion_*.csv")
            if "taxonomia" not in p.name.lower()
        )
        if not csvs:
            print(f"  AVISO: no hay seleccion_*.csv en {path}")
            return None
        for csv_path in csvs:
            frames.append(pd.read_csv(csv_path, encoding="utf-8-sig"))
    else:
        frames.append(pd.read_csv(path, encoding="utf-8-sig"))

    sel = pd.concat(frames, ignore_index=True)
    sel["grid_id"] = sel["grid_id"].astype(str)
    eco_col = "eco_dom_name" if "eco_dom_name" in sel.columns else "eco_name"
    if eco_col not in sel.columns:
        print(f"  AVISO: la tabla de selección no tiene columna de ecorregión ({eco_col})")
        return sel[["grid_id"]].drop_duplicates()
    keep = ["grid_id", eco_col]
    if "utm_zone" in sel.columns:
        keep.append("utm_zone")
    return sel[keep].drop_duplicates("grid_id")


def iter_class_masks(path: Path):
    """Devuelve (clase, mask_bool, fuente) por archivo, autodetectando estructura."""
    with rasterio.open(path) as src:
        arr = src.read(1)
        nd = src.nodata if src.nodata is not None else NODATA
    uniq = [int(v) for v in np.unique(arr) if v != nd]
    if len(uniq) == 0:
        print(f"  {path.name}: vacío, omitido")
        return
    if len(uniq) == 1:
        val = uniq[0]
        if val == 1:
            cls = class_from_name(path.stem)
            print(f"  {path.name}: binario {{0,1}} → clase '{cls}' (del nombre)")
        else:
            cls = val
            print(f"  {path.name}: 1 clase, id={cls} (del valor)")
        yield cls, (arr == val), path.name
    else:
        print(f"  {path.name}: multiclase, {len(uniq)} clases {uniq}")
        for cls in uniq:
            yield cls, (arr == cls), path.name


def accumulate(files: list[Path]):
    """
    sizes: cls -> conn -> list[np.ndarray]
    file_rows: metadata + parches conn4 por archivo (para cobertura)
    """
    sizes: dict = {}
    file_rows: list[dict] = []

    for f in files:
        meta = parse_raster_metadata(f) or {"archivo": f.name, "grid_id": f.stem}
        n_patches_conn4 = 0
        n_classes = 0

        for cls, mask, _ in iter_class_masks(f):
            n_classes += 1
            for conn, struct in STRUCT.items():
                labeled, n = ndimage.label(mask, structure=struct)
                if n == 0:
                    continue
                comp = np.bincount(labeled.ravel())[1:]
                sizes.setdefault(cls, {}).setdefault(conn, []).append(comp)
                if conn == 4:
                    n_patches_conn4 += int(comp.size)

        file_rows.append(
            {
                **meta,
                "n_clases": n_classes,
                "n_parches_conn4": n_patches_conn4,
            }
        )

    return sizes, file_rows


def build_table(sizes: dict) -> pd.DataFrame:
    rows = []
    for cls, by_conn in sizes.items():
        for conn, chunks in sorted(by_conn.items()):
            s = np.concatenate(chunks)
            small = s <= SPECKLE_PX
            rows.append(
                {
                    "clase": cls,
                    "nombre": CLASS_NAMES.get(cls, ""),
                    "conect": conn,
                    "n_parches": int(s.size),
                    "ha_total": round(s.sum() * PX_AREA_HA, 2),
                    "px_p50": round(float(np.percentile(s, 50)), 1),
                    "px_p90": round(float(np.percentile(s, 90)), 1),
                    "px_max": int(s.max()),
                    "ha_p50": round(float(np.percentile(s, 50)) * PX_AREA_HA, 3),
                    f"pct_parches_<= {SPECKLE_PX}px": round(small.mean() * 100, 1),
                    f"pct_area_en_<= {SPECKLE_PX}px": round(s[small].sum() / s.sum() * 100, 1),
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    conn4_counts = df.loc[df["conect"] == 4].set_index("clase")["n_parches"]
    df["confiable"] = df["clase"].map(lambda c: bool(conn4_counts.get(c, 0) >= MIN_PARCHES_CONFIABLE))
    return df.sort_values(["clase", "conect"], key=lambda c: c.astype(str))


def report_missing_classes(sizes: dict) -> pd.DataFrame:
    found = {int(c) if str(c).isdigit() else c for c in sizes.keys()}
    found_ids = {c for c in found if isinstance(c, int)}
    legend_ids = set(CLASS_NAMES.keys())
    missing_ids = sorted(legend_ids - found_ids)
    rows = [{"clase": cid, "nombre": CLASS_NAMES[cid], "en_muestra": False} for cid in missing_ids]
    return pd.DataFrame(rows)


def build_coverage_tile(file_rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(file_rows)
    if df.empty or "tile_mgrs" not in df.columns:
        return pd.DataFrame()
    g = (
        df.groupby("tile_mgrs", as_index=False)
        .agg(
            n_rectangulos=("grid_id", "nunique"),
            n_parches_conn4=("n_parches_conn4", "sum"),
            n_clases_promedio=("n_clases", "mean"),
        )
        .sort_values("n_rectangulos")
    )
    g["n_clases_promedio"] = g["n_clases_promedio"].round(1)
    g["poca_representacion"] = g["n_rectangulos"] < MIN_RECTANGULOS_COBERTURA
    return g


def build_coverage_year(file_rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(file_rows)
    if df.empty or "anio" not in df.columns:
        return pd.DataFrame()
    g = (
        df.groupby("anio", as_index=False)
        .agg(
            n_rectangulos=("grid_id", "nunique"),
            n_parches_conn4=("n_parches_conn4", "sum"),
        )
        .sort_values("anio")
    )
    g["poca_representacion"] = g["n_rectangulos"] < MIN_RECTANGULOS_COBERTURA
    return g


def build_coverage_eco(file_rows: list[dict], selection: pd.DataFrame | None) -> pd.DataFrame | None:
    if selection is None:
        return None
    df = pd.DataFrame(file_rows)
    if df.empty or "grid_id" not in df.columns:
        return pd.DataFrame()
    eco_col = "eco_dom_name" if "eco_dom_name" in selection.columns else "eco_name"
    merged = df.merge(selection, on="grid_id", how="left")
    missing = merged[eco_col].isna().sum()
    if missing:
        print(f"  AVISO: {missing} rectángulos sin match en tabla de selección")
    g = (
        merged.groupby(eco_col, as_index=False)
        .agg(
            n_rectangulos=("grid_id", "nunique"),
            n_parches_conn4=("n_parches_conn4", "sum"),
        )
        .rename(columns={eco_col: "ecorregion"})
        .sort_values("n_rectangulos")
    )
    g["poca_representacion"] = g["n_rectangulos"] < MIN_RECTANGULOS_COBERTURA
    return g


def print_summary(
    df: pd.DataFrame,
    missing_df: pd.DataFrame,
    cov_tile: pd.DataFrame,
    cov_year: pd.DataFrame,
    cov_eco: pd.DataFrame | None,
    selection: pd.DataFrame | None,
):
    print("\n" + "=" * 70)
    print("RESUMEN DE CONFIABILIDAD Y COBERTURA")
    print("=" * 70)

    if df.empty:
        print("Sin datos de parches.")
        return

    no_conf = df[(df["conect"] == 4) & (~df["confiable"])]
    print(f"\n── Clases NO confiables (conect-4, n_parches < {MIN_PARCHES_CONFIABLE}) ──")
    if no_conf.empty:
        print("  (ninguna — todas las clases presentes superan el umbral)")
    else:
        for _, r in no_conf.iterrows():
            print(f"  · {r['clase']:>3} {r['nombre']:<35} n_parches={r['n_parches']}")

    print(f"\n── Clases ausentes en la muestra ({len(missing_df)} de {len(CLASS_NAMES)} en leyenda) ──")
    if missing_df.empty:
        print("  (todas las clases de la leyenda aparecen al menos una vez)")
    else:
        for _, r in missing_df.iterrows():
            print(f"  · {r['clase']:>3} {r['nombre']}")

    print(f"\n── Tiles MGRS con poca representación (< {MIN_RECTANGULOS_COBERTURA} rectángulos) ──")
    if cov_tile.empty:
        print("  (sin metadata de tile en nombres de archivo)")
    else:
        low = cov_tile[cov_tile["poca_representacion"]]
        if low.empty:
            print("  (ninguno)")
        else:
            print(low.to_string(index=False))

    print(f"\n── Años con poca representación (< {MIN_RECTANGULOS_COBERTURA} rectángulos) ──")
    if cov_year.empty:
        print("  (sin metadata de año en nombres de archivo)")
    else:
        low = cov_year[cov_year["poca_representacion"]]
        if low.empty:
            print("  (ninguno)")
        else:
            print(low.to_string(index=False))

    if selection is None:
        print("\n── Ecorregión ──")
        print("  Join no disponible: configure SELECTION_TABLE para desglosar por ecorregión.")
    elif cov_eco is not None:
        print(f"\n── Ecorregiones con poca representación (< {MIN_RECTANGULOS_COBERTURA} rectángulos) ──")
        low = cov_eco[cov_eco["poca_representacion"]]
        if low.empty:
            print("  (ninguna)")
        else:
            print(low.to_string(index=False))


def main():
    files = find_raster_files(INPUT_DIR)
    if not files:
        raise FileNotFoundError(f"No hay .tif en {INPUT_DIR} (probado plano y **/*_classes.tif)")

    print(f"Directorio: {INPUT_DIR}")
    print(f"Archivos encontrados: {len(files)}")
    print(f"Umbral confiable: n_parches (conect-4) >= {MIN_PARCHES_CONFIABLE}")

    selection = load_selection_table(SELECTION_TABLE)

    print("\n── Autodetección por archivo ──")
    sizes, file_rows = accumulate(files)

    df = build_table(sizes)
    missing_df = report_missing_classes(sizes)
    cov_tile = build_coverage_tile(file_rows)
    cov_year = build_coverage_year(file_rows)
    cov_eco = build_coverage_eco(file_rows, selection)

    pd.set_option("display.width", 170)
    print("\n── DISTRIBUCIÓN DE TAMAÑOS POR CLASE (conect 4 vs 8) ──")
    print(df.to_string(index=False))

    df.to_csv(OUT_CSV, index=False)
    print(f"\nGuardado: {OUT_CSV}")

    missing_df.to_csv(OUT_MISSING_CSV, index=False)
    print(f"Guardado: {OUT_MISSING_CSV}")

    if not cov_tile.empty:
        cov_tile.to_csv(OUT_COVERAGE_TILE_CSV, index=False)
        print(f"Guardado: {OUT_COVERAGE_TILE_CSV}")
    if not cov_year.empty:
        cov_year.to_csv(OUT_COVERAGE_YEAR_CSV, index=False)
        print(f"Guardado: {OUT_COVERAGE_YEAR_CSV}")
    if cov_eco is not None and not cov_eco.empty:
        cov_eco.to_csv(OUT_COVERAGE_ECO_CSV, index=False)
        print(f"Guardado: {OUT_COVERAGE_ECO_CSV}")

    print_summary(df, missing_df, cov_tile, cov_year, cov_eco, selection)

    print("\n── Cómo leerlo ──")
    print(f"  · confiable=True → al menos {MIN_PARCHES_CONFIABLE} parches conect-4; "
          f"umbrales MMU más fiables.")
    print(f"  · pct_area_en_<= {SPECKLE_PX}px ALTO → clase pequeña por naturaleza "
          f"(vega/bofedal, laguna): MMU bajo o cero.")
    print(f"  · pct_area_en_<= {SPECKLE_PX}px BAJO + muchos parches → speckle: MMU estándar.")
    print("  · conect=4 refleja parches reales (rook); conect=8 muestra cuánto se fusionaría.")


if __name__ == "__main__":
    main()
