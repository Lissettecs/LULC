# App GEE — Revision QA muestras anuales

## Requisitos

- Asset base con campos QA: `annual_samples` en  
  `projects/mapbiomas-chile/assets/LULC/COLLECTION-03/SAMPLES/SAMPLES_COL3/SAMPLES_LABELS_SSL4EO/annual_samples`
- Proyecto GEE: `mapbiomas-chile`

## Instalacion

1. Abrir [Earth Engine Code Editor](https://code.earthengine.google.com/)
2. **New > App**
3. Copiar el contenido de `review_annual_samples.js` en el editor principal
4. Ejecutar y publicar la App (Share > Change sharing settings)

## Flujo de revision

1. **Cola (izquierda):** filtrar por UTM, tier, `rect_qa`; seleccionar rectangulo-año
2. **Gate:** completar `rect_qa`, `rect_note`, `qa_user`; guardar
3. **Mapa:** Landsat RGB del `rev_year`; NDVI si tier >= 2
4. **Poligono:** click en mapa → completar `poly_qa`, `qa_scope`, `corr_id`, `err_type`
5. **Batch:** aprobar/rechazar por clase, >=5%, rechazar <1%
6. **Borrador:** guardar JSON desde consola
7. **Publicar:** Export a `annual_samples_vN` o usar script Python para merge completo

## Publicacion versionada (recomendado para 334k poligonos)

```bash
# 1. Guardar borrador desde la app (consola JSON) a archivo
# 2. Publicar version fusionada local + GEE
python scripts/06_publish_qa_version.py \
  --draft-json /path/to/qa_draft.json \
  --version v1 \
  --wait --overwrite
```

## Validacion pre-publicacion

```bash
python scripts/05_validate_qa_export.py \
  --gpkg /home/lserey/mapbiomas_land/prod/labels/annual/annual_samples_v1.gpkg \
  --layer annual_samples_v1
```

## Campos del formulario

| Editable | Descripcion |
|---|---|
| `rect_qa` | pendiente / aprobado / rechazado / parcial |
| `rect_note` | notas rectangulo-año |
| `poly_qa` | vacio / aprobado / rechazado |
| `qa_scope` | auto / poligono / clase |
| `corr_id` | clase corregida C2 N3 |
| `err_type` | tipo de error si rechazado |
| `poly_note` | comentario |
| `qa_user` | revisor |

Derivados al exportar: `lbl_id`, `cov_rect`, `qa_ver`
