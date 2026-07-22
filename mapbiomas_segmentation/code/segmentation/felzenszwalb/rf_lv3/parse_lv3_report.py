"""Parser de bandas seleccionadas desde REPORT markdown (Lv3 multitile)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BandEntry:
    index: int
    name: str


TILE_HEADER_RE = re.compile(r"^###\s+(\w+)\s+\((\d+)\s+bands?\)\s*$")
TABLE_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|")


class ReportParseError(ValueError):
    """Error de parseo del REPORT .md."""


def parse_lv3_report_md(ruta: Path) -> dict[str, list[BandEntry]]:
    """
    Extrae bandas por tile desde la sección «2.1 Selected bands per tile».

    Devuelve {TILE: [BandEntry(index, name), ...]} ordenado como en el .md.
    """
    if not ruta.is_file():
        raise ReportParseError(f"REPORT no encontrado: {ruta}")

    texto = ruta.read_text(encoding="utf-8")
    marcador = "## 2.1 Selected bands per tile"
    if marcador not in texto:
        raise ReportParseError(
            f"No se encontró '{marcador}' en {ruta.name}. "
            "Revisar formato del REPORT o indicar otra fuente."
        )

    inicio = texto.index(marcador)
    fin = texto.find("\n## 3.", inicio)
    bloque = texto[inicio:fin] if fin != -1 else texto[inicio:]

    por_tile: dict[str, list[BandEntry]] = {}
    tile_actual: str | None = None
    esperadas: int | None = None
    en_tabla = False

    for linea in bloque.splitlines():
        m_hdr = TILE_HEADER_RE.match(linea.strip())
        if m_hdr:
            tile_actual = m_hdr.group(1).upper()
            esperadas = int(m_hdr.group(2))
            por_tile[tile_actual] = []
            en_tabla = False
            continue

        if tile_actual is None:
            continue

        celda = linea.strip()
        if celda == "| Index | Name |":
            en_tabla = True
            continue
        if en_tabla and celda.startswith("|---"):
            continue
        if en_tabla:
            m_fila = TABLE_ROW_RE.match(celda)
            if m_fila:
                por_tile[tile_actual].append(
                    BandEntry(index=int(m_fila.group(1)), name=m_fila.group(2).strip())
                )
            elif celda and not celda.startswith("|"):
                en_tabla = False

    if not por_tile:
        raise ReportParseError(
            f"Sección 2.1 presente pero sin subsecciones '### TILE (N bands)' en {ruta.name}"
        )

    problemas: list[str] = []
    for tile, entradas in por_tile.items():
        nombres = [e.name for e in entradas]
        if len(nombres) != len(set(nombres)):
            dup = sorted({n for n in nombres if nombres.count(n) > 1})
            problemas.append(f"{tile}: nombres duplicados {dup}")
        # Re-leer esperadas del header (no guardadas por tile en dict aux)
        hdr_match = re.search(rf"^###\s+{tile}\s+\((\d+)\s+bands?\)", bloque, re.MULTILINE)
        n_esperado = int(hdr_match.group(1)) if hdr_match else -1
        if n_esperado >= 0 and len(entradas) != n_esperado:
            problemas.append(
                f"{tile}: encabezado dice {n_esperado} bandas, tabla tiene {len(entradas)}"
            )

    if problemas:
        raise ReportParseError("Parseo ambiguo/incompleto:\n  - " + "\n  - ".join(problemas))

    return por_tile


def bandas_para_tile(ruta: Path, tile: str) -> list[BandEntry]:
    tile = tile.upper()
    por_tile = parse_lv3_report_md(ruta)
    if tile not in por_tile:
        disponibles = ", ".join(sorted(por_tile))
        raise ReportParseError(f"Tile '{tile}' no está en el REPORT. Disponibles: {disponibles}")
    return por_tile[tile]


def imprimir_bandas_tile(entradas: list[BandEntry], tile: str, origen: Path) -> None:
    print(f"\n=== Bandas REPORT Lv3 — tile {tile} ===")
    print(f"Origen: {origen}")
    print(f"Total: {len(entradas)} bandas\n")
    print(f"{'#':>4}  {'índice':>6}  nombre")
    print("-" * 40)
    for i, e in enumerate(entradas, start=1):
        print(f"{i:>4}  {e.index:>6}  {e.name}")
