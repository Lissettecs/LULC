# Pipeline muestras finales (2×2 / 3×3, scale300)

Ejecutar desde la raíz de `generacion-muestras-ssl4eo/`:

```powershell
cd LULC/generacion-muestras-ssl4eo
```

| Paso | Script | Descripción |
|------|--------|-------------|
| 01 | `01_caracterizacion_grillas_gee.py` | Caracteriza grillas candidatas en GEE (export SHP a Drive, v3.1) |
| 02 | `02_descargar_grillas_drive.py` | Descarga ZIPs caracterizados → `archivos_intermedios/gee_caracterizacion/` |
| 03 | `03_seleccion_rectangulos.py` | Selección por tipo de muestra → `muestras_finales/` (anti-solape intra-huso y frontera UTM18/UTM19) |
| 04 | `04_anotar_taxonomia_grillas.py` | Taxonomía N1/N2/N3 sobre selección (`*_taxonomia_n3`) |
| 05 | `05_revision_seleccion_rectangulos.py` | Reportes de revisión → `archivos_intermedios/revision/` |
| 06 | `06_auditoria_balanceo.py` | Checklist de balanceo vs metas (14 criterios) |
| 07 | `07_visualizar_reportes.py` | Dashboard Streamlit de reportes de revisión |
| 08 | — | *Sin script.* Prefijo `08_` = tablas de clases críticas del paso 05 |
| 09 | `09_generar_plan_revision_rectangulos.py` | Plan de años de revisión por rectángulo |
| 10 | `10_consolidar_plan_revision_nacional.py` | Consolida planes UTM18/UTM19 en plan nacional |

## Dashboard de visualización

```powershell
streamlit run scripts/07_visualizar_reportes.py
python scripts/07_visualizar_reportes.py --export-html revision_dashboard.html
```

Lee reportes de `archivos_intermedios/revision/`, geometrías de `muestras_finales/` y puede superponer chips 1×1 (opcional, desactivado por defecto).

## Ejemplo UTM19 (flujo completo 02–10)

```powershell
python scripts/02_descargar_grillas_drive.py --scale300-all

python scripts/03_seleccion_rectangulos.py `
  --homogeneo archivos_intermedios/gee_caracterizacion/grilla_ssl4eo_muestras_homogeneo_2x2_UTM19_scale300_n3.zip `
  --mixto archivos_intermedios/gee_caracterizacion/grilla_ssl4eo_muestras_mixto_3x3_UTM19_scale300_n3.zip `
  --no-auto-previous

python scripts/04_anotar_taxonomia_grillas.py `
  -i muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM19_scale300.csv

python scripts/05_revision_seleccion_rectangulos.py --utm 19
python scripts/06_auditoria_balanceo.py

python scripts/09_generar_plan_revision_rectangulos.py `
  -i muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM19_scale300.geojson `
  -o archivos_intermedios/revision/plan_revision_UTM19_scale300.csv

python scripts/10_consolidar_plan_revision_nacional.py `
  --input archivos_intermedios/revision/plan_revision_UTM18_scale300.csv `
          archivos_intermedios/revision/plan_revision_UTM19_scale300.csv `
  --out-dir archivos_intermedios/revision
```

## Módulos de apoyo

- `balanceo_seleccion.py` — balanceo, split espacial, relleno
- `clases_criticas.py` — clases raras / críticas
- `taxonomia_clases.py` — lookup taxonomía N3
- `rutas_proyecto.py` — rutas `muestras_finales/` e `archivos_intermedios/`
