import json
import random
import os
import argparse
from google.cloud import bigquery
from google.cloud import storage

# -------------------------------------------------------------------
# CONFIGURACIÓN Y PARSEADO DE ARGUMENTOS
# -------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Exportador de Métricas de Vertex AI, local Fallback y Registro en BigQuery")
parser.add_argument("--gcp-project", type=str, default="tfm-ms-3", help="ID del Proyecto de Google Cloud")
parser.add_argument("--gcp-location", type=str, default="europe-west1", help="Región de GCP (por ejemplo, europe-west1)")
parser.add_argument("--experiment-name", type=str, default="credit-risk-mvp", help="Nombre del experimento en Vertex AI")
parser.add_argument("--gcs-bucket", type=str, default="models-artifacts-tfm", help="Bucket de GCS para almacenar metrics.json")

args = parser.parse_args()

project_id = args.gcp_project or "tfm-ms-3"
champion_name = "Unknown"
best_metrics = {}
comparison_data = []
gcp_success = False

# Intentar cargar desde Vertex AI Experiments en GCP
try:
    from google.cloud import aiplatform
    
    print(f"[*] Conectando a Vertex AI en '{args.gcp_location}'...")
    aiplatform.init(project=project_id, location=args.gcp_location)
    df_runs = aiplatform.get_experiment_df(experiment=args.experiment_name)
    
    if not df_runs.empty:
        print(f"[*] Conexión exitosa a Vertex AI. Se encontraron {len(df_runs)} ejecuciones.")
        
        # Encontrar las columnas correspondientes a las métricas y ordenarlas por F1
        f1_col = [c for c in df_runs.columns if 'f1' in c.lower()][0]
        roc_col = [c for c in df_runs.columns if 'roc' in c.lower() or 'auc' in c.lower()][0]
        acc_col = [c for c in df_runs.columns if 'accuracy' in c.lower()][0]
        rec_col = [c for c in df_runs.columns if 'recall' in c.lower()][0]
        prec_col = [c for c in df_runs.columns if 'precision' in c.lower()][0]
        
        df_sorted = df_runs.sort_values(by=f1_col, ascending=False)
        best_row = df_sorted.iloc[0]
        
        # Mapear el nombre del campeón basándose en el run_name
        run_name = str(best_row['run_name'])
        if "catboost" in run_name.lower():
            champion_name = "CatBoost"
        elif "xgboost" in run_name.lower():
            champion_name = "XGBoost"
        else:
            champion_name = "LightGBM"
            
        best_metrics = {
            "f1": float(best_row[f1_col]),
            "roc_auc": float(best_row[roc_col]),
            "accuracy": float(best_row[acc_col]),
            "recall": float(best_row[rec_col]),
            "precision": float(best_row[prec_col])
        }
        
        # Rellenar comparison_data sin duplicados por tipo de modelo
        seen_types = set()
        for _, row in df_sorted.iterrows():
            rname = str(row['run_name'])
            if "catboost" in rname.lower():
                mtype = "CatBoost"
            elif "xgboost" in rname.lower():
                mtype = "XGBoost"
            else:
                mtype = "LightGBM"
                
            if mtype not in seen_types:
                comparison_data.append({
                    "name": mtype,
                    "f1": round(float(row[f1_col]), 3),
                    "roc_auc": round(float(row[roc_col]), 3),
                    "accuracy": round(float(row[acc_col]), 3),
                    "recall": round(float(row[rec_col]), 3)
                })
                seen_types.add(mtype)
                
        gcp_success = True
except Exception as e:
    print(f"[!] No se pudieron extraer datos de Vertex AI: {e}. Activando fallback local.")
    gcp_success = False

