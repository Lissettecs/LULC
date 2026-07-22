# Layout de datos (cluster)

Raíz de datos (fuera del repositorio):

```text
/home/lserey/mapbiomas_land/test/image_segmentation/
├── inputs/                          ← referencia lógica (paths reales abajo)
│   ├── nir_swir1_red_normalized_mosaics/   # mosaicos 3 bandas 0–1
│   ├── landcover_tiles/                    # Col2 por tile
│   └── mgrs_tiles.gpkg
│
├── seg_felzenszwalb/                # FELZ-01
├── seg_felzenszwalb_rf_n/           # FELZ-02
├── seg_felzenszwalb_rfn/            # FELZ-03
├── seg_felzenszwalb_ablacion/       # FELZ-04
├── seg_felzenszwalb_incremental/    # FELZ-05
├── seg_felzenszwalb_rf_lv3/         # FELZ-06
├── seg_felzenszwalb_ablacion_lv3/   # FELZ-07
├── seg_slic/
│   ├── pipeline_a/                  # SLIC-01 (RAG p10/p20/p30, size filter)
│   └── pipeline_b/                  # SLIC-02
│
├── labeling_tau95/                    # etiquetado + fusión (τ=0.95)
├── labeling_tau090/                   # τ=0.90
├── labeling_tau085/                   # τ=0.85
├── labeling_tau080/                   # τ=0.80
├── labeling_overlays/                 # PNG ok/mixed/no_data (LABEL-01)
├── labeling/                          # corridas tempranas (legacy)
│
├── eval_escala/                       # análisis escala óptima
├── optuna_6_tiles/
├── optuna_seg/
│
├── *.html                             # visualizadores generados
└── logs/                              # logs batch (recomendado)
```

## Salida de etiquetado (por tile / τ / segmentador)

```text
labeling_tau{95|090|085|080}/tile_{MGRS}_2010/{segmentador}/
├── segments_labeled.gpkg      # pre-fusión (1 polígono / segmento)
├── segments_merged.gpkg       # post-fusión (regiones contiguas misma clase)
├── C2_labels_merged.tif       # raster uint8 Col2 fusionado
├── summary.json
└── capas/viewer/              # PNG para visualizador HTML
```

## Segmentadores en producción (6 tiles 2010)

| ID | Raster segmentación |
|----|---------------------|
| `felzenszwalb_s50_sig01` | `seg_felzenszwalb/seg_{tile}_2010_s50_sig0.1.tif` |
| `slic_s50_sig01_ragp10` | `seg_slic/pipeline_a/seg_{tile}_2010_s50_sig0.1_ragp10.tif` |
