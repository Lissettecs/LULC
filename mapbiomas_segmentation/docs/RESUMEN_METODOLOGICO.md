# Resumen metodológico — segmentación y etiquetado Col2

Pruebas de calibración de segmentadores clásicos y etiquetado con MapBiomas Collection 2 sobre **6 tiles MGRS** (18FXH, 18GXP, 18HYD, 19HCD, 19JCJ, 19KDU), año **2010**. Julio 2026.

---

## 1. Objetivo

Desarrollar un flujo reproducible para:

1. **Segmentar** mosaicos Sentinel-2 normalizados con algoritmos interpretables (Felzenszwalb, SLIC+RAG).
2. **Elegir escala** de segmentación combinando criterios espectrales (sin usar Col2) y geométricos respecto a objetos Col2.
3. **Etiquetar** cada segmento por voto mayoritario Col2, filtrar por pureza, y **fusionar** parches adyacentes con la misma clase.
4. **Comparar** umbrales de pureza τ ∈ {0,95 · 0,90 · 0,85 · 0,80} antes de escalar a producción.

Los datos pesados (GeoTIFF, GPKG, HTML) viven en el cluster; el código en `mapbiomas_segmentation/`.

---

## 2. Datos de entrada

| Insumo | Descripción | Ruta (cluster) |
|--------|-------------|----------------|
| Mosaico 3B | NIR, SWIR1, Red normalizadas 0–1 | `nir_swir1_red_normalized_mosaics/{tile}_2010_nir_swir1_red_0-1.tif` |
| Col2 | Clasificación anual MapBiomas Chile C2 | `landcover_tiles/{tile}_classification_2010.tif` |
| Geometría MGRS | Referencia de tiles | `mgrs_tiles.gpkg` |

**Tiles:** 18FXH, 18GXP, 18HYD, 19HCD, 19JCJ, 19KDU.

---

## 3. Pruebas de segmentación

### 3.1 Segmentadores evaluados

| ID | Algoritmo | Entrada | Parámetros típicos | Salida |
|----|-----------|---------|-------------------|--------|
| **FELZ-01** | Felzenszwalb | Mosaico 3B | scale × sigma (grid 5×3) | `seg_felzenszwalb/` |
| **SLIC-01** | SLIC + RAG threshold | Mosaico 3B | scale × sigma; RAG p10/p20/p30 | `seg_slic/pipeline_a/` |
| **SLIC-02** | Pipeline unificado A→B | Mosaico 3B | Mismo grid | `seg_slic/pipeline_b/` |
| **FELZ-02…07** | Variantes RF (184 bandas, ablación Lv1/Lv3, incremental) | Stack multibanda | Combos reducidos | `seg_felzenszwalb_rf_*` |

El barrido principal usa **scale ∈ {25, 50, 100, 150, 200}** y **σ ∈ {0,1 · 0,5 · 0,8}** sobre el piloto **18HYD 2010**, con calibración visual en dashboards HTML.

### 3.2 SLIC Pipeline A (etapas)

1. **SLIC** sobre mosaico 3B → superpixels.
2. **RAG merge** con umbral por percentil de pesos (p10, p20, p30) — fusiona regiones espectralmente similares.
3. (Opcional) RAG jerárquico y filtro de tamaño mínimo (min150).

Para el etiquetado multi-tile se adoptó **SLIC s=50, σ=0,1, RAG p10** (`seg_{tile}_2010_s50_sig0.1_ragp10.tif`).

### 3.3 Felzenszwalb

Grafo de proximidad en espacio de color (3 bandas), parámetros **scale** (tamaño mínimo de componente) y **sigma** (suavizado).

Para el etiquetado multi-tile se adoptó **Felzenszwalb s=50, σ=0,1** (`seg_{tile}_2010_s50_sig0.1.tif`), permitiendo comparar ambos segmentadores a la **misma escala nominal** aunque la búsqueda de escala óptima (§4) recomiende otra para Felzenszwalb en 18HYD.

---

## 4. Búsqueda de escala óptima

Script: `eval_escala_optima.py` · Piloto: **18HYD 2010**, **σ = 0,1**.

Evalúa GeoTIFF de segmentación **ya existentes** del barrido; no re-segmenta.