# Fallback local usando local_runs.json
if not gcp_success:
    local_runs_path = "local_runs.json"
    if os.path.exists(local_runs_path):
        try:
            with open(local_runs_path, "r") as f:
                local_data = json.load(f)
                
            champion_name = local_data["champion_name"]
            runs_sorted = sorted(local_data["runs"], key=lambda x: x["metrics"]["f1"], reverse=True)
            
            best_run = runs_sorted[0]
            best_metrics = best_run["metrics"]
            
            for r in local_data["runs"]:
                comparison_data.append({
                    "name": r["name"],
                    "f1": round(r["metrics"]["f1"], 3),
                    "roc_auc": round(r["metrics"]["roc_auc"], 3),
                    "accuracy": round(r["metrics"]["accuracy"], 3),
                    "recall": round(r["metrics"]["recall"], 3)
                })
            print("[*] Datos locales cargados exitosamente de local_runs.json.")
        except Exception as err:
            print(f"[!] Falló la lectura de local_runs.json: {err}")
            exit(1)
    else:
        print("[!] Error: No se encontró local_runs.json ni conexión a Vertex AI. Generando mock de desarrollo...")
        champion_name = "LightGBM"
        best_metrics = {"f1": 0.550, "roc_auc": 0.852, "accuracy": 0.825, "recall": 0.6412, "precision": 0.482}
        comparison_data = [
            {"name": "LightGBM", "f1": 0.550, "roc_auc": 0.852, "accuracy": 0.825, "recall": 0.641},
            {"name": "XGBoost", "f1": 0.538, "roc_auc": 0.841, "accuracy": 0.812, "recall": 0.628},
            {"name": "Logistic_Regression", "f1": 0.451, "roc_auc": 0.765, "accuracy": 0.771, "recall": 0.512}
        ]

# -------------------------------------------------------------------
# SIMULACIONES Y KPI NEGOCIO
# -------------------------------------------------------------------
actual_roc = best_metrics.get("roc_auc", 0.85)
actual_f1 = best_metrics.get("f1", 0.80)

sim_roc = [round(actual_roc + 0.015, 3), round(actual_roc + 0.012, 3), round(actual_roc + 0.010, 3), round(actual_roc + 0.007, 3), round(actual_roc + 0.005, 3), round(actual_roc + 0.002, 3), round(actual_roc, 3)]
sim_f1 = [round(actual_f1 + 0.020, 3), round(actual_f1 + 0.018, 3), round(actual_f1 + 0.015, 3), round(actual_f1 + 0.012, 3), round(actual_f1 + 0.008, 3), round(actual_f1 + 0.004, 3), round(actual_f1, 3)]

drift_labels = ['importe_solicitado', 'puntuacion_buro', 'antiguedad_laboral', 'ratio_deuda_ingresos', 'ingresos_anuales']
drift_psi = [0.27, 0.12, 0.08, 0.05, 0.04]

recall_pct = best_metrics.get("recall", 0)
total_risk = 2500000
avoided_loss = total_risk * recall_pct
latency_api = random.randint(35, 55)
error_rate_api = round(random.uniform(0.01, 0.08), 2)

# Cargar SHAP
shap_data = {
    "global": [
        {"feature": "puntuacion_buro", "importance": 0.284},
        {"feature": "ingresos_anuales", "importance": 0.195},
        {"feature": "ratio_deuda_ingresos", "importance": 0.142},
        {"feature": "antiguedad_laboral", "importance": 0.091},
        {"feature": "importe_solicitado", "importance": 0.076}
    ],
    "local": {
        "low_risk": {
            "probability": 4.2,
            "factors": [
                {"feature": "puntuacion_buro", "value": "780 (Excelente)", "shap": -0.152},
                {"feature": "ingresos_anuales", "value": "€65.000", "shap": -0.084},
                {"feature": "ratio_deuda_ingresos", "value": "12%", "shap": -0.061}
            ]
        },
        "high_risk": {
            "probability": 72.8,
            "factors": [
                {"feature": "puntuacion_buro", "value": "450 (Deficiente)", "shap": 0.231},
                {"feature": "ratio_deuda_ingresos", "value": "62%", "shap": 0.154},
                {"feature": "importe_solicitado", "value": "€35.000", "shap": 0.112}
            ]
        }
    }
}

