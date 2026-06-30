import pandas as pd
import numpy as np
import random
import os
import argparse
import json
import joblib
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.calibration import CalibratedClassifierCV

# Intentar importar las librerías de GCP
gcp_active = False
try:
    from google.cloud import aiplatform
    from google.cloud import storage
    gcp_active = True
except ImportError:
    print("[!] google-cloud-aiplatform o google-cloud-storage no están instalados. Operando en modo Local Fallback.")

# -------------------------------------------------------------------
# 1. PARSEADO DE ARGUMENTOS
# -------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Pipeline de Entrenamiento de Riesgo Crediticio para Vertex AI / Local")
parser.add_argument("--data-source", type=str, choices=["local", "bigquery"], default="local", help="Origen de datos: 'local' (CSV) o 'bigquery'")
parser.add_argument("--data-path", type=str, default="df_completo_cr.csv", help="Ruta del archivo CSV o nombre de la tabla de BigQuery")
parser.add_argument("--sample-fraction", type=float, default=0.10, help="Fracción de muestreo del dataset")
parser.add_argument("--gcp-project", type=str, default=None, help="ID del Proyecto de Google Cloud")
parser.add_argument("--gcp-location", type=str, default="europe-west1", help="Región de GCP (por ejemplo, europe-west1)")
parser.add_argument("--gcs-bucket", type=str, default=None, help="Bucket de GCS para almacenar los artefactos del modelo")
parser.add_argument("--experiment-name", type=str, default="credit-risk-mvp", help="Nombre del experimento en Vertex AI")

args = parser.parse_args()

# -------------------------------------------------------------------
# FUNCIONES AUXILIARES DE GCP
# -------------------------------------------------------------------
def upload_to_gcs(local_file, bucket_name, gcs_path):
    print(f"[*] Subiendo {local_file} a gs://{bucket_name}/{gcs_path}...")
    client = storage.Client(project=args.gcp_project)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(local_file)
    print("[*] Archivo subido exitosamente a GCS.")

def load_dataset(source_type, data_path, sample_fraction):
    if source_type == "bigquery":
        print(f"[*] Cargando datos desde BigQuery: {data_path} (Muestra: {sample_fraction*100}%)...")
        from google.cloud import bigquery
        client = bigquery.Client(project=args.gcp_project)
        if sample_fraction < 1.0:
            query = f"SELECT * FROM `{data_path}` WHERE RAND() < {sample_fraction}"
        else:
            query = f"SELECT * FROM `{data_path}`"
        df = client.query(query).to_dataframe()
        print(f"[*] Datos cargados desde BigQuery. Tamaño: {df.shape}")
        return df
    else:
        print(f"[*] Cargando datos desde CSV local: {data_path} (Muestra: {sample_fraction*100}%)...")
        import random
        random.seed(42)
        if not os.path.exists(data_path):
            raise FileNotFoundError(f"No se encontró el archivo local: {data_path}")
        df = pd.read_csv(
            data_path,
            sep=';',
            header=0,
            skiprows=lambda i: i > 0 and random.random() > sample_fraction
        )
        print(f"[*] Datos cargados localmente. Tamaño: {df.shape}")
        return df

# -------------------------------------------------------------------
# INICIALIZACIÓN DE VERTEX AI O LOCAL FALLBACK
# -------------------------------------------------------------------
ai_initialized = False
if gcp_active:
    try:
        # Inicializar el SDK de Vertex AI
        aiplatform.init(
            project=args.gcp_project,
            location=args.gcp_location,
            staging_bucket=f"gs://{args.gcs_bucket}" if args.gcs_bucket else None,
            experiment=args.experiment_name
        )
        ai_initialized = True
        print(f"[*] Vertex AI inicializado con éxito. Experimento: '{args.experiment_name}'")
    except Exception as e:
        print(f"[!] No se pudo inicializar Vertex AI: {e}. Operando en modo Local Fallback.")
        ai_initialized = False
else:
    print("[*] Iniciando Pipeline en modo Local Fallback...")

# Cargar Datos
df = load_dataset(args.data_source, args.data_path, args.sample_fraction)

# -------------------------------------------------------------------
# 2. PREPROCESAMIENTO Y LIMPIEZA
# -------------------------------------------------------------------
print("[*] Limpiando datos...")

# Filtrar target
target_col = 'estado_prestamo'
clase_0 = ['Pagado completamente']
clase_1 = ['Incobrable', 'Default', 'Retraso de 31 a 120 días']

df = df[df[target_col].isin(clase_0 + clase_1)].copy()
df['target'] = np.where(df[target_col].isin(clase_1), 1, 0)
y = df['target']