### 4.1 Métricas

| Métrica | Fuente | Interpretación | Rol en decisión |
|---------|--------|----------------|-----------------|
| **Global Score (GS)** | Mosaico 3B (WV intra-segmento + índice de Moran entre vecinos) | Menor = segmentos más homogéneos espectralmente y mejor contrastados | **Argmin → scale_GS** (no circular: no usa Col2) |
| **ED2** | Objetos Col2 post-filtro moda 3×3 | Error dos lados (sobre/sub-segmentación), media por clase | **Argmin → scale_ED2** |
| **Pureza media** | Col2 vs segmentos | % píxeles con clase mayoritaria | **Solo control** (monótona ↓ al subir scale) |
| **Costo** | Nº de segmentos | Relativo al scale máximo del barrido | Desempate / penalización operativa |

**Clases tier protegido** (ED2 no puede empeorar >10% vs mínimo): 11, 61, 67, 23, 34, 24, 33.

### 4.2 Regla de decisión

1. Calcular **scale_GS** (óptimo espectral) y **scale_ED2** (óptimo vs objetos Col2).
2. Evaluar **convergencia**: si |scale_GS − scale_ED2| ≤ paso del barrido (25 px) → escala robusta.
3. Aplicar **restricción tier protegido** (descartar scales con ED2 degradado en clases sensibles).
4. Entre candidatas viables, preferir la de **menor costo** (menos segmentos) si GS está dentro del 5% del mínimo.

### 4.3 Resultados piloto 18HYD (σ=0,1)

| Segmentador | scale_GS | scale_ED2 | Convergen | **Escala elegida** | n segmentos |
|-------------|----------|-----------|-----------|-------------------|-------------|
| Felzenszwalb | 100 | 25 | No (Δ=75) | **150** | 20 721 |
| SLIC | 50 | 25 | Sí (Δ=25) | **50** | 265 246 |

**Lectura:**

- Col2 empuja hacia segmentos **pequeños** (scale_ED2=25); el mosaico favorece scales **intermedios**.
- Felzenszwalb: GS y ED2 **divergen** → se elige s=150 como compromiso (80,9% menos segmentos que s=25).
- SLIC: GS y ED2 **convergen** en s=50; scales ≥100 descartadas por tier protegido.
- SLIC produce ~**4× más segmentos** que Felzenszwalb a escala comparable.

Salidas: `eval_escala/puntos_*_18HYD_2010.{csv,md}`, gráficos PNG.

---

## 5. Etiquetado con MapBiomas Collection 2

Script: `label_and_merge.py` · Librería: `code/labeling/`.

### 5.1 Estadísticas por segmento

Para cada ID de segmento se calcula sobre píxeles válidos de Col2:

- **Clase mayoritaria** (`label_mode`) y su conteo.
- **Pureza** = píxeles clase mayoritaria / píxeles válidos Col2.
- **Cobertura** = píxeles válidos Col2 / píxeles totales del segmento.

### 5.2 Asignación de etiqueta

| Condición | Etiqueta | Código |
|-----------|----------|--------|
| Cobertura < κ **o** n_valid < n_min | Sin datos | 254 |
| Pureza < τ | Mixto | 255 |
| Pureza ≥ τ | Clase Col2 mayoritaria | ID Col2 |

**Parámetros fijos:**

| Parámetro | Valor |
|-----------|-------|
| κ (cobertura mínima) | 0,50 |
| n_min (píxeles válidos) | 10 |
| **τ (pureza)** | 0,95 · 0,90 · 0,85 · 0,80 |

### 5.3 Fusión de parches adyacentes

Tras la asignación, solo segmentos **ok** (pureza ≥ τ) reciben clase Col2 en un raster intermedio. Luego:

1. **Componentes conexas por clase** (8-vecinos implícitos en grilla): píxeles contiguos con la misma clase → una **región fusionada**.
2. Exportación:
   - `segments_labeled.gpkg` — polígonos pre-fusión (1 por segmento original).
   - `segments_merged.gpkg` — polígonos post-fusión (`region_id`, `label_final`).
   - `C2_labels_merged.tif` — raster uint8, 0 = sin etiqueta.