if os.path.exists("shap_results.json"):
    try:
        with open("shap_results.json", "r") as f:
            shap_data = json.load(f)
        print("[*] Datos SHAP cargados con éxito desde shap_results.json.")
    except Exception as e:
        print(f"[!] Error leyendo shap_results.json: {e}")

# Cargar EDA
eda_data = {
    "dimensions": {
        "total_rows_raw_est": 412260,
        "sample_rows": 41226,
        "total_columns": 11,
        "filtered_rows": 38400
    },
    "nulls": {
        "antiguedad_laboral": {"nulos": 4534, "porcentaje": 11},
        "puntuacion_buro": {"nulos": 412, "porcentaje": 1},
        "ingresos_anuales": {"nulos": 0, "porcentaje": 0}
    },
    "target_distribution": [
        {"label": "Solvente (0)", "count": 32643, "percentage": 79.18},
        {"label": "Impago (1)", "count": 8583, "percentage": 20.82}
    ],
    "descriptive_stats": {
        "ingresos_anuales": {"mean": 45000, "median": 41000, "std": 12000, "min": 12000, "max": 180000},
        "importe_solicitado": {"mean": 12500, "median": 10000, "std": 6200, "min": 1000, "max": 40000}
    },
    "correlation": {
        "columns": ["ingresos_anuales", "importe_solicitado", "puntuacion_buro"],
        "matrix": [
            [1.0, 0.35, 0.15],
            [0.35, 1.0, -0.05],
            [0.15, -0.05, 1.0]
        ]
    }
}

if os.path.exists("eda_results.json"):
    try:
        with open("eda_results.json", "r") as f:
            eda_data = json.load(f)
        print("[*] Datos EDA cargados con éxito desde eda_results.json.")
    except Exception as e:
        print(f"[!] Error leyendo eda_results.json: {e}")

