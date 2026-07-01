# 🏦 Sistema de Scoring Crediticio con MLOps — TFM Management Solutions & EDEM

Sistema de **Machine Learning en producción** para la predicción de **Probabilidad de Default (PD)** en carteras de crédito al consumo, con gobierno de modelos, explicabilidad SHAP y despliegue en Google Cloud Vertex AI. Desarrollado bajo los estándares metodológicos de Basilea III.

--

## 📂 Estructura del Proyecto

```
BDD Data Drift 3/
├── eda.py                  # Pipeline de preprocesamiento y análisis exploratorio
├── train_pipeline.py       # Pipeline de entrenamiento, búsqueda de hiperparámetros y calibración
├── export_metrics.py       # Consolidación de métricas para el dashboard
├── test_model_quality.py   # Suite de pruebas automáticas de calidad
├── dashboard.html          # Dashboard MLOps interactivo (servido en http://localhost:8080)
├── df_completo_cr.csv      # Dataset real de préstamos (~3.37M filas, ~1GB)
├── model.joblib            # Modelo campeón serializado (CatBoost/XGBoost/LightGBM calibrado)
├── metrics.json            # Métricas consolidadas para el dashboard (generado automáticamente)
├── local_runs.json         # Historial de ejecuciones de entrenamiento
├── eda_results.json        # Resultados del análisis exploratorio (generado automáticamente)
└── shap_results.json       # Valores SHAP de explicabilidad (generado automáticamente)
```

---

## ⚙️ Requisitos

```bash
pip install pandas numpy scikit-learn xgboost lightgbm catboost shap joblib
# Opcional para despliegue en GCP:
pip install google-cloud-aiplatform google-cloud-storage
```

---

## 🚀 Cómo Ejecutar el Sistema Completo

El flujo tiene **4 pasos** que deben ejecutarse en orden:

```bash
# Paso 1: Preprocesamiento y EDA
python3 eda.py --input-path df_completo_cr.csv --sample-fraction 0.1

# Paso 2: Entrenamiento de modelos
python3 train_pipeline.py --data-path df_completo_cr.csv --sample-fraction 0.1

# Paso 3: Consolidar métricas para el dashboard
python3 export_metrics.py

# Paso 4: Validar calidad del modelo
python3 test_model_quality.py

# Paso 5: Arrancar el dashboard (en una terminal separada)
python3 -m http.server 8080
# Abrir en el navegador: http://localhost:8080/dashboard.html
```

> **Nota sobre `--sample-fraction`**: Con el dataset completo (~3.37M filas), usar 0.10 (10%) es suficiente para el entrenamiento local. En producción con Vertex AI se puede usar 1.0.

---

## 📊 Pipeline de Preprocesamiento y EDA (`eda.py`)

### ¿Qué hace?

El script `eda.py` realiza **dos tareas diferenciadas** en un solo paso:

#### 1. Limpieza y Filtrado de Registros

Solo se conservan préstamos con estado de madurez crediticia definida, siguiendo la **definición de Default de Basilea III**:

| Clase | Estado del préstamo | Label |
|:---|:---|:---:|
| Solvente | `Pagado completamente` | `0` |
| Default | `Incobrable`, `Default`, `Retraso de 31 a 120 días` | `1` |

Los préstamos en estados intermedios (`En vigor`, `En periodo de gracia`, etc.) se **excluyen** porque no tienen resultado crediticio observable y contaminarían el target.

#### 2. Ingeniería de Características Financieras

La función `preprocess_and_feature_engineering()` aplica las siguientes transformaciones, **idénticas** en EDA y en entrenamiento para garantizar consistencia:

| Feature Nueva | Fórmula / Lógica | Justificación |
|:---|:---|:---|
| `plazo_meses` | Extracción numérica de `"36 months"` → `36.0` | Necesario para calcular la cuota |
| `antiguedad_laboral_num` | Mapeo ordinal: `< 1 year` → `0.5`, ..., `10+ years` → `10.0` | Preserva jerarquía de estabilidad laboral |
| `grado_riesgo_num` | Mapeo ordinal: `A` → `1`, ..., `G` → `7` | Preserva el sentido crediticio (mayor número = peor calidad) |
| `cuota_mensual_estimada` | `importe × (1 + tipo_interes/100) / plazo_meses` | Carga mensual real del cliente |
| `ratio_carga_financiera` | `(cuota × 12) / (ingresos_anuales + 1)` | Debt-to-Income (DTI) anual |
| `ingreso_residual_anual` | `ingresos_anuales − (cuota × 12)` | Margen de liquidez disponible |
| `alerta_sobreendeudamiento` | `(% uso revolving / 100) × consultas_últimos_6m` | Señal de deterioro financiero activo |
| `ingresos_anuales_log` | `log1p(ingresos_anuales)` | Normaliza la asimetría positiva fuerte |
| `importe_solicitado_log` | `log1p(importe_solicitado)` | Normaliza la asimetría positiva fuerte |

