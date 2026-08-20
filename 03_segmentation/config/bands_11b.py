"""Índices rasterio 1-based de bandas en mosaicos CIM 11B (medians + índices)."""

# Bandas de entrada a SLIC (orden: red, nir, swir1)
SEGMENTATION_BANDS: list[tuple[str, int]] = [
    ("red", 3),     # red_median
    ("nir", 4),     # nir_median
    ("swir1", 5),   # swir1_median
]

# Firma espectral por segmento
SIGNATURE_BANDS: list[tuple[str, int]] = [
    ("blue", 1),    # blue_median
    ("green", 2),   # green_median
    ("red", 3),
    ("nir", 4),
    ("swir1", 5),
    ("swir2", 6),   # swir2_median
]

BANDAS_SEGMENTACION = SEGMENTATION_BANDS
BANDAS_FIRMA = SIGNATURE_BANDS