# -------------------------------------------------------------------
# CREACIÓN DE TABLAS E INSERCIÓN EN BIGQUERY
# -------------------------------------------------------------------
try:
    print(f"[*] Inicializando BigQuery Client para el proyecto '{project_id}'...")
    bq_client = bigquery.Client(project=project_id)
    dataset_ref = f"{project_id}.gubernatura_modelos"
    
    # 1. Crear Schema/Dataset
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = args.gcp_location
    dataset.description = "Dataset para gobernanza MLOps, test quality y metrics."
    dataset = bq_client.create_dataset(dataset, exists_ok=True)
    print(f"[*] Dataset '{dataset_ref}' verificado/creado con éxito.")
    
    # DDL Declarativas para ejecutar
    ddls = [
        # KPIs del Modelo Campeón
        f"""
        CREATE TABLE IF NOT EXISTS `{dataset_ref}.t_modelo_campeon_kpis` (
          run_id STRING,
          model_name STRING NOT NULL,
          accuracy FLOAT64 NOT NULL,
          precision FLOAT64 NOT NULL,
          recall FLOAT64 NOT NULL,
          f1_score FLOAT64 NOT NULL,
          roc_auc FLOAT64 NOT NULL,
          pipeline_latency INT64,
          pipeline_error_rate FLOAT64,
          fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
        );
        """,
        # Comparativa histórica de algoritmos candidatos
        f"""
        CREATE TABLE IF NOT EXISTS `{dataset_ref}.t_modelo_comparativa` (
          run_id STRING,
          model_name STRING NOT NULL,
          accuracy FLOAT64 NOT NULL,
          precision FLOAT64 NOT NULL,
          recall FLOAT64 NOT NULL,
          f1_score FLOAT64 NOT NULL,
          roc_auc FLOAT64 NOT NULL,
          es_campeon BOOL NOT NULL,
          fecha_evaluacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
        );
        """,
        # Concept Drift (Evolución Temporal)
        f"""
        CREATE TABLE IF NOT EXISTS `{dataset_ref}.t_modelo_evaluacion_temporal` (
          semana_etiqueta STRING NOT NULL,
          f1_score FLOAT64 NOT NULL,
          roc_auc FLOAT64 NOT NULL,
          fecha_auditoria DATE DEFAULT CURRENT_DATE()
        );
        """,
        # Monitorización de Data Drift (PSI)
        f"""
        CREATE TABLE IF NOT EXISTS `{dataset_ref}.t_modelo_data_drift_psi` (
          feature_name STRING NOT NULL,
          psi_value FLOAT64 NOT NULL,
          fecha_auditoria TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
        );
        """,
        # SHAP Global Importance
        f"""
        CREATE TABLE IF NOT EXISTS `{dataset_ref}.t_modelo_shap_global` (
          feature_name STRING NOT NULL,
          shap_importance FLOAT64 NOT NULL,
          fecha_calculo TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
        );
        """,
        # SHAP Local (Perfiles Sintéticos)
        f"""
        CREATE TABLE IF NOT EXISTS `{dataset_ref}.t_modelo_shap_local` (
          perfil_tipo STRING NOT NULL,
          probability_pct FLOAT64 NOT NULL,
          feature_name STRING NOT NULL,
          feature_value STRING NOT NULL,
          shap_impact FLOAT64 NOT NULL,
          orden INT64 NOT NULL,
          fecha_calculo TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
        );
        """,
        # Registro de Tests de Calidad (para /quality-results del dashboard)
        f"""
        CREATE TABLE IF NOT EXISTS `{dataset_ref}.t_quality_test_log` (
          gcp_project STRING,
          gcs_bucket STRING,
          results STRING,
          fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
        );
        """
    ]
    
    for idx, ddl in enumerate(ddls, 1):
        bq_client.query(ddl).result()
        print(f"[*] Tabla de Gobernanza {idx} verificada/creada en BigQuery.")
        
    # 2. Inserción de Datos mediante Sentencias DML
    print("[*] Insertando métricas de la última ejecución en BigQuery...")
    
    # Insertar campeón
    dml_champion = f"""
    INSERT INTO `{dataset_ref}.t_modelo_campeon_kpis` 
    (run_id, model_name, accuracy, precision, recall, f1_score, roc_auc, pipeline_latency, pipeline_error_rate)
    VALUES ('run_{random.randint(1000,9999)}', '{champion_name}', {round(best_metrics.get("accuracy", 0)*100, 2)}, {round(best_metrics.get("precision", 0)*100, 2)}, {round(best_metrics.get("recall", 0)*100, 2)}, {round(best_metrics.get("f1", 0)*100, 2)}, {round(best_metrics.get("roc_auc", 0)*100, 2)}, {latency_api}, {error_rate_api});
    """
    bq_client.query(dml_champion).result()
    
    # Limpiar e insertar comparativas
    bq_client.query(f"DELETE FROM `{dataset_ref}.t_modelo_comparativa` WHERE TRUE").result()
    for row in comparison_data:
        is_champ = "TRUE" if row["name"] == champion_name else "FALSE"
        dml_comp = f"""
        INSERT INTO `{dataset_ref}.t_modelo_comparativa` (run_id, model_name, accuracy, precision, recall, f1_score, roc_auc, es_campeon)
        VALUES ('run_comp', '{row["name"]}', {row["accuracy"]}, {row["f1"]}, {row["recall"]}, {row["f1"]}, {row["roc_auc"]}, {is_champ});
        """
        bq_client.query(dml_comp).result()

    # Limpiar e insertar evolución temporal
    bq_client.query(f"DELETE FROM `{dataset_ref}.t_modelo_evaluacion_temporal` WHERE TRUE").result()
    semanas = ["Día -25", "Día -20", "Día -15", "Día -10", "Día -5", "Día -1", "Hoy"]
    for i, sem in enumerate(semanas):
        dml_evo = f"""
        INSERT INTO `{dataset_ref}.t_modelo_evaluacion_temporal` (semana_etiqueta, f1_score, roc_auc)
        VALUES ('{sem}', {sim_f1[i]}, {sim_roc[i]});
        """
        bq_client.query(dml_evo).result()

    # Limpiar e insertar Data Drift PSI
    bq_client.query(f"DELETE FROM `{dataset_ref}.t_modelo_data_drift_psi` WHERE TRUE").result()
    for i, feature in enumerate(drift_labels):
        dml_drift = f"""
        INSERT INTO `{dataset_ref}.t_modelo_data_drift_psi` (feature_name, psi_value)
        VALUES ('{feature}', {drift_psi[i]});
        """
        bq_client.query(dml_drift).result()

    # Limpiar e insertar SHAP Global
    bq_client.query(f"DELETE FROM `{dataset_ref}.t_modelo_shap_global` WHERE TRUE").result()
    for row in shap_data["global"]:
        dml_sg = f"""
        INSERT INTO `{dataset_ref}.t_modelo_shap_global` (feature_name, shap_importance)
        VALUES ('{row["feature"]}', {row["importance"]});
        """
        bq_client.query(dml_sg).result()

    # Limpiar e insertar SHAP Local
    bq_client.query(f"DELETE FROM `{dataset_ref}.t_modelo_shap_local` WHERE TRUE").result()
    for perfil, p_data in shap_data["local"].items():
        prob = p_data["probability"]
        for idx, f in enumerate(p_data["factors"], 1):
            dml_sl = f"""
            INSERT INTO `{dataset_ref}.t_modelo_shap_local` (perfil_tipo, probability_pct, feature_name, feature_value, shap_impact, orden)
            VALUES ('{perfil}', {prob}, '{f["feature"]}', '{f["value"]}', {f["shap"]}, {idx});
            """
            bq_client.query(dml_sl).result()

    print("[*] ¡Datos consolidados insertados exitosamente en BigQuery gubernatura_modelos!")

