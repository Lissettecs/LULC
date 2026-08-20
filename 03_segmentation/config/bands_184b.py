"""Índices rasterio 1-based de bandas en mosaicos SBAND-184B (layout HARM estándar)."""

# Bandas de entrada a SLIC (orden: red, nir, swir1)
SEGMENTATION_BANDS: list[tuple[str, int]] = [
    ("red", 128),    # red_median
    ("nir", 107),    # nir_median
    ("swir1", 164),  # swir1_median
]

# Firma espectral por segmento
SIGNATURE_BANDS: list[tuple[str, int]] = [
    ("blue", 3),     # blue_median
    ("green", 46),   # green_median
    ("red", 128),
    ("nir", 107),
    ("swir1", 164),
    ("swir2", 171),  # swir2_median
]

# Aliases compatibles (nombres en español usados en corridas anteriores)
BANDAS_SEGMENTACION = SEGMENTATION_BANDS
BANDAS_FIRMA = SIGNATURE_BANDS
