# Labeling — etiquetado C2 por segmento

Asigna estadísticas de **MapBiomas Collection 2** a cada segmento producido por
`LULC/segmentacion` (SLIC + RAG p10).

## Estadísticas por segmento

| Campo | Descripción |
|-------|-------------|
| `clase_moda` | Clase mayoritaria C2 en el segmento |
| `pureza` | % de píxeles de esa clase (sobre píxeles C2 válidos) |
| `clase_2` / `pureza_2` | Segunda clase y su % — distingue `95/2/1` de `51/48/1` |
| `n_clases` | Número de clases C2 distintas en el segmento |
| `area_px` | Píxeles del segmento (para filtrar por tamaño) |
| `tiene_protegida` | True si hay ≥1 píxel de clase del tier protegido (aunque no sea moda) |
| `distribucion_top3` | Cadena tipo `95/2/1` (moda / 2ª / resto) |

**Tier protegido:** 3, 11, 23, 24, 33, 34, 61, 67 (`config/clases_c2.py`).

**Nodata C2:** 0, 27 (excluidos del cálculo de pureza).

## Entrada / salida

| | Ruta |
|---|------|
| Segmentación | `/home/lserey/mapbiomas_land/prod/segmentacion_slic_rev2015/` |
| Landcover | `ancillary_data/landcover_col2/classification_{year}.tif` |
| Salida | `/home/lserey/mapbiomas_land/prod/labeling_slic_rev2015/` |

Por rectángulo:

- `{grid_id}_labeled_segments.gpkg` — geometría + espectral (si existía) + C2
- `{grid_id}_labeled_segments.csv` — tabla de atributos
- `{grid_id}_labeling_summary.json`

## Uso

```bash
cd /home/lserey/repositorio/LULC/labeling
/home/lserey/.conda/envs/mb_coverage/bin/python etiquetar_segmentos_c2.py \
  --prueba-tile 18GXA --force
```

Todos los rects segmentados:

```bash
python etiquetar_segmentos_c2.py --year 2015 --force
```

Un rectángulo:

```bash
python etiquetar_segmentos_c2.py --grid-id 18GXA_3x3_c003_r003 --force
```

## Visualizador (pureza mínima)

**Streamlit** — mapa interactivo + slider de pureza (0–100 %):

```bash
cd /home/lserey/repositorio/LULC/labeling
conda activate mb_coverage   # o use la ruta completa abajo

/home/lserey/.conda/envs/mb_coverage/bin/streamlit run visualizar_segmentos_etiquetados.py -- \
  --gpkg /home/lserey/mapbiomas_land/prod/labeling_slic_rev2015/18GXA/18GXA_3x3_c003_r003/18GXA_3x3_c003_r003_labeled_segments.gpkg
```

Alternativa sin activar conda:

```bash
/home/lserey/.conda/envs/mb_coverage/bin/python -m streamlit run visualizar_segmentos_etiquetados.py -- \
  --gpkg /home/lserey/mapbiomas_land/prod/labeling_slic_rev2015/18GXA/18GXA_3x3_c003_r003/18GXA_3x3_c003_r003_labeled_segments.gpkg
```

- Color = `clase_moda` (paleta C2)
- Borde rojo = segmento con `tiene_protegida`
- Sidebar: pureza mínima, opción solo tier protegido, histograma y tabla

**HTML estático** (misma barra de pureza, sin Streamlit):

```bash
python visualizar_segmentos_etiquetados.py \
  --export-html /home/lserey/mapbiomas_land/prod/labeling_slic_rev2015/18GXA/18GXA_3x3_c003_r003/dashboard.html \
  --gpkg .../18GXA_3x3_c003_r003_labeled_segments.gpkg
```
