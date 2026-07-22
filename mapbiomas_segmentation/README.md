# MapBiomas — segmentación y etiquetado

Repositorio **canónico** de código para experimentos de segmentación (Felzenszwalb, SLIC) y etiquetado MapBiomas Collection 2 sobre tiles MGRS.

Los **datos** (GeoTIFF, GPKG, HTML, logs) permanecen en el cluster:

`/home/lserey/mapbiomas_land/test/image_segmentation/`

> **No subir a GitHub todavía** — reorganización local en curso.

## Estructura

```text
mapbiomas_segmentation/
├── README.md
├── config/
│   └── paths.yaml              # DATA_ROOT, tiles, rutas de salida
├── docs/
│   ├── DATA_LAYOUT.md          # mapa de datos en cluster
│   ├── EXPERIMENT.md           # catálogo FELZ-01…07, SLIC, LABEL
│   └── labeling/               # SPEC, READMEs de librería
├── code/
│   ├── segmentation/
│   │   ├── felzenszwalb/       # FELZ-01…07 (subcarpetas por experimento)
│   │   └── slic/               # pipeline_a (legado), pipeline_b
│   ├── labeling/               # librería unificada (assign, merge, overlays)
│   ├── viewers/                # generadores HTML (*.py)
│   └── analysis/
│       └── eval_escala_optima.py
├── jobs/
│   ├── slurm/                  # sbatch (segmentación, etiquetado, export)
│   └── shell/                  # bash batch local / llamados desde SLURM
└── logs/                       # logs locales (gitignored)
```

## Uso rápido

### Etiquetado τ (6 tiles × 4 purezas × 2 segmentadores)

```bash
cd jobs/slurm
mkdir -p ../../logs
sbatch run_all_tiles_tau.slurm
```

### Visualizador etiquetado

```bash
/home/lserey/.conda/envs/mb_coverage/bin/python code/viewers/labeling_tau95_viewer.py
cd /home/lserey/mapbiomas_land/test/image_segmentation
python3 -m http.server 8765
# → http://localhost:8765/labeling_tau95_viewer.html
```

### Segmentación SLIC RAG batch

```bash
cd jobs/slurm
sbatch run_ragp10_s50_batch.slurm
```

## Migración desde `image_segmentation/`

La carpeta anterior (`coverage_test/labeling/image_segmentation/`) queda como **legado**.
El código fue **copiado** aquí; los scripts viejos siguen funcionando hasta migrar referencias.

Próximo paso (pendiente): actualizar imports/`DATA_ROOT` en todos los módulos para leer `config/paths.yaml`.

## Referencias

- [Layout de datos en cluster](docs/DATA_LAYOUT.md)
- [Catálogo de experimentos](docs/EXPERIMENT.md)
- [Especificación etiquetado](docs/labeling/SPEC.md)
