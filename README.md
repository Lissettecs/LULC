# LULC

Repositorio de flujos de trabajo para MapBiomas Chile Collection 3.

## Estructura del repositorio

### [generacion-mosaicos/](generacion-mosaicos/)

Contiene el flujo de generación de mosaicos Landsat por grillas MGRS.

Incluye scripts, notebooks, parámetros y módulos auxiliares usados para preparar mosaicos anuales. Documentación en [generacion-mosaicos/README.md](generacion-mosaicos/README.md).

### [generacion-muestras-ssl4eo/](generacion-muestras-ssl4eo/) (español)

Contiene el flujo de generación, caracterización, selección, revisión y auditoría de rectángulos de muestreo para chips SSL4EO-L.

Incluye scripts Python, documentación metodológica y archivos de ambiente. Instalación y ejecución en [generacion-muestras-ssl4eo/README.md](generacion-muestras-ssl4eo/README.md).

### [ssl4eo-sample-generation/](ssl4eo-sample-generation/) (English)

English version of the same SSL4EO-L sample generation workflow (READMEs and folder/file names translated; script logic unchanged).

Documentation and execution in [ssl4eo-sample-generation/README.md](ssl4eo-sample-generation/README.md).

### [labeling-samples/](labeling-samples/) (English)

Generación de mosaicos raster sieved y GeoPackages de etiquetas desde landcover MapBiomas Chile Colección 2 (pipeline en cluster, coherente con SSL4EO-L).

Documentación en [labeling-samples/README.md](labeling-samples/README.md).

### [segmentacion_etiquetas/](segmentacion_etiquetas/)

Calibración visual de segmentación Felzenszwalb sobre mosaicos NIR/SWIR1/red: grid de parámetros, quicklooks y explorador HTML antes de atribuir clases a polígonos.

Documentación en [segmentacion_etiquetas/README.md](segmentacion_etiquetas/README.md).

### [sample_review_calibration/](sample_review_calibration/) (English)

Prueba ciega de calibración de revisores sobre segmentos 100% puros (Collection 2). Propone cuotas, selecciona muestra no contigua estratificada por ecorregión y puntúa contra la clave confirmada por la supervisora.

Documentación en [sample_review_calibration/README.md](sample_review_calibration/README.md).

### [webapp_rgb/](webapp_rgb/)

GeoTIFF RGB (true color) y falso color (`swir1`/`nir`/`red`) por rectángulo de etiquetado CIM, con pirámides internas para la webapp.

Documentación en [webapp_rgb/README.md](webapp_rgb/README.md). Salidas en `mapbiomas_land/prod/webapp/rgb/`.

## Datos generados

No versionar datos pesados ni intermedios (rasters, shapefiles, GeoJSON, GeoPackage, ZIP, CSV de salida, etc.). Los productos se regeneran con los scripts o se almacenan fuera de Git.

Ver reglas de exclusión en [.gitignore](.gitignore).

### [mapbiomas_segmentation/](mapbiomas_segmentation/)

Segmentación de imágenes (Felzenszwalb, SLIC) y etiquetado MapBiomas Collection 2 sobre tiles MGRS: asignación por pureza τ, fusión de polígonos adyacentes, visualizadores HTML y jobs SLURM.

Documentación en [mapbiomas_segmentation/README.md](mapbiomas_segmentation/README.md). Los rasters y GPKG de salida viven en el cluster (`mapbiomas_land/test/image_segmentation/`), no en Git.