features_numericas = [
    'importe_solicitado', 
    'ingresos_anuales', 
    'ratio_prestamo_ingresos',
    'puntuacion_crediticia_media',
    'bancarrotas_publicas',
    'consultas_credito_ultimos_6_meses',
    'impago_ultimos_2_anios'
]
features_categoricas = [
    'finalidad_prestamo', 
    'antiguedad_laboral', 
    'grado_riesgo', 
    'tipo_vivienda', 
    'plazo_prestamo'
]

features_porcentaje = ['tipo_interes', 'porcentaje_uso_credito_revolving']
for col in features_porcentaje:
    if col in df.columns:
        df[col] = df[col].astype(str).str.replace('%', '').str.strip()
        df[col] = pd.to_numeric(df[col], errors='coerce')
        features_numericas.append(col)

cols_to_use = [c for c in features_numericas + features_categoricas if c in df.columns]
X = df[cols_to_use]
# Partición Train/Test
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
print(f"[*] Train shape: {X_train.shape}, Test shape: {X_test.shape}")

# Sub-división del conjunto de entrenamiento para calibración (Platt Scaling)
X_train_base, X_calib, y_train_base, y_train_calib = train_test_split(
    X_train, y_train, test_size=0.2, random_state=42, stratify=y_train
)
print(f"[*] Split Calibración: Train Base shape: {X_train_base.shape}, Calib shape: {X_calib.shape}")

# Calculamos el desbalanceo para XGBoost/LightGBM (basado en el conjunto de entrenamiento base)
spw = len(y_train_base[y_train_base == 0]) / len(y_train_base[y_train_base == 1])
print(f"[*] Ratio de desbalanceo calculado (Negativos/Positivos): {spw:.2f}")

# -------------------------------------------------------------------
# 3. TRANSFORMADORES
# -------------------------------------------------------------------
numeric_transformer = Pipeline(steps=[
    ('imputer', SimpleImputer(strategy='median')),
    ('scaler', StandardScaler())
])

categorical_transformer = Pipeline(steps=[
    ('imputer', SimpleImputer(strategy='most_frequent')),
    ('onehot', OneHotEncoder(handle_unknown='ignore'))
])

preprocessor = ColumnTransformer(
    transformers=[
        ('num', numeric_transformer, [c for c in features_numericas if c in X.columns]),
        ('cat', categorical_transformer, [c for c in features_categoricas if c in X.columns])
    ])

# -------------------------------------------------------------------
# 4. DEFINICIÓN DE MODELOS A COMPARAR
# -------------------------------------------------------------------
models = {
    "CatBoost": {
        "model": CatBoostClassifier(verbose=0, random_state=42),
        "params": {
            "classifier__iterations": [50, 100, 200],
            "classifier__depth": [4, 6, 8],
            "classifier__learning_rate": [0.01, 0.05, 0.1],
            "classifier__scale_pos_weight": [1.0, 2.0, 3.0, spw, spw * 1.5]
        }
    },
    "LightGBM": {
        "model": LGBMClassifier(random_state=42),
        "params": {
            "classifier__n_estimators": [50, 100, 200],
            "classifier__max_depth": [3, 5, 7],
            "classifier__learning_rate": [0.01, 0.05, 0.1],
            "classifier__scale_pos_weight": [1.0, 2.0, 3.0, spw, spw * 1.5]
        }
    },
    "XGBoost": {
        "model": XGBClassifier(use_label_encoder=False, eval_metric='logloss', random_state=42),
        "params": {
            "classifier__n_estimators": [50, 100, 200],
            "classifier__max_depth": [3, 5, 7],
            "classifier__learning_rate": [0.01, 0.05, 0.1],
            "classifier__scale_pos_weight": [1.0, 2.0, 3.0, spw, spw * 1.5]
        }
    }
}

# -------------------------------------------------------------------
# 5. ENTRENAMIENTO Y MIGRACIÓN DE TRACKING
# -------------------------------------------------------------------
best_global_score = 0
best_global_model = None
best_global_name = ""
local_runs_summary = []

print("[*] Iniciando comparación de modelos...")

