# LULC

Repositorio de flujos de trabajo para MapBiomas Chile Collection 3.

## Estructura del repositorio

### [generacion-mosaicos/](generacion-mosaicos/)

Contiene el flujo de generación de mosaicos Landsat por grillas MGRS.

Incluye scripts, notebooks, parámetros y módulos auxiliares usados para preparar mosaicos anuales.

### [generacion-muestras-ssl4eo/](generacion-muestras-ssl4eo/)

Contiene el flujo de generación, caracterización, selección, revisión y auditoría de rectángulos de muestreo para chips SSL4EO-L.

Incluye scripts Python, documentación metodológica y archivos de ambiente. La documentación completa del flujo está en [generacion-muestras-ssl4eo/README.md](generacion-muestras-ssl4eo/README.md).

#### Instalación rápida

```bash
git clone https://github.com/Lissettecs/LULC.git
cd LULC/generacion-muestras-ssl4eo
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
```

Alternativa con Conda/Mamba:

```bash
cd LULC/generacion-muestras-ssl4eo
mamba env create -f environment.yml
mamba activate lulc-muestras
```

Los scripts se ejecutan desde `generacion-muestras-ssl4eo/`, no desde la raíz del repositorio.

## Datos generados

Este repositorio no debe almacenar datos generados pesados o intermedios.

No se deben subir grillas exportadas, shapefiles, GeoJSON, GeoPackage, rasters, ZIP de salida, carpetas de procesamiento ni reportes derivados.

Los datos generados deben mantenerse fuera de Git o en almacenamiento externo. Las reglas de exclusión están en [.gitignore](.gitignore).
