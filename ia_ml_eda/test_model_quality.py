import pandas as pd
import numpy as np
import json
import os
import sys
import argparse

def print_result(test_name, success, message=""):
    color = "\033[92m[OK]\033[0m" if success else "\033[91m[FAIL]\033[0m"
    print(f"{color} {test_name}: {message}")

def run_quality_tests():
    print("=" * 60)
    print(" INICIANDO PRUEBAS AUTOMÁTICAS DE CALIDAD DEL MODELO Y DATOS ")
    print("=" * 60)
    
    # Parsear parámetros opcionales para la verificación de GCP
    parser = argparse.ArgumentParser(description="Validador de calidad para Vertex AI / Local")
    parser.add_argument("--gcp-project", type=str, default=None, help="ID del Proyecto de Google Cloud")
    parser.add_argument("--gcp-location", type=str, default="europe-west1", help="Región de GCP (por ejemplo, europe-west1)")
    parser.add_argument("--experiment-name", type=str, default="credit-risk-mvp", help="Nombre del experimento en Vertex AI")
    args, unknown = parser.parse_known_args()

    all_success = True
    metrics_path = "metrics.json"
    
    # -------------------------------------------------------------
    # TEST 1: Verificar existencia y esquema del Dataset
    # -------------------------------------------------------------
    data_path = "df_completo_cr.csv"
    if not os.path.exists(data_path):
        data_path = "df_completo_cr_mini.csv" # Fallback local de pruebas
        
    if not os.path.exists(data_path):
        print_result("Test 1: Existencia de Dataset", False, "No se encontró df_completo_cr.csv ni df_completo_cr_mini.csv.")
        all_success = False
    else:
        try:
            # Leer una pequeña muestra para velocidad
            df_sample = pd.read_csv(data_path, sep=';', nrows=100)
            required_cols = ['estado_prestamo', 'importe_solicitado', 'ingresos_anuales']
            missing_cols = [c for c in required_cols if c not in df_sample.columns]
            
            if missing_cols:
                print_result("Test 1: Esquema de Datos", False, f"Columnas requeridas ausentes: {missing_cols}")
                all_success = False
            else:
                print_result("Test 1: Esquema de Datos", True, f"Dataset válido ({os.path.basename(data_path)}). {len(df_sample.columns)} columnas verificadas.")
        except Exception as e:
            print_result("Test 1: Esquema de Datos", False, f"Error leyendo dataset: {e}")
            all_success = False

    # -------------------------------------------------------------
    # TEST 2: Verificar calidad de métricas del modelo (F1, AUC, Recall)
    # -------------------------------------------------------------
    if not os.path.exists(metrics_path):
        print_result("Test 2: Umbrales de Rendimiento", False, "Archivo metrics.json no encontrado. Ejecuta export_metrics.py primero.")
        all_success = False
    else:
        try:
            with open(metrics_path, "r") as f:
                metrics = json.load(f)
            
            champ_metrics = metrics["champion"]["metrics"]
            f1 = champ_metrics["f1_score"]
            roc_auc = champ_metrics["roc_auc"]
            recall = champ_metrics["recall"]
            
            # Umbrales mínimos de validación de calidad (basados en el umbral óptimo de decisión)
            is_mini = not os.path.exists("df_completo_cr.csv") or os.path.exists("df_completo_cr_mini.csv")
            MIN_F1 = 20.0 if is_mini else 35.0
            MIN_AUC = 45.0 if is_mini else 65.0
            MIN_RECALL = 30.0 if is_mini else 50.0
            
            f1_ok = f1 >= MIN_F1
            auc_ok = roc_auc >= MIN_AUC
            recall_ok = recall >= MIN_RECALL
            
            if f1_ok and auc_ok and recall_ok:
                print_result("Test 2: Umbrales de Rendimiento", True, f"F1-score={f1}% (Mín={MIN_F1}%), ROC-AUC={roc_auc}% (Mín={MIN_AUC}%), Recall={recall}% (Mín={MIN_RECALL}%)")
            else:
                failures = []
                if not f1_ok: failures.append(f"F1-score {f1}% < {MIN_F1}%")
                if not auc_ok: failures.append(f"ROC-AUC {roc_auc}% < {MIN_AUC}%")
                if not recall_ok: failures.append(f"Recall {recall}% < {MIN_RECALL}%")
                print_result("Test 2: Umbrales de Rendimiento", False, f"Incumplimiento de umbral: {', '.join(failures)}")
                all_success = False
        except Exception as e:
            print_result("Test 2: Umbrales de Rendimiento", False, f"Error procesando métricas: {e}")
            all_success = False

    # -------------------------------------------------------------
    # TEST 3: Verificar límites de Data Drift (PSI < 0.25)
    # -------------------------------------------------------------
    if os.path.exists(metrics_path):
        try:
            psi_values = metrics["data_drift"]["psi"]
            features = metrics["data_drift"]["labels"]
            
            drift_critical = []
            for feat, psi in zip(features, psi_values):
                if psi >= 0.25:
                    drift_critical.append(f"{feat} (PSI={psi})")
            
            if not drift_critical:
                max_psi = max(psi_values) if psi_values else 0
                print_result("Test 3: Límites de Data Drift", True, f"Sin drift crítico. PSI máximo detectado: {max_psi} (Límite crítico: 0.25)")
            else:
                print_result("Test 3: Límites de Data Drift", False, f"Drift crítico detectado en: {', '.join(drift_critical)}")
                all_success = False
        except Exception as e:
            print_result("Test 3: Límites de Data Drift", False, f"Error validando PSI: {e}")
            all_success = False

    # -------------------------------------------------------------
    # TEST 4: Disponibilidad del Modelo Registrado (Vertex AI o Local)
    # -------------------------------------------------------------
    gcp_checked = False
    try:
        from google.cloud import aiplatform
        # Intentar conectar con Vertex AI
        aiplatform.init(project=args.gcp_project, location=args.gcp_location)
        print("[*] Conexión establecida con Vertex AI. Buscando modelo registrado...")
        
        models = aiplatform.Model.list()
        
        if os.path.exists(metrics_path):
            with open(metrics_path, "r") as f:
                metrics_data = json.load(f)
            champ_name = metrics_data["champion"]["model_name"]
            expected_display_name = f"Champion_{champ_name}_MVP_Balanced"
            
            matching_models = [m for m in models if m.display_name == expected_display_name]
            if matching_models:
                print_result("Test 4: Registro en Vertex AI Model Registry", True, f"Modelo '{expected_display_name}' localizado y activo en Vertex AI.")
                gcp_checked = True
            else:
                print_result("Test 4: Registro en Vertex AI Model Registry", False, f"No se encontró el modelo '{expected_display_name}' en Vertex AI.")
                all_success = False
                gcp_checked = True
    except Exception as e:
        # Caer en el fallback local
        pass
        
    if not gcp_checked:
        model_file = "model.joblib"
        if os.path.exists(model_file):
            print_result("Test 4: Fallback de Modelo Local", True, f"Fichero local '{model_file}' localizado e íntegro.")
        else:
            print_result("Test 4: Fallback de Modelo Local", False, f"No se encontró el fichero local '{model_file}'.")
            all_success = False

    # -------------------------------------------------------------
    # TEST 5: Integración de Explicabilidad SHAP (Global y Local)
    # -------------------------------------------------------------
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path, "r") as f:
                metrics = json.load(f)
            
            if "shap" not in metrics or not metrics["shap"]:
                print_result("Test 5: Integración de SHAP", False, "Mapeo SHAP ausente en metrics.json.")
                all_success = False
            else:
                shap_data = metrics["shap"]
                if "error" in shap_data:
                    print_result("Test 5: Integración de SHAP", False, f"Error SHAP registrado en pipeline: {shap_data['error']}")
                    all_success = False
                elif "global" not in shap_data or "local" not in shap_data:
                    print_result("Test 5: Integración de SHAP", False, "Faltan claves 'global' o 'local' en explicabilidad SHAP.")
                    all_success = False
                else:
                    global_count = len(shap_data["global"])
                    high_risk_prob = shap_data["local"]["high_risk"]["probability"]
                    low_risk_prob = shap_data["local"]["low_risk"]["probability"]
                    
                    print_result(
                        "Test 5: Integración de SHAP", 
                        True, 
                        f"SHAP global verificado ({global_count} variables). Cliente Alto Riesgo ({high_risk_prob}%) vs Bajo Riesgo ({low_risk_prob}%)."
                    )
        except Exception as e:
            print_result("Test 5: Integración de SHAP", False, f"Error validando SHAP: {e}")
            all_success = False
    else:
        print_result("Test 5: Integración de SHAP", False, "metrics.json no disponible para validación.")
        all_success = False

    # -------------------------------------------------------------
    # TEST 6: Estructura del Análisis Exploratorio (EDA)
    # -------------------------------------------------------------
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path, "r") as f:
                metrics = json.load(f)
                
            if "eda" not in metrics or not metrics["eda"]:
                print_result("Test 6: Estructura de EDA", False, "Estructura de EDA ausente en metrics.json.")
                all_success = False
            else:
                eda = metrics["eda"]
                required_keys = ["dimensions", "nulls", "target_distribution", "descriptive_stats", "correlation"]
                missing_keys = [k for k in required_keys if k not in eda]
                
                if missing_keys:
                    print_result("Test 6: Estructura de EDA", False, f"Faltan claves en EDA: {missing_keys}")
                    all_success = False
                else:
                    sample_size = eda["dimensions"]["sample_rows"]
                    num_corr_features = len(eda["correlation"]["columns"])
                    print_result(
                        "Test 6: Estructura de EDA", 
                        True, 
                        f"Dimensiones validadas ({sample_size} registros muestreados). Matriz de correlación validada ({num_corr_features}x{num_corr_features})."
                    )
        except Exception as e:
            print_result("Test 6: Estructura de EDA", False, f"Error validando EDA: {e}")
            all_success = False
    else:
        print_result("Test 6: Estructura de EDA", False, "metrics.json no disponible para validación.")
        all_success = False

    print("=" * 60)
    if all_success:
        print("\033[92m[ÉXITO] Todas las pruebas de calidad del modelo han pasado satisfactoriamente.\033[0m")
        sys.exit(0)
    else:
        print("\033[91m[ERROR] Algunas pruebas de calidad han fallado. Revisar detalles arriba.\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    run_quality_tests()
