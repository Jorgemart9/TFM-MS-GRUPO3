import pandas as pd
import numpy as np
import json
import os
import sys
import argparse
import httpx
from google.cloud import storage
import logging

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

def trigger_cloud_build(trigger_name_or_url, project_id, location):
    """Dispara el trigger de Cloud Build inyectando credenciales OAuth2 por defecto.
    
    Resuelve el UUID del trigger en GCP a partir de su nombre descriptivo
    y envía la rama por defecto ("main") en el cuerpo de la petición.
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
        
        # 1. Resolver el UUID del trigger
        trigger_id = trigger_name_or_url
        
        # Si parece una URL completa, intentamos extraer el nombre del trigger
        if trigger_name_or_url.startswith("http"):
            parts = trigger_name_or_url.split("/")
            if parts:
                last_part = parts[-1].split(":")[0]  # Obtiene 'reentrenar-modelo' de 'reentrenar-modelo:run'
                trigger_id = last_part

        # Si el trigger_id no parece un UUID (longitud ~36 y contiene guiones)
        if len(trigger_id) != 36 or "-" not in trigger_id:
            logging.info(f"[*] Buscando UUID del trigger con nombre: '{trigger_id}'...")
            resolved_id = None
            list_url = f"https://cloudbuild.googleapis.com/v1/projects/{project_id}/locations/{location}/triggers"
            list_response = httpx.get(list_url, headers=headers, timeout=30.0)
            if list_response.status_code == 200:
                triggers_data = list_response.json()
                for t in triggers_data.get("triggers", []):
                    if t.get("name") == trigger_id or t.get("id") == trigger_id:
                        resolved_id = t.get("id")
                        break
            if resolved_id:
                logging.info(f"[+] Trigger '{trigger_id}' resuelto a UUID: {resolved_id}")
                trigger_id = resolved_id
            else:
                logging.warning(f"[!] No se pudo resolver el trigger por nombre a UUID. Intentando llamar con: {trigger_id}")

        # 2. Ejecutar la llamada POST
        trigger_url = f"https://cloudbuild.googleapis.com/v1/projects/{project_id}/locations/{location}/triggers/{trigger_id}:run"
        payload = {
            "source": {
                "branchName": "main"
            }
        }
        
        logging.info(f"[*] Ejecutando POST a {trigger_url} con payload: {payload}")
        response = httpx.post(trigger_url, headers=headers, json=payload, timeout=30.0)

        if response.status_code in [200, 201, 202]:
            print_result("Trigger de Cloud Build", True, f"Pipeline de reentrenamiento ({trigger_id}) disparado correctamente.")
        else:
            logging.warning(f"[!] Falló el trigger (Código {response.status_code}). Intentando lanzar reentrenamiento directo (source-less build) en Cloud Build...")
            build_url = f"https://cloudbuild.googleapis.com/v1/projects/{project_id}/locations/{location}/builds"
            build_payload = {
                "serviceAccount": f"projects/{project_id}/serviceAccounts/sa-mlops-evaluator-v2@{project_id}.iam.gserviceaccount.com",
                "steps": [
                    {
                        "name": "gcr.io/google.com/cloudsdktool/cloud-sdk",
                        "entrypoint": "gcloud",
                        "args": [
                            "ai",
                            "custom-jobs",
                            "create",
                            f"--region={location}",
                            "--display-name=reentreno-vertex-job",
                            f"--worker-pool-spec=machine-type=n1-standard-4,container-image-uri={location}-docker.pkg.dev/{project_id}/training-repo/training-pipeline:latest",
                            f"--service-account=sa-vertex-train@{project_id}.iam.gserviceaccount.com"
                        ]
                    }
                ],
                "options": {
                    "logging": "CLOUD_LOGGING_ONLY"
                }
            }
            build_response = httpx.post(build_url, headers=headers, json=build_payload, timeout=30.0)
            if build_response.status_code in [200, 201, 202]:
                print_result("Trigger de Cloud Build (Fallback Directo)", True, "Build de reentrenamiento lanzado correctamente (sin origen).")
            else:
                print_result("Trigger de Cloud Build (Fallback Directo)", False, f"Error al lanzar build de reentrenamiento directo: {build_response.status_code} - {build_response.text}")
    except Exception as e:
        print_result("Trigger de Cloud Build", False, f"Error al autenticar o conectar con Cloud Build: {e}")

def download_input_artifacts(model_bucket, model_prefix, raw_data_bucket, raw_data_prefix,
                              metrics_bucket, metrics_prefix):
    """Descarga a disco local los ficheros necesarios, resolviendo dinámicamente el prefijo del modelo campeón."""
    client = storage.Client()
    
    # 1. Primero descargamos metrics.json para leer de ahí el nombre del modelo campeón
    metrics_filename = "metrics.json"
    metrics_prefix = metrics_prefix.strip("/") if metrics_prefix else ""
    metrics_blob_path = f"{metrics_prefix}/{metrics_filename}" if metrics_prefix else metrics_filename
    
    try:
        logging.info(f"[*] Descargando metrics.json desde gs://{metrics_bucket}/{metrics_blob_path}...")
        bucket = client.bucket(metrics_bucket)
        blob = bucket.blob(metrics_blob_path)
        if blob.exists():
            blob.download_to_filename(metrics_filename)
            print_result("Descarga de metrics.json", True, f"Descargado gs://{metrics_bucket}/{metrics_blob_path}")
        else:
            print_result("Descarga de metrics.json", False, f"No existe gs://{metrics_bucket}/{metrics_blob_path}")
    except Exception as e:
        print_result("Descarga de metrics.json", False, f"Error descargando metrics.json: {e}")

    # 2. Leer metrics.json si existe para obtener el modelo campeón actual y su prefijo dinámico
    resolved_model_prefix = model_prefix
    if os.path.exists(metrics_filename):
        try:
            with open(metrics_filename, "r") as f:
                metrics_data = json.load(f)
            champion_name = metrics_data.get("champion", {}).get("model_name")
            if champion_name:
                resolved_model_prefix = f"models/{champion_name}"
                logging.info(f"[+] Modelo campeón detectado: '{champion_name}'. Prefijo resuelto a: {resolved_model_prefix}")
        except Exception as e:
            logging.warning(f"[!] Error leyendo metrics.json para resolver prefijo del modelo: {e}. Fallback a: {model_prefix}")

    # 3. Descargar el modelo (el CSV ya no se necesita, se valida contra BigQuery)
    expected_files = {
        "model.joblib": (model_bucket, resolved_model_prefix),
    }

    try:
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


# API Endpoint para metrics.json eliminado por redundancia (el Dashboard consume desde dash/app.py)


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
    # TEST 1: Verificar existencia y esquema del Dataset Limpio en BigQuery
    # -------------------------------------------------------------
    bq_clean_table = f"{PROJECT_ID}.analytics_warehouse.df_completo_cr_clean_v2"
    try:
        if bq_client:
            query = f"SELECT * FROM `{bq_clean_table}` LIMIT 10"
            df_sample = bq_client.query(query).to_dataframe()
            required_cols = ['target', 'importe_solicitado', 'ingresos_anuales']
            missing_cols = [c for c in required_cols if c not in df_sample.columns]

            if missing_cols:
                print_result("Test 1: Esquema de Datos", False, f"Columnas requeridas ausentes en BQ: {missing_cols}")
                results["Test 1"] = f"Fail: Columnas requeridas ausentes: {missing_cols}"
                all_success = False
            elif df_sample.empty:
                print_result("Test 1: Esquema de Datos", False, f"Tabla {bq_clean_table} está vacía.")
                results["Test 1"] = f"Fail: Tabla vacía."
                all_success = False
            else:
                print_result("Test 1: Esquema de Datos", True, f"Dataset limpio válido en BigQuery. {len(df_sample.columns)} columnas verificadas.")
                results["Test 1"] = "Pass: Dataset limpio válido en BigQuery."
        else:
            print_result("Test 1: Esquema de Datos", False, "BigQuery client no disponible.")
            results["Test 1"] = "Fail: BigQuery client no disponible."
            all_success = False
    except Exception as e:
        print_result("Test 1: Esquema de Datos", False, f"Error consultando BigQuery: {e}")
        results["Test 1"] = f"Fail: Error consultando BigQuery: {e}"
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
            required_keys_prefixed = ["eda_dimensions", "eda_nulls", "eda_target_distribution", "eda_descriptive_stats", "eda_correlation"]
            if all(k in eda for k in required_keys) or all(k in eda for k in required_keys_prefixed):
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
        project_id = args.gcp_project or os.getenv("GCP_PROJECT") or os.getenv("PROJECT_ID") or "tfm-ms-3"
        location = args.gcp_location or "europe-west1"
        trigger_cloud_build(args.cloud_build_trigger_url, project_id, location)

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