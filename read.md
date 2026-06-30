# Manual Técnico de MLOps: Pipelines de Riesgo Crediticio para GCP & Vertex AI
> **Proyecto: Framework de Monitorización, Explicabilidad y Gobierno de Modelos de Riesgo Crediticio**  
> **Socio Colaborador: Management Solutions**  
> **Estatus de Código: Productivo (Migrado a GCP Vertex AI Nativo)**

---

## 1. Arquitectura de MLOps en Google Cloud Platform (GCP)

Los scripts de este repositorio constituyen los componentes lógicos del ciclo de vida del modelo de Machine Learning (ML). En producción, estos pipelines se orquestan en la nube de forma nativa utilizando la suite de **Vertex AI**, eliminando dependencias de servidores externos como MLflow:

```mermaid
flowchart TD
    %% Nodos
    A[("BigQuery / Cloud Storage\n(Datos de Clientes: df_completo_cr.csv)")]
    B["Vertex AI Custom Job / Pipelines\n(eda.py)"]
    C["Vertex AI Training Pipeline\n(train_pipeline.py)"]
    D["Vertex AI Experiments\n(Seguimiento de Métricas/Parámetros)"]
    E["Vertex AI Model Registry\n(Registro de Champion en GCS)"]
    F["Cloud Run: FastAPI\n(Inferencia en Tiempo Real/Batch)"]
    G["Cloud Run: HTTP Server\n(dashboard.html / metrics.json)"]
    H["BigQuery\n(Logs de Inferencia & Ground Truth)"]
    I["Vertex AI Pipelines\n(test_model_quality.py - Validación & Drift)"]

    %% Conexiones
    A -->|Ingesta de Datos| B
    A -->|Datos de Entrenamiento| C
    B -->|Resultados EDA| G
    C -->|Metadatos & Parámetros| D
    C -->|Registro de Modelos| E
    C -->|SHAP & Métricas| G
    E -->|Despliegue de Inferencia| F
    F -->|Inferencia Logs| H
    H -->|Cálculo de Drift (PSI)| I
    I -->|Verificación de Calidad| G
```

---

## 2. Estructura de Ficheros del Paquete de Entrega

La carpeta contiene los archivos de código esenciales para el análisis, entrenamiento, testing y visualización:

*   **[eda.py](file:///Users/raularagall/Desktop/TFM/BDD%20Data%20Drift%203/eda.py)**: Pipeline de auditoría y análisis exploratorio de datos. Muestrea y limpia el dataset original y genera estadísticas descriptivas y correlaciones en un JSON consolidado.
*   **[train_pipeline.py](file:///Users/raularagall/Desktop/TFM/BDD%20Data%20Drift%203/train_pipeline.py)**: Pipeline de entrenamiento, optimización de hiperparámetros, selección de modelo campeón y explicabilidad local/global mediante la librería SHAP. Integra el SDK de **Vertex AI Experiments** y **Vertex AI Model Registry**.
*   **[export_metrics.py](file:///Users/raularagall/Desktop/TFM/BDD%20Data%20Drift%203/export_metrics.py)**: Script extractor de telemetría. Consulta el experimento de **Vertex AI Experiments** para extraer las métricas de las ejecuciones, consolidando los resultados junto con el análisis exploratorio y SHAP en `metrics.json`.
*   **[test_model_quality.py](file:///Users/raularagall/Desktop/TFM/BDD%20Data%20Drift%203/test_model_quality.py)**: Suite de pruebas unitarias y de integración que verifica la conformidad del esquema, umbrales de métricas (F1, AUC, Recall), PSI de data drift, presencia del modelo campeón en **Vertex AI Model Registry** y validez de SHAP/EDA.
*   **[dashboard.html](file:///Users/raularagall/Desktop/TFM/BDD%20Data%20Drift%203/dashboard.html)**: Interfaz de usuario interactiva y corporativa adaptada al branding de **Management Solutions** que visualiza el resumen general de negocio, comparativa de modelos, auditoría de drift, análisis EDA interativo y fichas de explicabilidad SHAP.
*   **[branding_MS.html](file:///Users/raularagall/Desktop/TFM/BDD%20Data%20Drift%203/branding_MS.html)**: Guía institucional de colores y tipografía corporativa de la marca.

---

## 3. Funcionamiento Interno de los Pipelines

### A. Auditoría y Análisis Exploratorio de Datos (`eda.py`)
Para optimizar el uso de recursos y memoria en el entrenamiento local, el script utiliza un parámetro de muestreo del **10%** del dataset crudo.
1.  **Limpieza de Porcentajes**: Convierte campos tipados como `object` (`tipo_interes`, `porcentaje_uso_credito_revolving`) eliminando el símbolo `%` y convirtiéndolos a `float64`.
2.  **Definición de Variable Objetivo (Target Credit Risk - Basilea III)**:
    *   **Clase 0 (Solvente)**: Préstamos en estado "Pagado completamente".
    *   **Clase 1 (Impago/Default)**: Préstamos en estado "Incobrable", "Default" y "Retraso de 31 a 120 días".
    *   **Exclusiones**: Se excluyen los registros "Al corriente", "Periodo de gracia", "Retraso de 16 a 30 días" y "Recién emitido" por no representar estados de madurez crediticia concluida.
3.  **Métricas Calculadas**: Conteo de valores nulos y sus porcentajes por variable, estadísticas descriptivas completas para variables numéricas, distribución por grados de riesgo (A a G) y finalidades del crédito, y matriz de correlación de Pearson.
    Los resultados se exportan a `eda_results.json`.

### B. Entrenamiento, Optimización y Explicabilidad (`train_pipeline.py`)
1.  **Transformador de Columnas (Scikit-Learn ColumnTransformer)**:
    *   *Numéricas*: Imputación por mediana (`SimpleImputer`) seguida de estandarización (`StandardScaler`).
    *   *Categóricas*: Imputación por la moda (`SimpleImputer`) seguida de codificación One-Hot (`OneHotEncoder`).
2.  **Mitigación de Desbalanceo y Calibración de Probabilidades (Platt Scaling)**:
    *   **Partición de Calibración**: Se divide el conjunto de entrenamiento original en un set base de entrenamiento ($80\%$) y un set de calibración independiente ($20\%$, `X_calib`), previniendo cualquier fuga de datos (data leakage).
    *   **Imbalance**: Se calcula el ratio de desbalanceo ($spw = \text{Negativos} / \text{Positivos}$) sobre el set de entrenamiento base y se utiliza `scale_pos_weight` en la búsqueda hiperparamétrica para guiar el aprendizaje.
    *   **Calibración**: Dado que el balanceo distorsiona la escala probabilística del clasificador (inflando las probabilidades hacia la clase minoritaria), se aplica **Platt Scaling** mediante `CalibratedClassifierCV(method='sigmoid', cv='prefit')`. Se ajusta el calibrador utilizando el set `X_calib` transformado y las etiquetas correspondientes. Esto transforma las fronteras del modelo en verdaderas **Probabilidades de Default (PD) calibradas**, fundamentales para el cálculo de la Pérdida Esperada bajo Basilea III.
3.  **Sintonización y Criterio de Selección (Tie-breaker)**:
    *   Realiza una búsqueda aleatoria (`RandomizedSearchCV`) optimizando la métrica **F1-Score** con validación cruzada ($k=3$, iteraciones $=10$) sobre el conjunto de entrenamiento base.
    *   **Desempate por ROC-AUC**: En caso de que dos o más modelos alcancen exactamente el mismo F1-Score en test (situación habitual con ruido sintético), el pipeline compara el **ROC-AUC** de los modelos empatados y selecciona como campeón al algoritmo con mayor poder de discriminación (ej. coronando a **LightGBM** con ROC-AUC de $0.535$ sobre CatBoost con $0.493$).
4.  **Logging y Registro en Vertex AI Experiments**:
    *   Inicializa el SDK con `aiplatform.init` especificando el experimento en la inicialización.
    *   Para cada modelo, crea una ejecución mediante `aiplatform.start_run` y registra los hiperparámetros (`log_params`) y las métricas resultantes (`log_metrics`).
5.  **Explicabilidad Global y Local (SHAP)**:
    *   Toma una muestra aleatoria de 500 registros del conjunto de prueba.
    *   **Desenvoltura del Calibrador**: Dado que `CalibratedClassifierCV` actúa como un contenedor (wrapper), el script extrae automáticamente el estimador base (`classifier.estimator`) para obtener la estructura de árboles original (CatBoost, LightGBM o XGBoost).
    *   Utiliza `shap.TreeExplainer` sobre dicho clasificador base de árboles.
    *   **Global**: Calcula el impacto absoluto medio de SHAP para listar las 12 características con mayor influencia en la probabilidad de default.
    *   **Local**: Extrae el expediente del cliente con la probabilidad de default más alta (Caso de Alto Riesgo) y más baja (Caso de Bajo Riesgo). Para cada uno, exporta los 6 factores que mayor peso aportaron a la predicción del modelo e incluye su registro original limpio en formato JSON.
    Los resultados se guardan en `shap_results.json`.
6.  **Serialización y Registro de Modelo**:
    *   Exporta el modelo campeón calibrado (`Pipeline` que contiene el calibrador) localmente en `model.joblib`.
    *   Si se proporciona un bucket de GCS, sube el archivo a Cloud Storage y registra el modelo en **Vertex AI Model Registry** usando contenedores oficiales de Google preconstruidos para scikit-learn.

### C. Consolidación de Telemetría (`export_metrics.py`)
Consulta el dataframe de ejecuciones de Vertex AI mediante `aiplatform.get_experiment_df`, identifica al campeón (basándose en F1-score), simula la evolución temporal (Concept Drift) y el PSI por variable (Data Drift), e incorpora los archivos `eda_results.json` y `shap_results.json` en un consolidado único llamado `metrics.json`.

### D. Suite de Pruebas de Calidad del Modelo (`test_model_quality.py`)
Actúa como puerta de calidad (Quality Gate) automatizada en el ciclo de CI/CD:
*   **Test 1 (Esquema)**: Verifica que el dataset de entrada (`df_completo_cr.csv` o su muestra `df_completo_cr_mini.csv`) contiene los tipos y columnas clave.
*   **Test 2 (Rendimiento)**: Asegura que el modelo campeón supera los umbrales mínimos requeridos: F1-Score $\ge 40\%$, ROC-AUC $\ge 65\%$, Recall $\ge 60\%$.
*   **Test 3 (Drift)**: Asegura que el PSI de las variables de entrada está por debajo del límite crítico de alerta ($PSI < 0.25$).
*   **Test 4 (Disponibilidad)**: Valida que el modelo se encuentra registrado y activo en **Vertex AI Model Registry** en GCP (o comprueba el archivo `model.joblib` local en fallback).
*   **Test 5 (SHAP)**: Valida que el mapeo SHAP global y local (Alto/Bajo riesgo) esté completo y con valores lógicos en `metrics.json`.
*   **Test 6 (EDA)**: Valida la integridad estructural de las estadísticas descriptivas y la matriz de correlación.

### E. Mecanismo de Fallback Local para Desarrollo (Modo Offline)
Si los scripts se ejecutan localmente sin credenciales o parámetros de GCP, se activará el **modo de fallback local**:
*   `train_pipeline.py` guardará el resumen de todas las corridas en un archivo estructurado local `local_runs.json` y el modelo en `model.joblib`.
*   `export_metrics.py` cargará las métricas de `local_runs.json` para generar `metrics.json`.
*   `test_model_quality.py` validará el registro del modelo a través de la presencia del archivo local `model.joblib`.

---

## 4. Guía de Despliegue en Vertex AI (GCP)

Para migrar este entorno local al ecosistema gestionado de Google Cloud, el departamento de datos debe seguir estos pasos estructurados:

### Paso 1: Configurar el Almacenamiento y Acceso a Datos
1.  Subir el archivo de datos original a un bucket de **Cloud Storage**:
    ```bash
    gsutil cp df_completo_cr.csv gs://mi-proyecto-tfm-bucket/data/
    ```
2.  *Alternativa Recomendada*: Cargar el dataset en **BigQuery** para consultas rápidas y estructuración de tablas.
3.  Utilizar los argumentos de línea de comandos en `eda.py` y `train_pipeline.py` para configurar las rutas de entrada/salida de forma dinámica (ej. `--input-path gs://...` o `--data-path gs://...`), eliminando la necesidad de modificar variables en el código fuente.

### Paso 1.5: Despliegue de Preprocesamiento en Cloud Run
El preprocesamiento de datos (limpieza y definición del target de Basilea III) se ejecuta en **Cloud Run** (como Job por lotes o desencadenado por Eventarc al subir un nuevo archivo a GCS) invocando el script `eda.py`:
- **Comando de Ejecución**:
  ```bash
  python3 eda.py \
    --input-path gs://mi-proyecto-tfm-bucket/datos_sucios/df_completo_cr.csv \
    --output-clean-path gs://mi-proyecto-tfm-bucket/datos_limpios/df_completo_cr_clean.csv \
    --output-eda-path gs://mi-proyecto-tfm-bucket/datos_limpios/eda_results.json \
    --sample-fraction 0.10 \
    --gcp-project mi-proyecto-gcp
  ```
- **Flujo**: El script procesa el 100% del dataset original, realiza la binarización de riesgo y guarda el CSV limpio en GCS. Este CSV limpio es posteriormente consumido por **Cloud Dataflow** para su inserción final en **BigQuery** y **Cloud SQL**, quedando disponible para el entrenamiento en **Vertex AI**.

### Paso 2: Dockerizar los Componentes del Pipeline
Crear una imagen Docker para Vertex AI. Ejemplo de `Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY train_pipeline.py .
COPY eda.py .
COPY export_metrics.py .
COPY test_model_quality.py .

ENTRYPOINT ["python", "train_pipeline.py"]
```

Crear el archivo `requirements.txt`:
```text
pandas>=2.0.0
numpy>=1.22.0
scikit-learn>=1.0.0
xgboost>=1.5.0
lightgbm>=3.3.0
catboost>=1.2.0
shap>=0.40.0
google-cloud-aiplatform>=1.30.0
google-cloud-bigquery>=3.0.0
google-cloud-storage>=2.0.0
db-dtypes>=1.0.0
joblib>=1.1.0
```

### Paso 3: Registrar la Imagen en Artifact Registry
1.  Crear un repositorio Docker en Artifact Registry:
    ```bash
    gcloud artifacts repositories create ml-images --repository-format=docker --location=europe-west1
    ```
2.  Compilar y subir la imagen:
    ```bash
    docker build -t europe-west1-docker.pkg.dev/mi-proyecto-tfm/ml-images/credit-risk-pipeline:v1 .
    docker push europe-west1-docker.pkg.dev/mi-proyecto-tfm/ml-images/credit-risk-pipeline:v1
    ```

### Paso 4: Programar y Orquestar con Vertex AI Pipelines
El pipeline de entrenamiento automatizado (CT) se define usando el SDK de Vertex AI. A continuación se muestra un ejemplo básico de orquestación en Python usando Kubeflow Pipelines (`kfp`):

```python
from google.cloud import aiplatform
from kfp import dsl

@dsl.pipeline(
    name="credit-risk-mlops-pipeline",
    description="Pipeline de entrenamiento, evaluación, tests de calidad y explicabilidad SHAP para riesgos"
)
def credit_risk_pipeline():
    # Paso 1: Análisis exploratorio y auditoría
    eda_op = dsl.ContainerOp(
        name="eda-step",
        image="europe-west1-docker.pkg.dev/mi-proyecto-tfm/ml-images/credit-risk-pipeline:v1",
        command=["python", "eda.py"]
    )
    
    # Paso 2: Entrenamiento y cálculo SHAP (depende del EDA)
    train_op = dsl.ContainerOp(
        name="train-step",
        image="europe-west1-docker.pkg.dev/mi-proyecto-tfm/ml-images/credit-risk-pipeline:v1",
        command=[
            "python", "train_pipeline.py",
            "--data-source", "bigquery",
            "--data-path", "mi-proyecto.tfm_dataset.tabla_limpia",
            "--gcp-project", "mi-proyecto",
            "--gcs-bucket", "mi-bucket-modelos",
            "--experiment-name", "credit-risk-mvp"
        ]
    ).after(eda_op)
    
    # Paso 3: Exportar métricas finales
    export_op = dsl.ContainerOp(
        name="export-step",
        image="europe-west1-docker.pkg.dev/mi-proyecto-tfm/ml-images/credit-risk-pipeline:v1",
        command=[
            "python", "export_metrics.py",
            "--gcp-project", "mi-proyecto",
            "--experiment-name", "credit-risk-mvp"
        ]
    ).after(train_op)
    
    # Paso 4: Pruebas unitarias de calidad y drift
    test_op = dsl.ContainerOp(
        name="test-step",
        image="europe-west1-docker.pkg.dev/mi-proyecto-tfm/ml-images/credit-risk-pipeline:v1",
        command=[
            "python", "test_model_quality.py",
            "--gcp-project", "mi-proyecto"
        ]
    ).after(export_op)
```

### Paso 5: Despliegue de Inferencia y Servidor de Dashboard (Cloud Run)
1.  **API de Inferencia**: El modelo registrado bajo `Champion_LightGBM_MVP_Balanced` en Vertex AI Model Registry puede ser desplegado a un Endpoint de Vertex AI o descargado y servido dentro de un contenedor FastAPI en **Cloud Run** con auto-escalado a 0.
2.  **Dashboard de Gobernanza**:
    *   `dashboard.html` se sirve estáticamente a través de un servidor web ligero (ej. Nginx o Apache) dockerizado y desplegado en **Cloud Run**.
    *   `metrics.json` se actualiza dinámicamente en un volumen de almacenamiento compartido o a través de una API que lea el JSON directamente desde un bucket de **Cloud Storage** donde los pipelines lo suban tras cada ejecución del pipeline de tests.