for model_name, config in models.items():
    print(f"\n---> Entrenando {model_name}...")
    
    pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('classifier', config["model"])
    ])
    
    # Grid/Randomized Search para este modelo (optimizado para F1-Score)
    # Se ajusta sobre X_train_base/y_train_base para separar la calibración
    search = RandomizedSearchCV(
        pipeline,
        param_distributions=config["params"],
        n_iter=10, 
        cv=3,
        scoring='f1',
        n_jobs=-1,
        random_state=42
    )
    
    search.fit(X_train_base, y_train_base)
    
    best_pipeline = search.best_estimator_
    best_params = search.best_params_
    
    # Extraemos el preprocesador y el clasificador del mejor pipeline
    preprocessor_step = best_pipeline.named_steps['preprocessor']
    classifier_step = best_pipeline.named_steps['classifier']
    
    # Transformamos el set de calibración
    X_calib_trans = preprocessor_step.transform(X_calib)
    
    # Calibramos las probabilidades usando Platt Scaling (sigmoid) con cv='prefit'
    from sklearn.calibration import CalibratedClassifierCV
    calibrated_classifier = CalibratedClassifierCV(estimator=classifier_step, cv='prefit', method='sigmoid')
    calibrated_classifier.fit(X_calib_trans, y_train_calib)
    
    # Ensamblamos el pipeline final calibrado
    calibrated_pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor_step),
        ('classifier', calibrated_classifier)
    ])
    
    y_pred = calibrated_pipeline.predict(X_test)
    y_prob = calibrated_pipeline.predict_proba(X_test)[:, 1]
    
    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, y_prob))
    }
    
    print(f"[{model_name}] Mejores parámetros: {best_params}")
    print(f"[{model_name}] Métricas Calibradas en Test: ROC-AUC = {metrics['roc_auc']:.4f}, Recall = {metrics['recall']:.4f}, F1 = {metrics['f1']:.4f}")
    
    # Guardar localmente para fallback
    # Convertimos los parámetros a string para evitar problemas de tipos complejos
    cleaned_params = {k.replace("classifier__", ""): str(v) for k, v in best_params.items()}
    local_runs_summary.append({
        "name": model_name,
        "params": cleaned_params,
        "metrics": metrics
    })
    
    # Registro en Vertex AI Experiments
    if ai_initialized:
        try:
            run_uid = f"{model_name.lower()}-{random.randint(10000, 99999)}"
            print(f"[*] Registrando en Vertex AI Experiments: Run '{run_uid}'")
            aiplatform.start_run(run=run_uid)
            aiplatform.log_params(cleaned_params)
            aiplatform.log_metrics(metrics)
        except Exception as e:
            print(f"[!] Error al registrar en Vertex AI: {e}")
            
    # Selección del campeón: Mejor F1-Score. En caso de empate, desempate por ROC-AUC.
    is_better = False
    if metrics["f1"] > best_global_score:
        is_better = True
    elif abs(metrics["f1"] - best_global_score) < 1e-5:
        prev_champ = next((r for r in local_runs_summary[:-1] if r["name"] == best_global_name), None)
        if prev_champ:
            prev_auc = prev_champ["metrics"]["roc_auc"]
            if metrics["roc_auc"] > prev_auc:
                is_better = True
        else:
            is_better = True
            
    if is_better:
        best_global_score = metrics["f1"]
        best_global_model = calibrated_pipeline
        best_global_name = model_name

# Escribir el log local de runs para fallback offline
with open("local_runs.json", "w") as f:
    json.dump({
        "champion_name": best_global_name,
        "runs": local_runs_summary
    }, f, indent=4)
print("[*] Historial de ejecuciones locales guardado en local_runs.json.")

