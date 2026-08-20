"""Carga y filtrado de rectángulos desde el plan de revisión (CIM / rev_year*)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import pandas as pd

from config.paths import masked_mosaic_path, summary_path
from config.run_refs import GPKG_SELECCION, GPKG_UTM18, GPKG_UTM19

# Prefijos de tile: MGRS (18GXA) o carta CIM (SI-19-Y-A)
TILE_MGRS = re.compile(r"^(\d{2}[A-Z]{3})")
TILE_CIM = re.compile(r"^([A-Z]{2}-\d{2}-[A-Z]-[A-Z])")

COLUMNAS_REV_YEAR = ["rev_year1", "rev_year2", "rev_year3"]
COLUMNAS_REV_ROLE = ["rev_role1", "rev_role2", "rev_role3"]


def tile_desde_grid_id(grid_id: str) -> str:
    """Infiere el prefijo de tile desde ``grid_id``."""
    m = TILE_CIM.match(grid_id) or TILE_MGRS.match(grid_id)
    if not m:
        raise ValueError(f"No se puede inferir tile desde grid_id={grid_id!r}")
    return m.group(1)


def tile_desde_fila(row: pd.Series) -> str:
    """Obtiene el tile desde columnas mgrs_dom/cim_name o desde grid_id."""
    for col in ("mgrs_dom", "cim_name"):
        if col in row.index and pd.notna(row[col]):
            return str(row[col]).upper()
    return tile_desde_grid_id(str(row["grid_id"]))


def utm_epsg_desde_fila(row: pd.Series) -> int:
    """EPSG UTM sur (327xx) desde utm_zone o longitud del centroide."""
    if "utm_zone" in row.index and pd.notna(row["utm_zone"]):
        zona = int(row["utm_zone"])
        return 32700 + zona
    geom = row.geometry
    lon = float(geom.centroid.x)
    zona = int((lon + 180) // 6) + 1
    return 32700 + zona


@dataclass
class PlanRectangulo:
    """Un rectángulo del plan de segmentación (contrato de campos en inglés)."""

    grid_id: str
    tile: str
    rev_year: int
    rev_slot: int
    rev_role: str
    source_gpkg: str
    mosaic_path: str | None = None
    mosaic_ok: bool = False
    already_processed: bool = False
    summary_path: str | None = None
    omitido: str | None = None
    error: str | None = None
    # Compatibilidad con código que lee rev_year1
    rev_year1: int | None = None
    rev_role1: str | None = None
    slots_extra: list[dict] | None = None

    def __post_init__(self) -> None:
        if self.rev_year1 is None:
            self.rev_year1 = self.rev_year
        if self.rev_role1 is None:
            self.rev_role1 = self.rev_role

    def to_dict(self) -> dict:
        return {
            "grid_id": self.grid_id,
            "tile": self.tile,
            "rev_year": self.rev_year,
            "rev_slot": self.rev_slot,
            "rev_role": self.rev_role,
            "rev_year1": self.rev_year1,
            "rev_role1": self.rev_role1,
            "source_gpkg": self.source_gpkg,
            "mosaic_path": self.mosaic_path,
            "mosaic_ok": self.mosaic_ok,
            "already_processed": self.already_processed,
            "summary_path": self.summary_path,
            "omitido": self.omitido,
            "error": self.error,
            "slots_extra": self.slots_extra,
        }


@dataclass
class PlanSegmentacion:
    """Plan completo de segmentación para un ``rev_year`` / año de mosaico."""

    rev_year: int
    year: int
    mosaic_root: str
    output_dir: str
    rects: list[PlanRectangulo] = field(default_factory=list)
    source_gpkg: str | None = None

    @property
    def ready(self) -> list[PlanRectangulo]:
        return [
            r
            for r in self.rects
            if r.mosaic_ok and not r.already_processed and not r.error and not r.omitido
        ]

    @property
    def missing_mosaic(self) -> list[PlanRectangulo]:
        return [r for r in self.rects if not r.mosaic_ok]

    @property
    def already_done(self) -> list[PlanRectangulo]:
        return [r for r in self.rects if r.already_processed]

    def summary(self) -> dict:
        return {
            "rev_year": self.rev_year,
            "year": self.year,
            "mosaic_root": self.mosaic_root,
            "output_dir": self.output_dir,
            "source_gpkg": self.source_gpkg,
            "n_total": len(self.rects),
            "n_mosaic_ok": sum(1 for r in self.rects if r.mosaic_ok),
            "n_ready": len(self.ready),
            "n_already_processed": len(self.already_done),
            "n_missing_mosaic": len(self.missing_mosaic),
            "n_omitidos": sum(1 for r in self.rects if r.omitido),
            "tiles_missing_mosaic": sorted({r.tile for r in self.missing_mosaic}),
            "rects": [r.to_dict() for r in self.rects],
        }


# Aliases públicos en inglés (compatibilidad)
RectPlan = PlanRectangulo
SegmentationPlan = PlanSegmentacion
tile_from_grid_id = tile_desde_grid_id
tile_from_row = tile_desde_fila


def _anio_valido(valor) -> int | None:
    if pd.isna(valor):
        return None
    try:
        y = int(valor)
    except (TypeError, ValueError):
        return None
    if y <= 0 or y == -9999:
        return None
    return y


def cargar_plan_multianual(ruta_gpkg: Path) -> gpd.GeoDataFrame:
    """
    Melt de rev_year1/2/3 (+ roles) a formato largo y dedupe por (grid_id, rev_year).

    Conserva la lista de slots en ``_slots``; el slot primario es el de menor índice.
    """
    if not ruta_gpkg.is_file():
        raise FileNotFoundError(ruta_gpkg)
    gdf = gpd.read_file(ruta_gpkg)
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        raise ValueError(f"Se espera EPSG:4326 en {ruta_gpkg}, crs={gdf.crs}")

    filas: list[dict] = []
    for _, row in gdf.iterrows():
        slots: list[dict] = []
        for slot, yc, rc in zip(
            range(1, 4), COLUMNAS_REV_YEAR, COLUMNAS_REV_ROLE, strict=True
        ):
            if yc not in gdf.columns:
                raise KeyError(f"Falta columna {yc} en {ruta_gpkg}")
            anio = _anio_valido(row[yc])
            if anio is None:
                continue
            rol = ""
            if rc in gdf.columns and pd.notna(row[rc]):
                rol = str(row[rc])
            slots.append({"rev_slot": slot, "rev_year": anio, "rev_role": rol})

        # Agrupar por año
        por_anio: dict[int, list[dict]] = {}
        for s in slots:
            por_anio.setdefault(s["rev_year"], []).append(s)

        for anio, lista in por_anio.items():
            lista = sorted(lista, key=lambda x: x["rev_slot"])
            primario = lista[0]
            rec = row.to_dict()
            rec["rev_year"] = anio
            rec["rev_slot"] = primario["rev_slot"]
            rec["rev_role"] = primario["rev_role"]
            rec["rev_year1"] = anio  # compat
            rec["rev_role1"] = primario["rev_role"]
            rec["_slots"] = lista
            filas.append(rec)

    if not filas:
        raise ValueError(f"Sin slots de revisión válidos en {ruta_gpkg}")

    out = gpd.GeoDataFrame(filas, geometry="geometry", crs=gdf.crs)
    out["_tile"] = out.apply(tile_desde_fila, axis=1)
    out["_utm_epsg"] = out.apply(utm_epsg_desde_fila, axis=1)
    out["_source_gpkg"] = ruta_gpkg.name
    if "rect_id" not in out.columns:
        out["rect_id"] = out["grid_id"]
    if "utm_epsg" not in out.columns:
        out["utm_epsg"] = out["_utm_epsg"].map(lambda e: f"EPSG:{e}")
    return out


def cargar_gpkg_seleccion(
    gpkg_utm18: Path = GPKG_UTM18,
    gpkg_utm19: Path = GPKG_UTM19,
    rev_year: int = 2015,
    test_tile: str | None = None,
    grid_id: str | None = None,
    gpkg_seleccion: Path | None = None,
) -> list[gpd.GeoDataFrame]:
    """
    Carga selección. Preferencia: GPKG nacional único; fallback a utm18/utm19.
    """
    rutas: list[Path] = []
    principal = gpkg_seleccion or GPKG_SELECCION
    if principal.is_file():
        rutas = [principal]
    else:
        for path in (gpkg_utm18, gpkg_utm19):
            if path.is_file() and path not in rutas:
                rutas.append(path)

    if not rutas:
        raise FileNotFoundError("No hay GPKG de selección disponible")

    vistos: set[str] = set()
    out: list[gpd.GeoDataFrame] = []
    for path in rutas:
        key = str(path.resolve())
        if key in vistos:
            continue
        vistos.add(key)
        plan = cargar_plan_multianual(path)
        plan = plan[plan["rev_year"] == rev_year].copy()
        if test_tile:
            plan = plan[plan["_tile"] == test_tile.upper()].copy()
        if grid_id:
            plan = plan[plan["grid_id"] == grid_id].copy()
        if not plan.empty:
            out.append(plan)

    if not out:
        raise ValueError("No hay rectángulos tras filtrar rev_year / tile / grid_id")
    return out


def construir_plan(
    *,
    rev_year: int,
    year: int,
    mosaic_root_dir: Path,
    output_root: Path,
    gpkg_utm18: Path = GPKG_UTM18,
    gpkg_utm19: Path = GPKG_UTM19,
    test_tile: str | None = None,
    grid_id: str | None = None,
    gpkg_seleccion: Path | None = None,
    anios_permitidos: list[int] | None = None,
) -> PlanSegmentacion:
    """Construye el plan de segmentación (mosaicos y estado de procesamiento)."""
    plan = PlanSegmentacion(
        rev_year=rev_year,
        year=year,
        mosaic_root=str(mosaic_root_dir),
        output_dir=str(output_root),
        source_gpkg=str(gpkg_seleccion or GPKG_SELECCION),
    )
    for gdf in cargar_gpkg_seleccion(
        gpkg_utm18,
        gpkg_utm19,
        rev_year,
        test_tile,
        grid_id,
        gpkg_seleccion=gpkg_seleccion,
    ):
        for _, row in gdf.iterrows():
            gid = str(row["grid_id"])
            tile = str(row["_tile"])
            anio = int(row["rev_year"])
            mosaic = masked_mosaic_path(mosaic_root_dir, tile, year)
            summ = summary_path(output_root, tile, gid, year=year)
            omitido = None
            if anios_permitidos is not None and anio not in anios_permitidos:
                omitido = "anio_no_permitido"
            mosaic_ok = mosaic is not None and mosaic.is_file()
            if not mosaic_ok and omitido is None:
                omitido = "mosaico_ausente"
            item = PlanRectangulo(
                grid_id=gid,
                tile=tile,
                rev_year=anio,
                rev_slot=int(row["rev_slot"]),
                rev_role=str(row.get("rev_role", "")),
                source_gpkg=str(row["_source_gpkg"]),
                mosaic_path=str(mosaic) if mosaic else None,
                mosaic_ok=mosaic_ok,
                already_processed=summ.is_file(),
                summary_path=str(summ) if summ.is_file() else None,
                omitido=omitido,
                slots_extra=list(row.get("_slots") or []),
            )
            if year != rev_year:
                item.error = f"year ({year}) != rev_year ({rev_year})"
            plan.rects.append(item)

    plan.rects.sort(key=lambda r: (r.tile, r.grid_id))
    return plan


def filtrar_plan(
    plan: PlanSegmentacion,
    *,
    require_mosaic: bool = False,
    skip_existing: bool = False,
) -> list[PlanRectangulo]:
    """Rectángulos listos para procesar (mosaico OK, sin error duro)."""
    rects = [r for r in plan.rects if not r.error and r.omitido != "anio_no_permitido"]
    if require_mosaic:
        rects = [r for r in rects if r.mosaic_ok]
    else:
        # Sin require_mosaic aún así no intentamos segmentar sin archivo
        rects = [r for r in rects if r.mosaic_ok]
    if skip_existing:
        rects = [r for r in rects if not r.already_processed]
    return rects


def iterar_filas_plan(
    plan: PlanSegmentacion,
    gpkg_seleccion: Path | None = None,
) -> list[gpd.GeoDataFrame]:
    """Reconstruye GeoDataFrames para los rectángulos del plan."""
    if not plan.rects:
        return []
    ids = {r.grid_id for r in plan.rects}
    gdfs = cargar_gpkg_seleccion(
        rev_year=plan.rev_year,
        gpkg_seleccion=gpkg_seleccion or GPKG_SELECCION,
    )
    out: list[gpd.GeoDataFrame] = []
    for gdf in gdfs:
        sub = gdf[gdf["grid_id"].isin(ids)].copy()
        if not sub.empty:
            out.append(sub)
    return out


def guardar_plan(plan: PlanSegmentacion, path: Path) -> None:
    """Escribe el resumen del plan como JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.summary(), indent=2, ensure_ascii=False), encoding="utf-8")


# Aliases públicos en inglés
load_selection_gpkg = cargar_gpkg_seleccion
build_plan = construir_plan
filter_plan = filtrar_plan
iter_plan_rows = iterar_filas_plan
save_plan = guardar_plan