La fusión reduce fuertemente el número de entidades en SLIC (muchos segmentos ok son adyacentes y homogéneos).

### 5.4 Corridas realizadas

| Alcance | Detalle |
|---------|---------|
| Tiles | 6 MGRS × 2010 |
| Segmentadores | Felzenszwalb s50 σ0,1 · SLIC s50 σ0,1 RAG p10 |
| τ | 0,95 · 0,90 · 0,85 · 0,80 |
| Total | **48 corridas** (6×4×2) vía SLURM array |

Salidas por corrida: `labeling_tau{95|090|085|080}/tile_{MGRS}_2010/{segmentador}/`.

### 5.5 Resultados agregados (6 tiles)

Segmentos **ok** (pureza ≥ τ) y **regiones** tras fusión:

| τ | Felzenszwalb — ok | Felzenszwalb — regiones | SLIC RAG p10 — ok | SLIC RAG p10 — regiones |
|---|------------------:|------------------------:|------------------:|------------------------:|
| 0,95 | 138 147 | 80 235 | 503 295 | 53 691 |
| 0,90 | 160 322 | 87 352 | 582 232 | 60 949 |
| 0,85 | 180 116 | 93 362 | 649 149 | 66 361 |
| 0,80 | 200 130 | 100 030 | 713 617 | 71 586 |

**Patrones:**

- A menor τ, más segmentos reciben etiqueta (ok ↑, mixed ↓).
- SLIC tiene muchos más segmentos ok pero la fusión los condensa (~88–90% de reducción ok→regiones a τ=0,95).
- Felzenszwalb: menos segmentos totales; fusión modesta (~40% reducción ok→regiones a τ=0,95).

Ejemplo piloto **18HYD**, Felzenszwalb τ=0,95: 56 521 segmentos → 10 894 ok (19%) → **10 534 regiones** tras fusión.

---

## 6. Visualización y QA

| Visualizador | Contenido |
|--------------|-----------|
| `segmenters_viewer.html` | Barrido scale×sigma Felzenszwalb / SLIC |
| `tiles_segmentation_viewer.html` | 6 tiles, capas SLIC+RAG |
| `labeling_tau95_viewer.html` | Etiquetado: tile × τ × segmentador, capas pre/post fusión |

Capas PNG multi-resolución (1024 / 2048 / 4096 px) generadas en `capas/viewer/` por corrida.

---

## 7. Flujo metodológico (resumen)

```text
Mosaico 3B (6 tiles, 2010)
        │
        ├─► Felzenszwalb / SLIC+RAG  (barrido scale×sigma en piloto 18HYD)
        │
        ├─► eval_escala_optima  →  scale_GS, scale_ED2, escala elegida
        │
        ├─► Segmentación producción  (s=50, σ=0,1; SLIC + RAG p10)
        │         │
        │         ▼
        ├─► Estadísticas segmento × Col2  (pureza, mayoría, cobertura)
        │         │
        │         ▼
        ├─► Asignación con umbral τ  (ok / mixed / no_data)
        │         │
        │         ▼
        └─► Fusión adyacente misma clase  →  GPKG + GeoTIFF fusionados
```

---

## 8. Limitaciones y siguientes pasos

- Búsqueda de escala calibrada en **un tile** (18HYD); validar en tile del sur / macrozonas.
- Etiquetado multi-tile usa **s=50** para Felzenszwalb aunque el óptimo local fue **s=150** — conviene documentar sensibilidad o re-etiquetar con escala óptima por segmentador.
- Experimentos RF multibanda (FELZ-02…07) exploran geometría alternativa; no integrados aún al pipeline τ multi-tile.
- Pureza monótona **no** debe usarse para elegir escala; solo τ de **aceptación** post-segmentación.
- Anotación humana / recall de borde vs Col2 pendiente (Fase 2 en `eval_escala_optima.py`).

---

## Referencias en repositorio

- Catálogo experimentos: [EXPERIMENT.md](EXPERIMENT.md)
- Layout de datos: [DATA_LAYOUT.md](DATA_LAYOUT.md)
- Puntos de decisión escala: `~/mapbiomas_land/test/image_segmentation/eval_escala/puntos_comparativo_18HYD_2010.md`