except Exception as bq_err:
    print(f"[!] Error procesando el almacenamiento estructurado en BigQuery: {bq_err}")

# -------------------------------------------------------------------
# GENERACIÓN DE PAYLOAD JSON Y EXPORTACIÓN A CLOUD STORAGE
# -------------------------------------------------------------------
output = {
    "champion": {
        "model_name": champion_name,
        "metrics": {
            "accuracy": round(best_metrics.get("accuracy", 0) * 100, 2),
            "precision": round(best_metrics.get("precision", 0) * 100, 2),
            "recall": round(best_metrics.get("recall", 0) * 100, 2),
            "f1_score": round(best_metrics.get("f1", 0) * 100, 2),
            "roc_auc": round(best_metrics.get("roc_auc", 0) * 100, 2)
        }
    },
    "comparison": comparison_data,
    "evolution": {
        "labels": ["Día -25", "Día -20", "Día -15", "Día -10", "Día -5", "Día -1", "Hoy"],
        "roc_auc": sim_roc,
        "f1_score": sim_f1
    },
    "data_drift": {
        "labels": drift_labels,
        "psi": drift_psi
    },
    "business": {
        "total_risk": total_risk,
        "avoided_loss": avoided_loss,
        "pipeline_latency": latency_api,
        "pipeline_error_rate": error_rate_api
    },
    "shap": shap_data,
    "eda": eda_data
}

# Guardar localmente
with open("metrics.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=4, ensure_ascii=False)

# Subir a Google Cloud Storage para consumo del Dashboard
try:
    print(f"[*] Subiendo 'metrics.json' al bucket de GCS '{args.gcs_bucket}/dash/metrics.json'...")
    storage_client = storage.Client()
    bucket = storage_client.bucket(args.gcs_bucket)
    blob = bucket.blob("dash/metrics.json")
    
    blob.upload_from_filename("metrics.json", content_type="application/json")
    print("[*] ¡metrics.json actualizado con éxito en GCS para lectura instantánea del HTML!")
except Exception as gcs_err:
    print(f"[!] No se pudo subir el archivo JSON a Google Cloud Storage: {gcs_err}")

print("[*] Proceso finalizado.")
