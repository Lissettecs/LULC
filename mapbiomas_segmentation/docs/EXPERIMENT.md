# Experimentos — segmentación clásica · MapBiomas Chile · tile 18HYD / 2010

Índice maestro de pruebas de **Felzenszwalb** y **SLIC** para calibración visual antes de etiquetado con Collection 2.

Cada experimento vive en su **carpeta de código** (`seg_*`) y escribe salidas fuera del repo en `/home/lserey/mapbiomas_land/test/image_segmentation/`.

---

## Cómo leer los IDs

```
FELZ-05_ablacion_lv1
  │      └─ variante (grid, rf_n, podado, ablación, incremental…)
  └──────── ID cronológico estable dentro de Felzenszwalb
```

| Prefijo | Alcance |
|---------|---------|
| `FELZ-NN` | Felzenszwalb (geometría / granularidad) |
| `SLIC-NN` | SLIC + RAG + size filter |
| `LABEL-NN` | Etiquetado mayoritario vs landcover Col2 |

---

## Todos los experimentos

| ID | Carpeta | Entrada | Bandas / enfoque | Combos | Salida (data root) | Visualizador |
|----|---------|---------|------------------|--------|--------------------|--------------|
| FELZ-01 | [seg_felzenszwalb/](seg_felzenszwalb/) | mosaico 3B 0–1 | nir, swir1, red | 5×3 grid | `seg_felzenszwalb/` | `segmenters_viewer.py` |
| SLIC-01 | [seg_slic/pipeline_a/](seg_slic/pipeline_a/) | mosaico 3B 0–1 | SLIC → RAG hier → min150 | 5×3 grid | `seg_slic/pipeline_a/` | `segmenters_viewer.py` |
| SLIC-02 | [seg_slic/pipeline_b/](seg_slic/pipeline_b/) | mosaico 3B 0–1 | flujo unificado A→B | 5×3 grid | `seg_slic/pipeline_b/` | `segmenters_viewer.py` |
| FELZ-02 | [seg_felzenszwalb_rf_n/](seg_felzenszwalb_rf_n/) | stack 184B | RF Lv1/Lv3 (`importance_gated_clusters`) | 5×3 grid | `seg_felzenszwalb_rf_n/` | `segmenters_viewer.py` |
| FELZ-03 | [seg_felzenszwalb_rfn/](seg_felzenszwalb_rfn/) | stack 184B | RF_N **podado** (~10 bandas duras) | 1 combo (s200 σ0.1) | `seg_felzenszwalb_rfn/` | `segmenters_labeling_viewer.py` |
| FELZ-04 | [seg_felzenszwalb_ablacion/](seg_felzenszwalb_ablacion/) | stack 184B | ablación Lv1: medianas → medianas+1 dura | 14 corridas | `seg_felzenszwalb_ablacion/` | `segmenters_labeling_viewer.py` |
| FELZ-05 | [seg_felzenszwalb_incremental/](seg_felzenszwalb_incremental/) | stack 184B | **constructivo**: base 3B + 1 incremento | ~8 corridas | `seg_felzenszwalb_incremental/` | `incremental_results_viewer.py` |
| FELZ-06 | [seg_felzenszwalb_rf_lv3/](seg_felzenszwalb_rf_lv3/) | stack 184B | 34 bandas Lv3 desde `lv3_multitile.md` | 1 combo | `seg_felzenszwalb_rf_lv3/` | `lv3_results_viewer.py` |
| FELZ-07 | [seg_felzenszwalb_ablacion_lv3/](seg_felzenszwalb_ablacion_lv3/) | stack 184B | ablación Lv3: medianas → medianas+1 dura | 24 corridas | `seg_felzenszwalb_ablacion_lv3/` | `lv3_results_viewer.py` |
| LABEL-01 | [segmentation_labels/](segmentation_labels/) | seg_* + landcover | mayoría Col2 2015 sobre polígonos | por segmentador | `labeling_segmenters/` | `segmenters_labeling_viewer.py` |

> Referencia de granularidad: **FELZ-01** a s200 σ0.1 → ~16 732 segmentos (`REF_3BANDAS_NSEG`).  
> **FELZ-06** (34 bandas Lv3) → ~168 723 segmentos (`REF_LV3_COMPLETO_NSEG`, ~10× más fragmentado).

---

## Orden cronológico de las pruebas (julio 2026)

1. **FELZ-01 + SLIC-01/02** — calibración scale×sigma sobre mosaico 3 bandas.
2. **FELZ-02** — ¿RF mejora la geometría? Grid completo con bandas seleccionadas por RF.
3. **FELZ-03** — poda manual del stack RF_N para reducir fragmentación.
4. **FELZ-04** — ablación dirigida Lv1 (medianas puras vs medianas + feature dura).
5. **FELZ-05** — enfoque opuesto: sumar incrementos desde base 3B que funciona.
6. **FELZ-06** — replicar con selección Lv3 parseada desde REPORT `.md`.
7. **FELZ-07** — ablación Lv3 sobre las 34 bandas del reporte.
8. **LABEL-01** — overlays Col2 2015 y GPKG por combinación segmentador×params.

---

## Visualizadores

| Script | Alcance |
|--------|---------|
| [segmenters_viewer.py](segmenters_viewer.py) | FELZ-01, FELZ-02, SLIC-01/02 |
| [incremental_results_viewer.py](incremental_results_viewer.py) | FELZ-05 |
| [lv3_results_viewer.py](lv3_results_viewer.py) | FELZ-06, FELZ-07 |
| [segmenters_labeling_viewer.py](segmenters_labeling_viewer.py) | todos + overlays Col2 (LABEL-01) |

---

## Dónde están los outputs

| Tipo | Ubicación | En git |
|------|-----------|--------|
| GeoTIFF / PNG / CSV | `~/mapbiomas_land/test/image_segmentation/` | ❌ |
| HTML dashboards | mismo data root | ❌ |
| Logs SLURM | `labeling/image_segmentation/logs/` (local) | ❌ |
| Código + informes | este repo, rama `feat/image-seg-felzenszwalb` | ✅ |

---

## Fase 2 (no implementada)

- Verificación Col2: ¿incrementos viables recuperan pares de clases fusionados?
- Decisión final: segmentar con 3B y reservar RF solo para clasificación si geometría no mejora.
- Repetir ganador en SLIC+RAG para A/B de segmentadores.
