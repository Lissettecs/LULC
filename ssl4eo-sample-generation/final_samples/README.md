# SSL4EO final samples — 2×2 / 3×3 rectangles (scale300)

**330 samples** (138 UTM18 + 192 UTM19), with zero geometric overlap within each zone and at the UTM18/UTM19 border.

| File | Use |
|------|-----|
| `seleccion_grilla_ssl4eo_muestras_UTM18_scale300.geojson` | Map / GIS UTM18 |
| `seleccion_grilla_ssl4eo_muestras_UTM19_scale300.geojson` | Map / GIS UTM19 |
| `seleccion_grilla_ssl4eo_muestras_UTM*_scale300.gpkg` | GeoPackage (layer `seleccion`) |
| `seleccion_grilla_ssl4eo_muestras_UTM*_scale300.csv` | Attribute table |
| `seleccion_grilla_ssl4eo_muestras_UTM*_scale300_taxonomia_n3.csv` | Table + N3 taxonomy (recommended) |
| `reservas_grilla_ssl4eo_muestras_UTM19_scale300.csv` | Reserves E3/E6 (not part of the 330) |

Generated with `scripts/03_rectangle_selection.py` + `scripts/04_annotate_grid_taxonomy.py`.
