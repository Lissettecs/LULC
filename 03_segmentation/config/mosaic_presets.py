"""Presets de mosaico y bandas para la etapa 03."""

from __future__ import annotations

import os
from pathlib import Path

from config.paths import MAPBIOMAS_ROOT, mosaic_root as mosaic_root_184_mask


# Claves estables usadas en CLI / env MOSAIC_KIND
MOSAIC_KIND_184_MASK = "184_mask_water"
MOSAIC_KIND_11B = "11b"
MOSAIC_KINDS = (MOSAIC_KIND_184_MASK, MOSAIC_KIND_11B)

BAND_LAYOUT_184 = "184"
BAND_LAYOUT_11B = "11b"
BAND_LAYOUTS = (BAND_LAYOUT_184, BAND_LAYOUT_11B, "auto")


def mosaic_root_11b() -> Path:
    """Raíz de mosaicos CIM 11B enmascarados (agua/glaciar)."""
    env = os.environ.get("MOSAIC_11B_ROOT")
    if env:
        return Path(env).resolve()
    return (MAPBIOMAS_ROOT / "mosaic_11bands_mask_water").resolve()


def resolve_mosaic_kind(kind: str | None = None) -> str:
    raw = (kind or os.environ.get("MOSAIC_KIND") or MOSAIC_KIND_184_MASK).strip().lower()
    aliases = {
        "184": MOSAIC_KIND_184_MASK,
        "184masked": MOSAIC_KIND_184_MASK,
        "184_mask": MOSAIC_KIND_184_MASK,
        "184_mask_water": MOSAIC_KIND_184_MASK,
        "mask_water": MOSAIC_KIND_184_MASK,
        "11": MOSAIC_KIND_11B,
        "11b": MOSAIC_KIND_11B,
        "11bands": MOSAIC_KIND_11B,
        "mosaic_11bands": MOSAIC_KIND_11B,
        "11b_mask": MOSAIC_KIND_11B,
        "11b_mask_water": MOSAIC_KIND_11B,
        "mosaic_11bands_mask_water": MOSAIC_KIND_11B,
    }
    out = aliases.get(raw, raw)
    if out not in (MOSAIC_KIND_184_MASK, MOSAIC_KIND_11B):
        raise ValueError(
            f"MOSAIC_KIND inválido: {kind!r}. Use {MOSAIC_KIND_184_MASK} o {MOSAIC_KIND_11B}."
        )
    return out


def mosaic_root_for_kind(kind: str, year: int) -> Path:
    """Raíz de mosaicos según preset."""
    k = resolve_mosaic_kind(kind)
    if k == MOSAIC_KIND_11B:
        return mosaic_root_11b()
    return mosaic_root_184_mask(year)


def resolve_mosaic_root(
    *,
    mosaic_root: Path | None = None,
    mosaic_kind: str | None = None,
    year: int,
) -> tuple[Path, str]:
    """
    Resuelve (mosaic_root, kind_efectivo).

    Prioridad: --mosaic-root / MOSAIC_ROOT > --mosaic-kind / MOSAIC_KIND > default 184.
    """
    env_root = os.environ.get("MOSAIC_ROOT")
    if mosaic_root is not None:
        root = Path(mosaic_root).resolve()
        kind = resolve_mosaic_kind(mosaic_kind) if mosaic_kind else _infer_kind_from_root(root)
        return root, kind
    if env_root:
        root = Path(env_root).resolve()
        kind = resolve_mosaic_kind(mosaic_kind) if mosaic_kind else _infer_kind_from_root(root)
        return root, kind
    kind = resolve_mosaic_kind(mosaic_kind)
    return mosaic_root_for_kind(kind, year), kind


def _infer_kind_from_root(root: Path) -> str:
    s = str(root).lower()
    if "11band" in s or "11b" in s:
        return MOSAIC_KIND_11B
    return MOSAIC_KIND_184_MASK


def resolve_band_layout(
    *,
    band_layout: str | None = None,
    mosaic_kind: str,
    mosaic_path: Path | None = None,
) -> str:
    """Devuelve '184' o '11b'."""
    raw = (band_layout or os.environ.get("BAND_LAYOUT") or "auto").strip().lower()
    if raw in ("184", "184b"):
        return BAND_LAYOUT_184
    if raw in ("11", "11b", "11bands"):
        return BAND_LAYOUT_11B
    if raw != "auto":
        raise ValueError(f"BAND_LAYOUT inválido: {band_layout!r}")
    if mosaic_path is not None and "11B" in mosaic_path.name:
        return BAND_LAYOUT_11B
    if mosaic_kind == MOSAIC_KIND_11B:
        return BAND_LAYOUT_11B
    return BAND_LAYOUT_184


def cargar_bandas_layout(layout: str) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """Bandas SLIC + firma según layout."""
    if layout == BAND_LAYOUT_11B:
        from config.bands_11b import SEGMENTATION_BANDS, SIGNATURE_BANDS
    else:
        from config.bands_184b import SEGMENTATION_BANDS, SIGNATURE_BANDS
    return list(SEGMENTATION_BANDS), list(SIGNATURE_BANDS)


def resolve_features_parquet(
    *,
    features_parquet: bool | None = None,
    no_features_parquet: bool = False,
    mosaic_kind: str | None = None,
) -> bool:
    """
    ¿Generar features.parquet?

    Prioridad: flags CLI > env FEATURES_PARQUET > política por mosaic_kind.

    Política:
      - mosaic_kind 11b / 11b_mask_water → default **False** (parquet pendiente)
      - 184_mask_water → default **True**
    """
    if no_features_parquet:
        return False
    if features_parquet is True:
        return True
    if features_parquet is False:
        return False
    env = os.environ.get("FEATURES_PARQUET")
    if env is not None and env.strip() != "":
        v = env.strip().lower()
        if v in ("0", "false", "no", "off"):
            return False
        if v in ("1", "true", "yes", "on"):
            return True
        raise ValueError(f"FEATURES_PARQUET inválido: {env!r} (use 0/1)")
    kind = resolve_mosaic_kind(mosaic_kind) if mosaic_kind else resolve_mosaic_kind(None)
    if kind == MOSAIC_KIND_11B:
        return False
    return True


def resolve_anios_permitidos(
    *,
    mosaic_kind: str,
    allowed_years: list[int] | None = None,
) -> list[int] | None:
    """
    None = todos los años del plan.
    Env ANIOS_PERMITIDOS=2015,2009 o 'all'.
    """
    if allowed_years is not None:
        return allowed_years
    env = os.environ.get("ANIOS_PERMITIDOS")
    if env is not None:
        raw = env.strip().lower()
        if raw in ("", "all", "*", "none"):
            return None
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    # 11B: permitir todos; 184 masked histórico: default 2015 si no se redefine
    if mosaic_kind == MOSAIC_KIND_11B:
        return None
    env_default = os.environ.get("ANIOS_PERMITIDOS_DEFAULT")
    if env_default is not None:
        if env_default.strip().lower() in ("all", "*", "none", ""):
            return None
        return [int(x.strip()) for x in env_default.split(",") if x.strip()]
    return [2015]
