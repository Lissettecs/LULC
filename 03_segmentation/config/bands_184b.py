"""1-based rasterio band indices in SBAND-184B mosaics (standard HARM layout)."""

# SLIC input bands (order: red, nir, swir1)
SEGMENTATION_BANDS: list[tuple[str, int]] = [
    ("red", 128),    # red_median
    ("nir", 107),    # nir_median
    ("swir1", 164),  # swir1_median
]

# Per-segment spectral signature
SIGNATURE_BANDS: list[tuple[str, int]] = [
    ("blue", 3),     # blue_median
    ("green", 46),   # green_median
    ("red", 128),
    ("nir", 107),
    ("swir1", 164),
    ("swir2", 171),  # swir2_median
]

# Backward-compatible aliases (Spanish names used in earlier runs)
BANDAS_SEGMENTACION = SEGMENTATION_BANDS
BANDAS_FIRMA = SIGNATURE_BANDS
