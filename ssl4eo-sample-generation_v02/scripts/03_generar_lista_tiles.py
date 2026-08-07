#!/usr/bin/env python3
"""03 — Genera tiles.txt y abre directorio de corrida de caracterización."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from caracterizacion.grilla import cargar_tiles_mgrs
from config import params_caracterizacion as P
from utilidades import REPO_ROOT, configurar_log, resolver_run_dir


def main() -> int:
    resume = P.RESUME
    run_dir = resolver_run_dir(P.OUT_ROOT, P.RUN_TAG or None, resume)
    logger = configurar_log(run_dir, "caracterizacion")

    gdf = cargar_tiles_mgrs(P.HUSOS)
    tiles = sorted(gdf["tile_name"].tolist())
    (run_dir / "tiles.txt").write_text("\n".join(tiles) + "\n", encoding="utf-8")
    (REPO_ROOT / "tiles.txt").write_text("\n".join(tiles) + "\n", encoding="utf-8")
    (REPO_ROOT / ".ultima_corrida_caract").write_text(str(run_dir), encoding="utf-8")

    logger.info(
        "Lista de tiles: %s (%d tiles, husos %s)",
        run_dir / "tiles.txt",
        len(tiles),
        P.HUSOS,
    )
    print(len(tiles))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
