import pandas as pd
import numpy as np
import json
import os
import sys
import argparse
import httpx
from google.cloud import storage
import logging
from fastapi import FastAPI

# Inicialización de la aplicación FastAPI para el Dashboard
app = FastAPI(title="MLOps Monitoring Dashboard API")

# Configuración del entorno de BigQuery (Variables que usará tu API)
PROJECT_ID = os.getenv("PROJECT_ID", "tfm-ms-3")
BQ_DATASET_DASH = os.getenv("BQ_DATASET_DASH", "gubernatura_modelos")
DATASET_REF = f"{PROJECT_ID}.{BQ_DATASET_DASH}"

try:
    from google.cloud import bigquery
    bq_client = bigquery.Client(project=PROJECT_ID)
except Exception as e:
    bq_client = None
    print(f"[*] Ejecución local o sin cliente BigQuery inicializado de forma global: {e}")

def setup_logger():
    """Configura logger para imprimir resultados en formato BQQ."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )

def print_result(test_name, success, message=""):
    color = "\033[92m[OK]\033[0m" if success else "\033[91m[FAIL]\033[0m"
    log_message = f"{color} {test_name}: {message}"
    logging.info(log_message)

def save_results_to_gcs(bucket_name, result_data):
    """Guarda los resultados en Google Cloud Storage."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob('quality_test_results.json')
    blob.upload_from_string(json.dumps(result_data), content_type='application/json')
    print_result("Guardar Resultados", True, f"Resultados guardados en gs://{bucket_name}/quality_test_results.json.")

def trigger_dashboard(results, gcp_project, gcs_bucket):
    """Envía los resultados al dashboard.

    FIX: la app de FastAPI del dashboard solo expone GET en "/" y en
    "/metrics.json". Postear a la raíz devolvía 405 Method Not Allowed.
    Ahora se apunta al endpoint POST dedicado "/quality-results"
    (ver app.py del backend del dashboard).
    """
    DASHBOARD_URL = "https://dash-1076362823794.europe-west1.run.app/quality-results"
    payload = {
        "results": results,
        "gcp_project": gcp_project,
        "gcs_bucket": gcs_bucket
    }
    try:
        response = httpx.post(DASHBOARD_URL, json=payload, verify=False, timeout=30.0)
        if response.status_code in [200, 201]:
            print_result("Conexión al Dashboard", True, "Resultados enviados correctamente.")
        else:
            print_result("Conexión al Dashboard", False, f"{response.status_code} - {response.text}")
    except Exception as e:
        print_result("Conexión al Dashboard", False, str(e))

def trigger_cloud_build(trigger_url):
    """Dispara el trigger de Cloud Build inyectando credenciales OAuth2 por defecto.

    NOTA: si esto sigue devolviendo 403 PERMISSION_DENIED, es un problema de
    IAM, no de código. La cuenta de servicio que ejecuta este Cloud Run Job
    necesita el rol "roles/cloudbuild.builds.editor" (o un rol custom con el
    permiso "cloudbuild.builds.create") sobre el proyecto/trigger:

        gcloud run jobs describe <NOMBRE_JOB> --region=<REGION> \\
          --format="value(spec.template.spec.template.spec.serviceAccountName)"

        gcloud projects add-iam-policy-binding <PROJECT_ID> \\
          --member="serviceAccount:<SA_DEL_JOB>" \\
          --role="roles/cloudbuild.builds.editor"
    """
    try:
        import google.auth
        import google.auth.transport.requests

        credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)

        headers = {"Authorization": f"Bearer {credentials.token}"}
        response = httpx.post(trigger_url, headers=headers, timeout=30.0)

        if response.status_code in [200, 201, 202]:
            print_result("Trigger de Cloud Build", True, "Pipeline de reentrenamiento disparado correctamente.")
        else:
            print_result("Trigger de Cloud Build", False, f"Error al disparar el trigger: {response.status_code} - {response.text}")
    except Exception as e:
        print_result("Trigger de Cloud Build", False, f"Error al autenticar o conectar con Cloud Build: {e}")

