"""Utilidades compartidas del pipeline v02."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def configurar_log(run_dir: Path, nombre: str = "pipeline") -> logging.Logger:
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(nombre)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    log_path = run_dir / f"log_{nombre}.txt"
    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


def resolver_run_dir(out_root: Path, run_tag: str | None, resume: bool) -> Path:
    if run_tag:
        base = out_root / run_tag
        if base.exists() and not resume:
            raise FileExistsError(
                f"El directorio de corrida ya existe: {base}. "
                "Use --resume o defina otro RUN_TAG."
            )
        base.mkdir(parents=True, exist_ok=resume)
        return base
    tag = datetime.now().strftime("%Y%m%d_%H%M")
    base = out_root / tag
    if base.exists() and not resume:
        i = 1
        while (out_root / f"{tag}_{i}").exists():
            i += 1
        base = out_root / f"{tag}_{i}"
        if base.exists():
            raise FileExistsError(f"No se pudo crear directorio único bajo {out_root}")
    base.mkdir(parents=True, exist_ok=resume)
    return base


def ultima_corrida(out_root: Path) -> Path | None:
    if not out_root.is_dir():
        return None
    dirs = sorted(
        [d for d in out_root.iterdir() if d.is_dir() and not d.name.startswith("_")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return dirs[0] if dirs else None


def git_hash() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "desconocido"


def versiones_paquetes() -> dict[str, str]:
    import numpy as np
    import pandas as pd
    import rasterio

    out = {
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "rasterio": rasterio.__version__,
    }
    try:
        import geopandas as gpd

        out["geopandas"] = gpd.__version__
    except ImportError:
        pass
    return out


def escribir_summary(run_dir: Path, data: dict, nombre: str = "summary.json") -> Path:
    path = run_dir / nombre
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def agregar_auditoria(run_dir: Path, fila: dict, nombre: str = "auditoria.csv") -> None:
    import pandas as pd

    path = run_dir / nombre
    df = pd.DataFrame([fila])
    if path.is_file():
        prev = pd.read_csv(path)
        df = pd.concat([prev, df], ignore_index=True)
    df.to_csv(path, index=False)


def corrida_caracterizacion_activa() -> Path | None:
    marca = REPO_ROOT / ".ultima_corrida_caract"
    if marca.is_file():
        p = Path(marca.read_text().strip())
        if p.is_dir():
            return p
    from config import params_caracterizacion as PC

    return ultima_corrida(PC.OUT_ROOT)


def unidad_completa(salida: Path, auditoria_path: Path, clave: str) -> bool:
    import pandas as pd

    if not auditoria_path.is_file():
        return salida.is_file()
    aud = pd.read_csv(auditoria_path)
    filas = aud[aud.get("unidad", pd.Series(dtype=str)).astype(str) == clave]
    if filas.empty:
        return salida.is_file()
    estado = str(filas.iloc[-1].get("estado", "ok"))
    if estado == "vacio":
        return True
    return salida.is_file() and estado == "ok"
