# Lanzamiento nacional UTM + plan de revisión — 2026-07-27

Registro del primer pipeline **Chile completo** (grilla UTM nativa) y derivación de años
de revisión sobre la selección validada.

## Corridas en producción

| Etapa | Tag | Ubicación |
|-------|-----|-----------|
| Caracterización UTM | `20260727_1004` | `prod/samples_v02/01_caracterizacion/20260727_1004/` |
| Selección nacional | `20260727_1340` | `prod/samples_v02/02_seleccion/20260727_1340/` |
| Plan años revisión | `plan_revision_20260727_2030` | `…/20260727_1340/plan_revision_20260727_2030/` |

**Baseline de comparación (solo lectura):** selección `20260724_1357`, caracterización `20260724_1056`.

## Resultados clave

### Selección `20260727_1340`

- 341 rectángulos · 15/15 ecorregiones
- Mix 2×2 / 3×3: 76 % / 24 %
- Relleno: 12,3 % · 0 celdas vacías · 0 solapes
- Tests nacionales: **15/15** (`tests/test_aceptacion_nacional.py`)
- Informe: `informe_seleccion.md` · Dashboard: `dashboard_seleccion.html`

### Plan revisión `plan_revision_20260727_2030`

- 341 / 341 con `rev_year1`
- 384 pares (rectángulo, año) en `plan_revision_expandido.csv`
- 14 transiciones con fallback (revisión manual sugerida)
- Validación automática: OK

## Comandos de verificación (local)

```bash
cd /home/lserey/repositorio/coverage/ssl4eo-sample-generation_v02
conda activate mb_coverage

# Tests aceptación nacional
CARACT_RUN_TAG=20260727_1004 SEL_RUN_TAG=20260727_1340 \
  python -m pytest tests/test_aceptacion_nacional.py -v

# Informe vs baseline
python scripts/09_generar_informe_seleccion.py \
  --seleccion 20260727_1340 \
  --baseline 20260724_1357 \
  --caracterizacion 20260727_1004

# Dashboard HTML
python scripts/08_visualizar_seleccion.py \
  --run-tag 20260727_1340 \
  --export-html /home/lserey/mapbiomas_land/prod/samples_v02/02_seleccion/20260727_1340/dashboard_seleccion.html

# Plan de años de revisión
python scripts/10_generar_plan_revision.py --seleccion 20260727_1340

# Tests plan revisión
python -m pytest tests/test_plan_revision.py -v
```

## Capas canónicas

- Selección métrica: `seleccion_nacional_utm18.gpkg` (EPSG:32718), `seleccion_nacional_utm19.gpkg` (EPSG:32719)
- Selección con años revisión: `plan_revision_*/seleccion_con_rev_years_utm*.gpkg`
- Tabla larga segmentación: `plan_revision_*/plan_revision_expandido.csv`

## Rama git

`feature/plan-revision-years` — incluye grilla UTM nacional, selección corregida (cuotas A/B),
visualizador, informe y módulo `plan_revision/`.

## Pendientes conocidos (no bloquean el lanzamiento)

1. **split_inviable** en 13 ecorregiones (nivel eco; split nacional cumple).
2. **14 transiciones** sin cambio de moda entre periodos Landsat → revisar año manualmente.
3. **224 censo/refuerzo** con `censo_refuerzo_fallback` (clase objetivo no moda en ningún periodo; esperado en refuerzo).