def download_input_artifacts(model_bucket, model_prefix, raw_data_bucket, raw_data_prefix,
                              metrics_bucket, metrics_prefix):
    """Descarga a disco local los ficheros necesarios, cada uno desde su bucket/prefijo real.

    FIX: antes se asumía que df_completo_cr.csv y model.joblib vivían en el
    mismo bucket que gcs_bucket (models-artifacts-tfm) bajo el prefijo
    "preprocess". En realidad:
      - df_completo_cr.csv  -> bucket "raw-data-tfm"
      - model.joblib        -> bucket "models-artifacts-tfm", prefijo "models/XGBoost"
      - metrics.json        -> bucket "models-artifacts-tfm", prefijo "dash" (esto ya funcionaba)

    Verifica con `gsutil ls gs://models-artifacts-tfm/models/XGBoost/` el
    nombre exacto del fichero de modelo si no es literalmente "model.joblib".
    """
    expected_files = {
        "df_completo_cr.csv": (raw_data_bucket, raw_data_prefix),
        "model.joblib": (model_bucket, model_prefix),
        "metrics.json": (metrics_bucket, metrics_prefix),
    }

    try:
        client = storage.Client()
        downloaded = []
        not_found = []

        for filename, (bucket_name, prefix) in expected_files.items():
            if os.path.exists(filename):
                continue

            if not bucket_name:
                print_result("Descarga de Artefactos de Entrada", False,
                             f"No se especificó bucket para {filename}.")
                continue

            prefix = prefix.strip("/") if prefix else ""
            blob_path = f"{prefix}/{filename}" if prefix else filename

            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)

            if blob.exists():
                blob.download_to_filename(filename)
                downloaded.append(f"gs://{bucket_name}/{blob_path}")
            else:
                not_found.append(f"gs://{bucket_name}/{blob_path}")

        if downloaded:
            print_result("Descarga de Artefactos de Entrada", True, f"Descargados: {', '.join(downloaded)}")
        if not_found:
            print_result("Descarga de Artefactos de Entrada", False, f"No encontrados: {', '.join(not_found)}")
        if not downloaded and not not_found:
            print_result("Descarga de Artefactos de Entrada", True, "No se descargó nada nuevo (archivos ya locales).")
    except Exception as e:
        print_result("Descarga de Artefactos de Entrada", False, f"Error descargando artefactos: {e}")


# ===================================================================
# ENDPOINT PARA EL DASHBOARD FastAPI (Métricas dinámicas de BigQuery)
# ===================================================================
@app.get("/metrics.json")
async def get_dashboard_metrics():
    try:
        # 1. KPIs DEL MODELO CAMPEÓN EN PRODUCCIÓN (XGBoost por defecto)
        query_champion = f"""
            SELECT run_id, model_name, accuracy, precision, recall, f1_score, roc_auc,
                   pipeline_latency, pipeline_error_rate, fecha_registro
            FROM `{DATASET_REF}.t_modelo_campeon_kpis`
            ORDER BY fecha_registro DESC
            LIMIT 1
        """
        try:
            df_champ = bq_client.query(query_champion).to_dataframe() if bq_client else pd.DataFrame()
        except Exception as e:
            print(f"[!] Tabla t_modelo_campeon_kpis no disponible: {e}")
            df_champ = pd.DataFrame()

        if df_champ.empty:
            champion_data = {
                "model_name": "XGBoost",
                "metrics": {
                    "accuracy": 78.1,
                    "precision": 48.5,
                    "recall": 63.8,
                    "f1_score": 41.37,
                    "roc_auc": 76.5
                }
            }
            business_data = {"pipeline_latency": 45, "pipeline_error_rate": 0.05}
        else:
            row = df_champ.iloc[0]
            champion_data = {
                "model_name": row["model_name"],
                "metrics": {
                    "accuracy": float(row["accuracy"] * 100 if row["accuracy"] <= 1.0 else row["accuracy"]),
                    "precision": float(row["precision"] * 100 if row["precision"] <= 1.0 else row["precision"]),
                    "recall": float(row["recall"] * 100 if row["recall"] <= 1.0 else row["recall"]),
                    "f1_score": float(row["f1_score"] * 100 if row["f1_score"] <= 1.0 else row["f1_score"]),
                    "roc_auc": float(row["roc_auc"] * 100 if row["roc_auc"] <= 1.0 else row["roc_auc"])
                }
            }
            business_data = {
                "pipeline_latency": int(row["pipeline_latency"]) if not pd.isna(row["pipeline_latency"]) else 45,
                "pipeline_error_rate": float(row["pipeline_error_rate"]) if not pd.isna(row["pipeline_error_rate"]) else 0.0
            }

        # 2. COMPARATIVA DE MODELOS CANDIDATOS
        query_comp = f"""
            SELECT model_name, f1_score, roc_auc, accuracy, recall, es_campeon
            FROM `{DATASET_REF}.t_modelo_comparativa`
            ORDER BY f1_score DESC
        """
        try:
            df_comp = bq_client.query(query_comp).to_dataframe() if bq_client else pd.DataFrame()
        except Exception as e:
            print(f"[!] Tabla t_modelo_comparativa no disponible: {e}")
            df_comp = pd.DataFrame()

        comparison_list = []
        if df_comp.empty:
            comparison_list = [
                {"name": "XGBoost", "f1": 0.4137, "roc_auc": 0.765, "accuracy": 0.781, "recall": 0.638},
                {"name": "LightGBM", "f1": 0.4142, "roc_auc": 0.769, "accuracy": 0.785, "recall": 0.6412},
                {"name": "CatBoost", "f1": 0.4089, "roc_auc": 0.761, "accuracy": 0.779, "recall": 0.625}
            ]
        else:
            for _, r in df_comp.iterrows():
                comparison_list.append({
                    "name": r["model_name"],
                    "f1": float(r["f1_score"]),
                    "roc_auc": float(r["roc_auc"] / 100.0 if r["roc_auc"] > 1.0 else r["roc_auc"]),
                    "accuracy": float(r["accuracy"] / 100.0 if r["accuracy"] > 1.0 else r["accuracy"]),
                    "recall": float(r["recall"] / 100.0 if r["recall"] > 1.0 else r["recall"])
                })

        return {
            "champion": champion_data,
            "business": business_data,
            "comparative": comparison_list
        }
    except Exception as e:
        return {"error": str(e)}