# -------------------------------------------------------------------
# 6. EXPLICABILIDAD DEL MODELO CON SHAP (GLOBAL Y LOCAL)
# -------------------------------------------------------------------
try:
    import shap
    print("\n[*] Iniciando cálculo de valores SHAP para el modelo campeón...")
    preprocessor = best_global_model.named_steps['preprocessor']
    classifier = best_global_model.named_steps['classifier']
    
    # Muestreo para SHAP (por velocidad y estabilidad)
    X_test_sample = X_test.sample(n=min(500, len(X_test)), random_state=42)
    X_test_sample_trans = preprocessor.transform(X_test_sample)
    if hasattr(X_test_sample_trans, "toarray"):
        X_test_sample_trans = X_test_sample_trans.toarray()
        
    feature_names = [f.replace('num__', '').replace('cat__', '') for f in preprocessor.get_feature_names_out()]
    # Extraer estimador base si está calibrado para usar TreeExplainer nativo
    if isinstance(classifier, CalibratedClassifierCV):
        base_tree_classifier = classifier.estimator
    else:
        base_tree_classifier = classifier
        
    model_type = type(base_tree_classifier).__name__
    print(f"[*] Tipo de modelo base campeón para SHAP: {model_type}")
    
    if "LGBM" in model_type or "XGB" in model_type or "CatBoost" in model_type:
        explainer = shap.TreeExplainer(base_tree_classifier)
        shap_values = explainer.shap_values(X_test_sample_trans)
    else:
        explainer = shap.Explainer(base_tree_classifier, X_test_sample_trans)
        shap_values = explainer(X_test_sample_trans)
        
    # Extraer clase 1 (Default/Impago)
    if isinstance(shap_values, list):
        shap_values_class1 = shap_values[1] if len(shap_values) == 2 else shap_values[0]
    elif hasattr(shap_values, "values"):
        vals = shap_values.values
        shap_values_class1 = vals[:, :, 1] if len(vals.shape) == 3 else vals
    else:
        shap_values_class1 = shap_values[:, :, 1] if len(shap_values.shape) == 3 else shap_values
        
    # 1. Importancia global
    mean_abs_shap = np.abs(shap_values_class1).mean(axis=0)
    sorted_global_indices = np.argsort(mean_abs_shap)[::-1]
    
    global_importance = []
    for idx in sorted_global_indices[:12]:
        global_importance.append({
            "feature": feature_names[idx],
            "importance": round(float(mean_abs_shap[idx]), 4)
        })
        
    # 2. Explicación local (Cliente de Alto Riesgo vs Cliente de Bajo Riesgo)
    probs = best_global_model.predict_proba(X_test_sample)[:, 1]
    high_risk_idx = int(np.argmax(probs))
    low_risk_idx = int(np.argmin(probs))
    
    def get_local_expl(idx, risk_label):
        row_trans = X_test_sample_trans[idx]
        row_shap = shap_values_class1[idx]
        
        sorted_indices = np.argsort(np.abs(row_shap))[::-1]
        
        factors = []
        for f_idx in sorted_indices[:6]:
            val = float(row_trans[f_idx])
            shap_val = float(row_shap[f_idx])
            factors.append({
                "feature": feature_names[f_idx],
                "value": round(val, 4),
                "shap": round(shap_val, 4),
                "effect": "Incrementa riesgo" if shap_val > 0 else "Reduce riesgo"
            })
            
        raw_row = X_test_sample.iloc[idx].to_dict()
        raw_row_clean = {k: (None if pd.isna(v) else v) for k, v in raw_row.items()}
        
        return {
            "risk_label": risk_label,
            "probability": round(float(probs[idx]) * 100, 2),
            "factors": factors,
            "raw_features": raw_row_clean
        }
        
    local_high = get_local_expl(high_risk_idx, "Alto Riesgo")
    local_low = get_local_expl(low_risk_idx, "Bajo Riesgo")
    
    shap_out = {
        "global": global_importance,
        "local": {
            "high_risk": local_high,
            "low_risk": local_low
        }
    }
    
    with open("shap_results.json", "w") as f:
        json.dump(shap_out, f, indent=4)
        
    print("[*] Valores SHAP calculados y exportados a shap_results.json exitosamente.")
except Exception as e:
    print(f"[!] Error al calcular valores SHAP: {e}")
    with open("shap_results.json", "w") as f:
        json.dump({"error": str(e)}, f)

# -------------------------------------------------------------------
# 7. EXPORTACIÓN DEL MODELO CAMPEÓN A VERTEX AI MODEL REGISTRY
# -------------------------------------------------------------------
print(f"\n[*] FINALIZADO. El mejor modelo (por F1-Score) ha sido: {best_global_name} con F1-Score de {best_global_score:.4f}")

# Serializar el modelo localmente en model.joblib
joblib.dump(best_global_model, "model.joblib")
print("[*] Modelo campeón guardado localmente como model.joblib.")

if ai_initialized and args.gcs_bucket:
    try:
        # Subir model.joblib al bucket de GCS
        gcs_model_dir = f"models/{best_global_name}"
        upload_to_gcs("model.joblib", args.gcs_bucket, f"{gcs_model_dir}/model.joblib")
        
        # Opcional: Subir shap_results.json
        if os.path.exists("shap_results.json"):
            upload_to_gcs("shap_results.json", args.gcs_bucket, f"{gcs_model_dir}/explainability/shap_results.json")
            
        print(f"[*] Registrando modelo '{best_global_name}' en Vertex AI Model Registry...")
        gcs_uri = f"gs://{args.gcs_bucket}/{gcs_model_dir}/"
        
        # Subir y registrar
        model = aiplatform.Model.upload(
            display_name=f"Champion_{best_global_name}_MVP_Balanced",
            artifact_uri=gcs_uri,
            serving_container_image_uri="us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-0:latest"
        )
        print(f"[*] Modelo registrado con éxito en Vertex AI Model Registry. ID: {model.resource_name}")
    except Exception as e:
        print(f"[!] Error al registrar modelo en Vertex AI Model Registry: {e}")
else:
    print("[*] Omitiendo registro en Vertex AI Model Registry (modo local o sin bucket GCS especificado).")

print("\n[*] Ejecución del pipeline concluida con éxito.")
