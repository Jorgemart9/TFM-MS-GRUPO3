# TFM MS — Credit Risk MLOps (Grupo 3)

Pipeline de **riesgo de crédito** orientado a negocio (coste asimétrico,
calibración, equidad, interpretabilidad y despliegue) más la infraestructura
DevOps/Cloud (Terraform, CI de seguridad, gobierno del repo).

El proyecto se ha consolidado en **un único pipeline: `pipeline_v7.py`**.

## Estructura

```
TFM-MS-GRUPO3/
├── README.md                     # este archivo
├── .github/workflows/            # CI (security.yml)
├── terraform/                    # IaC (GCS, IAM, networking, monitoring)
├── CODEOWNERS, SECURITY.md, CONTRIBUTING.md, SETUP.md, .pre-commit-config.yaml
└── TFM/
    ├── requirements.txt          # dependencias del pipeline v7
    ├── pipeline/
    │   └── pipeline_v7.py        # ÚNICO pipeline (entrenamiento + evaluación + registro)
    ├── data/
    │   └── lending_club.csv      # dataset de entrada (no versionado, ~1 GB)
    ├── dashboard/
    │   └── dashboard.html        # panel de monitorización (consume artifacts/v7)
    ├── artifacts/                # SALIDAS generadas (no versionado)
    │   └── v7/                    #   modelo, métricas, SHAP, fairness, dashboard_data.js
    └── docs/
        └── ExplicacionVariables.xlsx
```

> Los artefactos (`TFM/artifacts/`), la base de MLflow (`mlflow.db`), `mlruns/`,
> el dataset y los `__pycache__` **no se versionan** (ver `.gitignore`): se
> regeneran al ejecutar el pipeline.

## Requisitos

```bash
cd TFM-MS-GRUPO3
python3 -m venv .venv && source .venv/bin/activate
pip install -r TFM/requirements.txt
```

## Cómo ejecutar el pipeline v7

Ejecutar **desde la raíz del repo** (las rutas por defecto son relativas a ella):

```bash
python TFM/pipeline/pipeline_v7.py
```

Opciones útiles (CLI):

```bash
# Entrenamiento definitivo con el 100% de los datos
python TFM/pipeline/pipeline_v7.py --sample-fraction 1.0

# Política de umbral por tasa de aprobación (controla falsos positivos)
python TFM/pipeline/pipeline_v7.py --threshold-mode approval_target --min-approval-rate 0.70

# Iterar rápido (sin calibración de probabilidades)
python TFM/pipeline/pipeline_v7.py --sample-fraction 0.05 --no-calibrate
```

El pipeline:
1. Limpia datos, crea el target y evita *data leakage* (split temporal 2018/2019).
2. Entrena XGBoost, LightGBM y CatBoost (challenger) con búsqueda de hiperparámetros.
3. Calibra probabilidades y fija el **umbral de decisión** (coste o tasa de aprobación).
4. Selecciona el **campeón por coste en validación** (no en test).
5. Evalúa en test: roll-out + significancia (bootstrap), SHAP, fairness.
6. Registra el campeón en **MLflow** como `pyfunc` con el umbral embebido.

Salidas en `TFM/artifacts/v7/`: `champion_model.pkl`, `champion_threshold.json`,
`model_comparison_summary_v7.json`, `rollout_comparison.csv`,
`threshold_policy_test.csv`, `fairness/`, `shap/` y `dashboard_data.js`.

## Dashboard

```bash
# servir el panel (lee TFM/artifacts/v7/dashboard_data.js)
python3 -m http.server 8000
# abrir http://127.0.0.1:8000/TFM/dashboard/dashboard.html
```

## MLflow

```bash
mlflow ui --backend-store-uri sqlite:///TFM/artifacts/mlflow.db
```
