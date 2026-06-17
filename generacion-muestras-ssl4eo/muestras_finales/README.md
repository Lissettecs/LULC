# Muestras finales SSL4EO — rectángulos 2×2 / 3×3 (scale300)

**330 muestras** (138 UTM18 + 192 UTM19), sin solape geométrico intra-huso ni en la frontera UTM18/UTM19.

| Archivo | Uso |
|---------|-----|
| `seleccion_grilla_ssl4eo_muestras_UTM18_scale300.geojson` | Mapa / GIS UTM18 |
| `seleccion_grilla_ssl4eo_muestras_UTM19_scale300.geojson` | Mapa / GIS UTM19 |
| `seleccion_grilla_ssl4eo_muestras_UTM*_scale300.gpkg` | GeoPackage (capa `seleccion`) |
| `seleccion_grilla_ssl4eo_muestras_UTM*_scale300.csv` | Tabla atributos |
| `seleccion_grilla_ssl4eo_muestras_UTM*_scale300_taxonomia_n3.csv` | Tabla + taxonomía N3 (recomendado) |
| `reservas_grilla_ssl4eo_muestras_UTM19_scale300.csv` | Suplentes E3/E6 (no entran en las 330) |

Generados con `scripts/03_seleccion_rectangulos.py` + `scripts/04_anotar_taxonomia_grillas.py`.