#### 3. Estadísticas del EDA

El análisis se ejecuta sobre una **muestra aleatoria** del dataset (controlable con `--sample-fraction`) y genera `eda_results.json` con:

- **Dimensiones**: número de filas brutas y filtradas
- **Nulos**: conteo y porcentaje por columna
- **Distribución del target**: proporción Solvente vs Default
- **Estadísticas descriptivas**: media, mediana, desviación típica, min, max para las 18 variables numéricas
- **Distribución categórica**: `grado_riesgo` y `finalidad_prestamo`
- **Matriz de correlación de Pearson**: 18×18

### Tasa de Default Real del Dataset

El dataset real presenta una distribución de clases aproximada de:

| Clase | Porcentaje |
|:---|:---:|
| Solvente (Clase 0) | ~79.2% |
| Default (Clase 1) | ~20.8% |

Ratio de desbalanceo **~4:1**, que se gestiona en el pipeline de entrenamiento.

---

## 🤖 Pipeline de Entrenamiento (`train_pipeline.py`)

### Arquitectura del Pipeline

El entrenamiento sigue una arquitectura de **Pipeline de Scikit-learn** con preprocesador y clasificador encadenados, más una capa adicional de calibración:

```
Datos Raw
    │
    ▼
preprocess_and_feature_engineering()   ← Misma función que eda.py
    │
    ▼
ColumnTransformer
  ├── Numéricas: SimpleImputer(median, add_indicator=True) → StandardScaler
  └── Categóricas: SimpleImputer(most_frequent) → OneHotEncoder
    │
    ▼
Clasificador Base (CatBoost / LightGBM / XGBoost)
  └── Entrenado con RandomizedSearchCV (20 iter × 3 folds)
    │
    ▼
Platt Scaling (CalibratedClassifierCV, sigmoid, cv='prefit')
  └── Ajustado sobre X_calib independiente (20% del train)
    │
    ▼
Búsqueda del Umbral Óptimo de Decisión
  └── Maximiza F1-Score en [0.05, 0.95] sobre X_calib
    │
    ▼
Evaluación en X_test independiente
```

### Partición de Datos

El dataset se divide en tres particiones estrictamente separadas:

```
Dataset completo (sample_fraction × total)
├── 80% → X_train
│   ├── 80% → X_train_base  (entrenamiento + RandomizedSearchCV)
│   └── 20% → X_calib       (calibración de probabilidades + búsqueda de umbral)
└── 20% → X_test            (evaluación final — nunca visto durante entrenamiento)
```

> ⚠️ **Importante**: Esta separación triple evita el *data leakage* en la calibración, un error metodológico grave en pipelines de crédito.

### Modelos Comparados

Se comparan tres Gradient Boosting de última generación con sus grids de hiperparámetros expandidos:

#### CatBoost
```
iterations:      [300, 500, 800]
depth:           [6, 8, 10]
learning_rate:   [0.01, 0.03, 0.05, 0.1]
l2_leaf_reg:     [1, 3, 5, 7]
subsample:       [0.7, 0.8, 0.9]
scale_pos_weight: centrado en ratio de desbalanceo
```

#### LightGBM
```
n_estimators:     [300, 500, 800]
max_depth:        [7, 9, 12, -1 (sin límite)]
num_leaves:       [31, 63, 127, 255]
learning_rate:    [0.01, 0.03, 0.05, 0.1]
min_child_samples:[20, 50, 100]
subsample:        [0.7, 0.8, 0.9]
colsample_bytree: [0.7, 0.8, 0.9]
reg_alpha:        [0, 0.1, 1.0]
reg_lambda:       [0, 1.0, 5.0]
```

#### XGBoost
```
n_estimators:     [300, 500, 800]
max_depth:        [6, 8, 10, 12]
learning_rate:    [0.01, 0.03, 0.05, 0.1]
min_child_weight: [1, 5, 10]
subsample:        [0.7, 0.8, 0.9]
colsample_bytree: [0.7, 0.8, 0.9]
reg_alpha:        [0, 0.1, 1.0]
reg_lambda:       [1.0, 5.0, 10.0]
gamma:            [0, 0.1, 0.5]
```

### Gestión del Desbalanceo de Clases

Se usa `scale_pos_weight = N_negativos / N_positivos ≈ 3.8` para penalizar el error en la clase minoritaria (Default). Se prueban también variantes ±25% alrededor de ese valor óptimo.

### Calibración de Probabilidades (Platt Scaling)