def run_quality_tests():
    setup_logger()
    print("=" * 60)
    print(" INICIANDO PRUEBAS AUTOMÁTICAS DE CALIDAD DEL MODELO Y DATOS ")
    print("=" * 60)

    parser = argparse.ArgumentParser(description="Validador de calidad para Vertex AI / Local")
    parser.add_argument("--gcp-project", type=str, default=None, help="ID del Proyecto de Google Cloud")
    parser.add_argument("--gcp-location", type=str, default="europe-west1", help="Región de GCP")
    parser.add_argument("--gcs-bucket", type=str, required=True, help="Bucket de GCS para guardar los resultados y de donde cuelga metrics.json")
    parser.add_argument("--cloud-build-trigger-url", type=str, required=True, help="URL del trigger de Cloud Build")

    # --- Rutas de entrada (FIX: cada artefacto vive en un bucket/prefijo distinto) ---
    parser.add_argument("--gcs-model-bucket", type=str, default="models-artifacts-tfm",
                         help="Bucket donde vive el modelo entrenado.")
    parser.add_argument("--gcs-model-prefix", type=str, default="models/XGBoost",
                         help="Prefijo del modelo dentro de --gcs-model-bucket.")
    parser.add_argument("--gcs-raw-data-bucket", type=str, default="raw-data-tfm",
                         help="Bucket donde vive df_completo_cr.csv.")
    parser.add_argument("--gcs-raw-data-prefix", type=str, default="",
                         help="Prefijo del CSV dentro de --gcs-raw-data-bucket (vacío = raíz).")
    parser.add_argument("--gcs-metrics-prefix", type=str, default="dash",
                         help="Prefijo de metrics.json dentro de --gcs-bucket.")
    args, unknown = parser.parse_known_args()

    results = {}
    all_success = True
    metrics_path = "metrics.json"

    download_input_artifacts(
        model_bucket=args.gcs_model_bucket,
        model_prefix=args.gcs_model_prefix,
        raw_data_bucket=args.gcs_raw_data_bucket,
        raw_data_prefix=args.gcs_raw_data_prefix,
        metrics_bucket=args.gcs_bucket,
        metrics_prefix=args.gcs_metrics_prefix,
    )

    # -------------------------------------------------------------
    # TEST 1: Verificar existencia y esquema del Dataset (Estándar Único)
    # -------------------------------------------------------------
    data_path = "df_completo_cr.csv"
    if not os.path.exists(data_path):
        print_result("Test 1: Existencia de Dataset", False, "No se encontró el archivo df_completo_cr.csv.")
        results["Test 1"] = "Fail: No se encontró df_completo_cr.csv."
        all_success = False
    else:
        try:
            df_sample = pd.read_csv(data_path, sep=';', nrows=100)
            required_cols = ['estado_prestamo', 'importe_solicitado', 'ingresos_anuales']
            missing_cols = [c for c in required_cols if c not in df_sample.columns]

            if missing_cols:
                print_result("Test 1: Esquema de Datos", False, f"Columnas requeridas ausentes: {missing_cols}")
                results["Test 1"] = f"Fail: Columnas requeridas ausentes: {missing_cols}"
                all_success = False
            else:
                print_result("Test 1: Esquema de Datos", True, f"Dataset válido. {len(df_sample.columns)} columnas verificadas.")
                results["Test 1"] = "Pass: Dataset válido."
        except Exception as e:
            print_result("Test 1: Esquema de Datos", False, f"Error leyendo dataset: {e}")
            results["Test 1"] = f"Fail: Error leyendo dataset: {e}"
            all_success = False

    # -------------------------------------------------------------
    # TEST 2: Verificar calidad de métricas del modelo
    # -------------------------------------------------------------
    metrics = {}
    if not os.path.exists(metrics_path):
        print_result("Test 2: Umbrales de Rendimiento", False, "Archivo metrics.json no encontrado.")
        results["Test 2"] = "Fail: Archivo metrics.json no encontrado."
        all_success = False
    else:
        try:
            with open(metrics_path, "r") as f:
                metrics = json.load(f)

            champ_metrics = metrics["champion"]["metrics"]
            f1 = champ_metrics["f1_score"]
            roc_auc = champ_metrics["roc_auc"]
            recall = champ_metrics["recall"]

            MIN_F1, MIN_AUC, MIN_RECALL = 35.0, 65.0, 50.0

            f1_ok = f1 >= MIN_F1
            auc_ok = roc_auc >= MIN_AUC
            recall_ok = recall >= MIN_RECALL

            if f1_ok and auc_ok and recall_ok:
                print_result("Test 2: Umbrales de Rendimiento", True, f"F1-score={f1}% (Mín={MIN_F1}%), ROC-AUC={roc_auc}% (Mín={MIN_AUC}%), Recall={recall}% (Mín={MIN_RECALL}%)")
                results["Test 2"] = "Pass: Umbrales de rendimiento cumplidos."
            else:
                failures = []
                if not f1_ok: failures.append(f"F1-score {f1}% < {MIN_F1}%")
                if not auc_ok: failures.append(f"ROC-AUC {roc_auc}% < {MIN_AUC}%")
                if not recall_ok: failures.append(f"Recall {recall}% < {MIN_RECALL}%")
                print_result("Test 2: Umbrales de Rendimiento", False, f"Incumplimiento de umbral: {', '.join(failures)}")
                results["Test 2"] = f"Fail: Incumplimiento de umbral: {', '.join(failures)}"
                all_success = False
        except Exception as e:
            print_result("Test 2: Umbrales de Rendimiento", False, f"Error procesando métricas: {e}")
            results["Test 2"] = f"Fail: Error procesando métricas: {e}"
            all_success = False

    # -------------------------------------------------------------
    # TEST 3: Verificar límites de Data Drift (PSI < 0.25)
    # -------------------------------------------------------------
    # NOTA: si esto falla (PSI >= 0.25) no es un bug: el umbral se superó de
    # verdad y el test está haciendo su trabajo (dispara el retrain en el
    # bloque final). Es un fallo "esperado" del pipeline de monitorización,
    # no del código.
    drift_detected = False
    if os.path.exists(metrics_path) and metrics:
        try:
            psi_values = metrics["data_drift"]["psi"]
            features = metrics["data_drift"]["labels"]
            drift_critical = [f"{feat} (PSI={psi})" for feat, psi in zip(features, psi_values) if psi >= 0.25]

            if not drift_critical:
                max_psi = max(psi_values) if psi_values else 0
                print_result("Test 3: Límites de Data Drift", True, f"Sin drift crítico. PSI máximo: {max_psi}")
                results["Test 3"] = "Pass: Sin drift crítico."
            else:
                print_result("Test 3: Límites de Data Drift", False, f"Drift crítico detectado en: {', '.join(drift_critical)}")
                results["Test 3"] = f"Fail: Drift crítico en: {', '.join(drift_critical)}"
                all_success = False
                drift_detected = True
        except Exception as e:
            print_result("Test 3: Límites de Data Drift", False, f"Error validando PSI: {e}")
            results["Test 3"] = f"Fail: Error validando PSI: {e}"
            all_success = False

    # -------------------------------------------------------------
    # TEST 4: Disponibilidad del Modelo XGBoost Registrado
    # -------------------------------------------------------------
    gcp_checked = False
    try:
        from google.cloud import aiplatform
        aiplatform.init(project=args.gcp_project, location=args.gcp_location)
        models = aiplatform.Model.list()

        expected_display_name = "Champion_XGBoost_MVP_Balanced"
        matching_models = [m for m in models if m.display_name == expected_display_name]

        if matching_models:
            print_result("Test 4: Registro en Vertex AI Model Registry", True, f"Modelo '{expected_display_name}' localizado en Vertex AI.")
            results["Test 4"] = "Pass: Modelo XGBoost localizado en Vertex AI."
            gcp_checked = True
        else:
            print_result("Test 4: Registro en Vertex AI Model Registry", False, f"No se encontró el modelo '{expected_display_name}' en Vertex AI.")
            results["Test 4"] = f"Fail: No se encontró el modelo '{expected_display_name}' en Vertex AI."
            all_success = False
            gcp_checked = True
    except Exception as e:
        # FIX: antes este error se tragaba en silencio (except: pass), lo que
        # ocultaba si el fallo era de permisos/API en vez de "modelo no
        # encontrado". Ahora se registra explícitamente.
        print_result("Test 4: Consulta a Vertex AI", False, f"No se pudo consultar Vertex AI Model Registry: {e}")

    if not gcp_checked:
        model_file = "model.joblib"
        if os.path.exists(model_file):
            print_result("Test 4: Fallback de Modelo Local", True, f"Fichero local '{model_file}' localizado.")
            results["Test 4"] = "Pass: Fichero modelo local XGBoost encontrado."
        else:
            print_result("Test 4: Fallback de Modelo Local", False, f"No se encontró el fichero local '{model_file}'.")
            results["Test 4"] = f"Fail: No se encontró el fichero local '{model_file}'."
            all_success = False

    # -------------------------------------------------------------
    # TEST 5: Integración de Explicabilidad SHAP
    # -------------------------------------------------------------
    if os.path.exists(metrics_path) and metrics:
        try:
            shap_data = metrics.get("shap", {})
            if not shap_data or "error" in shap_data or "global" not in shap_data or "local" not in shap_data:
                print_result("Test 5: Integración de SHAP", False, "Mapeo SHAP ausente o corrupto.")
                results["Test 5"] = "Fail: Estructura SHAP inválida."
                all_success = False
            else:
                print_result("Test 5: Integración de SHAP", True, "SHAP global y local validados correctamente.")
                results["Test 5"] = "Pass: Integración de SHAP validada."
        except Exception as e:
            print_result("Test 5: Integración de SHAP", False, f"Error: {e}")
            all_success = False

    # -------------------------------------------------------------
    # TEST 6: Estructura del Análisis Exploratorio (EDA)
    # -------------------------------------------------------------
    if os.path.exists(metrics_path) and metrics:
        try:
            eda = metrics.get("eda", {})
            required_keys = ["dimensions", "nulls", "target_distribution", "descriptive_stats", "correlation"]
            if all(k in eda for k in required_keys):
                print_result("Test 6: Estructura de EDA", True, "Estructura analítica de EDA validada.")
                results["Test 6"] = "Pass: Estructura de EDA validada."
            else:
                print_result("Test 6: Estructura de EDA", False, "Faltan secciones estructuradas en el EDA.")
                all_success = False
        except Exception as e:
            all_success = False

    save_results_to_gcs(args.gcs_bucket, results)
    trigger_dashboard(results, args.gcp_project, args.gcs_bucket)

    if drift_detected:
        trigger_cloud_build(args.cloud_build_trigger_url)

    print("=" * 60)
    if all_success:
        print("\033[92m[ÉXITO] Todas las pruebas han pasado satisfactoriamente.\033[0m")
        sys.exit(0)
    else:
        print("\033[91m[ERROR] Algunas pruebas de calidad han fallado.\033[0m")
        sys.exit(1)

# Asegura que la ejecución directa ejecute los tests, permitiendo a la vez importar la app de FastAPI
if __name__ == "__main__":
    run_quality_tests()