Un clasificador entrenado con `scale_pos_weight` produce **probabilidades infladas** que no representan la PD real del cliente. Esto hace el modelo no utilizable para el cálculo de provisiones bajo Basilea III.

La solución implementada es **Platt Scaling** (`CalibratedClassifierCV(method='sigmoid', cv='prefit')`):

1. El clasificador base se entrena sobre `X_train_base`
2. Se ajusta una función sigmoide sobre `X_calib` (datos nunca vistos por el clasificador base)
3. El resultado son **PDs calibradas** directamente comparables con la tasa de default observada

### Umbral Óptimo de Decisión

En riesgo crediticio **nunca se usa el umbral estándar de 0.5**. El sistema busca automáticamente el umbral que maximiza el F1-Score sobre `X_calib`:

```python
for thresh in np.linspace(0.05, 0.95, 91):
    f1 = f1_score(y_calib, (probs >= thresh).astype(int))
```

Los umbrales encontrados típicamente oscilan entre **0.19 y 0.21**, reflejo de la tasa base de default del ~20%.

### Selección del Modelo Campeón

El modelo con mayor **F1-Score** en `X_test` es coronado campeón. En caso de empate exacto, se usa el **ROC-AUC como desempate**.

### Resultados Obtenidos (10% muestra real)

| Modelo | Umbral | F1-Score | ROC-AUC | Recall | Accuracy | Precision |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **CatBoost** 🏆 | 0.21 | **41.51%** | **68.48%** | 63.76% | 62.31% | 30.70% |
| LightGBM | 0.20 | 41.43% | 68.41% | 66.76% | — | — |
| XGBoost | 0.19 | 41.43% | 68.29% | 69.53% | — | — |

**Contexto de la industria**: Un Gini (= 2×AUC - 1) del **~37%** es un resultado típico y sólido para modelos de *application scoring* (sin datos de comportamiento de pago), donde el rango habitual es 30%–50%.

### Explicabilidad SHAP

Tras seleccionar el campeón, el pipeline calcula valores SHAP con `TreeExplainer` (nativo para árboles, sin aproximaciones):

- **Global**: Top 12 variables más importantes por impacto medio absoluto
- **Local**: Explicación del cliente de mayor y menor riesgo del conjunto de test, con factores que incrementan o reducen el riesgo de default

Los valores SHAP se exportan a `shap_results.json` y se visualizan en el dashboard.

---

## 📈 Consolidación de Métricas (`export_metrics.py`)

Agrega en un único fichero `metrics.json` los resultados de todos los scripts:

| Sección | Fuente | Contenido |
|:---|:---|:---|
| `champion` | `local_runs.json` | Nombre y métricas del modelo campeón |
| `comparison` | `local_runs.json` | Comparativa de los 3 modelos |
| `evolution` | Simulación | Serie temporal de ROC-AUC y F1 (últimos 25 días) |
| `data_drift` | Simulación | PSI (Population Stability Index) por variable |
| `business` | Cálculo | KPIs de negocio: pérdidas evitadas, latencia del pipeline |
| `shap` | `shap_results.json` | Importancias globales y explicaciones locales |
| `eda` | `eda_results.json` | Análisis exploratorio completo |

El script soporta **GCP Vertex AI** como fuente primaria y **modo local** como fallback automático.

---

## ✅ Suite de Pruebas de Calidad (`test_model_quality.py`)

6 tests automáticos que validan el sistema end-to-end antes de cada despliegue:

| Test | Qué valida | Umbral de éxito |
|:---|:---|:---|
| **Test 1: Esquema de Datos** | Existencia y columnas mínimas del CSV | Columnas `estado_prestamo`, `importe_solicitado`, `ingresos_anuales` presentes |
| **Test 2: Rendimiento** | Métricas del modelo campeón | F1 ≥ 35%, ROC-AUC ≥ 65%, Recall ≥ 50% |
| **Test 3: Data Drift** | PSI de las variables clave | PSI < 0.25 en todas las variables |
| **Test 4: Modelo disponible** | Modelo serializado accesible | `model.joblib` existe ó modelo en Vertex AI |
| **Test 5: SHAP** | Integridad de explicabilidad | JSON con claves `global` y `local`, probabilidades diferenciales |
| **Test 6: EDA** | Estructura del análisis exploratorio | Claves `dimensions`, `nulls`, `target_distribution`, `correlation` |

```bash
python3 test_model_quality.py
# Output: [OK] / [FAIL] por cada test
# Exit code 0 = todo OK, Exit code 1 = hay fallos
```

---

## 🖥️ Dashboard MLOps (`dashboard.html`)

Dashboard interactivo que consume `metrics.json` y presenta:

- **KPIs del Modelo Campeón**: F1-Score, ROC-AUC, Recall, Precision, Accuracy
- **Comparativa de Modelos**: tabla y gráfico de barras con los 3 candidatos
- **Evolución Temporal**: línea de ROC-AUC y F1 en los últimos 25 días
- **Monitor de Data Drift**: barras de PSI por variable con alerta en PSI > 0.25
- **Importancia de Variables (SHAP)**: ranking global de las 12 features más predictivas
- **Explicación Local**: desglose de los factores de riesgo para un cliente concreto
- **Calculadora de Impacto Basilea III**: calcula la Pérdida Esperada con EL = EAD × PD × LGD
- **EDA Interactivo**: estadísticas descriptivas, distribución de nulos y correlaciones

```bash
# Para visualizar el dashboard:
python3 -m http.server 8080
# Abrir: http://localhost:8080/dashboard.html
```

---

## ☁️ Despliegue en Google Cloud (Vertex AI)

El sistema está diseñado para escalar a producción en GCP:

```bash
# Con proyecto GCP configurado:
python3 eda.py \
  --input-path gs://mi-bucket/datos/df_completo_cr.csv \
  --output-clean-path gs://mi-bucket/datos/clean.csv \
  --output-eda-path gs://mi-bucket/resultados/eda_results.json \
  --gcp-project mi-proyecto \
  --sample-fraction 1.0

python3 train_pipeline.py \
  --data-source bigquery \
  --data-path mi-proyecto.dataset.tabla_creditos \
  --gcp-project mi-proyecto \
  --gcs-bucket mi-bucket \
  --experiment-name credit-risk-v1 \
  --sample-fraction 1.0
```

En modo GCP, el modelo se registra automáticamente en **Vertex AI Model Registry** y los experimentos en **Vertex AI Experiments**.

---

## 📐 Marco Metodológico (Basilea III)

### Definición de Default
Se sigue el Artículo 178 del Reglamento (UE) 575/2013 (CRR): un préstamo se considera en default si presenta **más de 90 días de mora** (`Retraso de 31 a 120 días`) o si ha sido clasificado como `Incobrable` o `Default` por la entidad.

### Fórmula de Pérdida Esperada
$$EL = EAD \times PD \times LGD$$

- **PD** (Probability of Default): output calibrado del modelo
- **EAD** (Exposure at Default): saldo dispuesto al momento del impago (configurable, por defecto 75%)
- **LGD** (Loss Given Default): tasa de pérdida en caso de impago (por defecto **45%**, estándar Basilea para carteras senior no garantizadas)

### Por Qué No Se Usa el Umbral 0.5

En los departamentos de riesgo cuantitativo la PD se usa como **score continuo**, no como clasificación binaria. Cuando se requiere una decisión de concesión, el umbral se optimiza considerando:
- La tasa base de default de la cartera (~20%)
- La matriz de costes: coste de un Falso Negativo (cliente insolvente concedido) vs Falso Positivo (cliente solvente rechazado)
- Los requerimientos de capital del modelo interno

El umbral óptimo encontrado (~0.20) refleja que, con una tasa base del 20%, la separación óptima entre clases ocurre cerca de ese punto.

---

## 🔬 Decisiones de Diseño Clave

### ¿Por qué 3 modelos y no solo 1?
La comparación competitiva entre CatBoost, LightGBM y XGBoost en cada ejecución garantiza que el modelo que va a producción siempre es el óptimo para los datos más recientes. Los tres son Gradient Boosting sobre árboles y tienen rendimiento similar en este dominio, lo que valida la robustez del resultado.

### ¿Por qué `add_indicator=True` en el imputer?
Los valores nulos en variables como `antiguedad_laboral` o `ingresos_anuales` no son aleatorios: los clientes que no declaran estos datos presentan patrones de riesgo distintos. Con `add_indicator=True`, el `SimpleImputer` genera columnas booleanas adicionales que permiten a los árboles aprender si la **ausencia de información** es en sí misma una señal de riesgo.

### ¿Por qué variables ordinales en lugar de One-Hot para `grado_riesgo`?
`grado_riesgo` (A, B, C, D, E, F, G) tiene un orden natural crediticio. Codificarlo como One-Hot destruye ese orden y crea 7 columnas dispersas que añaden ruido. El mapeo ordinal (`A=1, ..., G=7`) preserva la información de jerarquía que los árboles pueden explotar directamente.

### ¿Por qué el F1-Score no mejora con más hiperparámetros?
Con el dataset actual y las features disponibles (~20 variables de *application scoring*), los tres modelos convergen al mismo techo de rendimiento (~41.5% F1, ~68.5% ROC-AUC). Esto no es un fallo del pipeline: indica que **la señal discriminativa del dataset está completamente capturada** por los modelos de árboles con la feature set actual. Para superar ese techo se necesitarían datos de comportamiento adicionales (historial de pagos, saldo dispuesto mensual, etc.).
