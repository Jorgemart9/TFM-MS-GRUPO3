import pandas as pd
import numpy as np
import json
import os
import random
import argparse
import io

# Intentar importar las librerías de GCP
gcp_active = False
try:
    from google.cloud import storage
    gcp_active = True
except ImportError:
    print("[!] google-cloud-storage no está instalado. Operando en modo Local Fallback.")

# -------------------------------------------------------------------
# 1. CONFIGURACIÓN Y PARSEADO DE ARGUMENTOS
# -------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Pipeline de Preprocesamiento y EDA para Cloud Run / Local")
parser.add_argument("--input-path", type=str, default=None, help="Ruta del CSV original 'sucio' (GCS gs://... o local)")
parser.add_argument("--output-clean-path", type=str, default=None, help="Ruta de destino del CSV limpio (GCS gs://... o local)")
parser.add_argument("--output-eda-path", type=str, default=None, help="Ruta de destino del JSON analítico de EDA (GCS gs://... o local)")
parser.add_argument("--sample-fraction", type=float, default=0.10, help="Fracción de muestreo para estadísticas del EDA")
parser.add_argument("--gcp-project", type=str, default=None, help="ID del Proyecto de Google Cloud")

args = parser.parse_args()

# Establecer fallbacks por defecto para desarrollo local
input_path = args.input_path
if not input_path:
    input_path = "df_completo_cr.csv"
    if not os.path.exists(input_path):
        input_path = "df_completo_cr_mini.csv"

output_clean_path = args.output_clean_path
if not output_clean_path:
    output_clean_path = "df_completo_cr_clean.csv"

output_eda_path = args.output_eda_path
if not output_eda_path:
    output_eda_path = "eda_results.json"

# -------------------------------------------------------------------
# FUNCIONES DE CARGA Y GUARDADO SOPORTANDO GCS NATIVO
# -------------------------------------------------------------------
def load_data(src_path):
    if src_path.startswith("gs://"):
        print(f"[*] Descargando dataset desde GCS: {src_path}...")
        path_parts = src_path[5:].split("/", 1)
        bucket_name = path_parts[0]
        blob_path = path_parts[1]
        
        client = storage.Client(project=args.gcp_project)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        data_bytes = blob.download_as_bytes()
        df = pd.read_csv(io.BytesIO(data_bytes), sep=';')
        print(f"[*] Dataset de GCS cargado. Filas: {len(df)}")
        return df
    else:
        print(f"[*] Cargando dataset local: {src_path}...")
        if not os.path.exists(src_path):
            raise FileNotFoundError(f"No se encontró el fichero local: {src_path}")
        df = pd.read_csv(src_path, sep=';')
        print(f"[*] Dataset local cargado. Filas: {len(df)}")
        return df

def save_file(content_or_df, dest_path, is_csv=False):
    if dest_path.startswith("gs://"):
        print(f"[*] Subiendo resultado a GCS: {dest_path}...")
        path_parts = dest_path[5:].split("/", 1)
        bucket_name = path_parts[0]
        blob_path = path_parts[1]
        
        client = storage.Client(project=args.gcp_project)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        if is_csv:
            csv_data = content_or_df.to_csv(sep=';', index=False)
            blob.upload_from_string(csv_data, content_type="text/csv")
        else:
            json_data = json.dumps(content_or_df, indent=4)
            blob.upload_from_string(json_data, content_type="application/json")
        print("[*] Subida a GCS completada con éxito.")
    else:
        print(f"[*] Guardando localmente: {dest_path}...")
        dir_name = os.path.dirname(dest_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
            
        if is_csv:
            content_or_df.to_csv(dest_path, sep=';', index=False)
        else:
            with open(dest_path, "w") as f:
                json.dump(content_or_df, f, indent=4)
        print("[*] Escritura local completada con éxito.")

# -------------------------------------------------------------------
# EJECUCIÓN DEL PIPELINE DE LIMPIEZA
# -------------------------------------------------------------------
print(f"[*] Iniciando Preprocesamiento de datos...")
df = load_data(input_path)

# Definición del target de Basilea III
target_col = 'estado_prestamo'
clase_0 = ['Pagado completamente']
clase_1 = ['Incobrable', 'Default', 'Retraso de 31 a 120 días']

# 1. Filtrar registros maduros y binarizar target al 100% de los datos
print("[*] Aplicando filtros de madurez crediticia y binarización...")
df_clean = df[df[target_col].isin(clase_0 + clase_1)].copy()
df_clean['target'] = np.where(df_clean[target_col].isin(clase_1), 1, 0)

# 2. Limpieza de columnas de porcentaje al 100% de los datos
features_porcentaje = ['tipo_interes', 'porcentaje_uso_credito_revolving']
for col in features_porcentaje:
    if col in df_clean.columns:
        df_clean[col] = df_clean[col].astype(str).str.replace('%', '').str.strip()
        df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')

# 3. Guardar dataset limpio (debe ir a GCS en GCP)
save_file(df_clean, output_clean_path, is_csv=True)

# -------------------------------------------------------------------
# EJECUCIÓN DE CÁLCULO ESTADÍSTICO EDA (MUESTREADO)
# -------------------------------------------------------------------
print(f"\n[*] Iniciando auditoría analítica EDA (Muestra: {args.sample_fraction*100}%)...")
random.seed(42)

# Muestreo para el reporte estadístico
if args.sample_fraction < 1.0:
    df_sample = df.sample(frac=args.sample_fraction, random_state=42)
    df_clean_sample = df_clean.sample(frac=min(1.0, args.sample_fraction), random_state=42)
else:
    df_sample = df.copy()
    df_clean_sample = df_clean.copy()

total_rows_sample = int(df_sample.shape[0])
total_cols = int(df_sample.shape[1])
total_rows_filtered = int(df_clean_sample.shape[0])

# Conteo de nulos en muestra
null_counts = df_sample.isnull().sum()
null_percentages = (null_counts / total_rows_sample) * 100
null_summary = {}
for col in df_sample.columns:
    null_summary[col] = {
        "nulos": int(null_counts[col]),
        "porcentaje": round(float(null_percentages[col]), 2)
    }

# Distribución del target
estado_prestamo_dist = df_sample[target_col].value_counts(dropna=False)
estado_prestamo_summary = [
    {"label": str(k), "count": int(v), "percentage": round(float(v / total_rows_sample) * 100, 2)}
    for k, v in estado_prestamo_dist.items()
]

target_dist = df_clean_sample['target'].value_counts()
target_summary = [
    {"label": "Solvente (Clase 0)", "count": int(target_dist.get(0, 0)), "percentage": round(float(target_dist.get(0, 0) / total_rows_filtered) * 100, 2) if total_rows_filtered > 0 else 0},
    {"label": "Impago/Default (Clase 1)", "count": int(target_dist.get(1, 0)), "percentage": round(float(target_dist.get(1, 0) / total_rows_filtered) * 100, 2) if total_rows_filtered > 0 else 0}
]

# Variables numéricas descriptivas
features_numericas = [
    'importe_solicitado', 
    'ingresos_anuales', 
    'ratio_prestamo_ingresos',
    'puntuacion_crediticia_media',
    'bancarrotas_publicas',
    'consultas_credito_ultimos_6_meses',
    'impago_ultimos_2_anios'
]

# Incorporar las numéricas de porcentaje ya limpias
for col in features_porcentaje:
    if col in df_clean_sample.columns and col not in features_numericas:
        features_numericas.append(col)

descriptive_stats = {}
for col in features_numericas:
    if col in df_clean_sample.columns:
        desc = df_clean_sample[col].describe()
        descriptive_stats[col] = {
            "count": int(desc.get("count", 0)),
            "mean": round(float(desc.get("mean", 0)), 2) if not pd.isna(desc.get("mean")) else 0,
            "std": round(float(desc.get("std", 0)), 2) if not pd.isna(desc.get("std")) else 0,
            "min": round(float(desc.get("min", 0)), 2) if not pd.isna(desc.get("min")) else 0,
            "median": round(float(df_clean_sample[col].median()), 2) if not pd.isna(df_clean_sample[col].median()) else 0,
            "max": round(float(desc.get("max", 0)), 2) if not pd.isna(desc.get("max")) else 0
        }

# Distribución categórica
categorical_summary = {}
for col in ['grado_riesgo', 'finalidad_prestamo']:
    if col in df_sample.columns:
        dist = df_sample[col].value_counts(dropna=False)
        categorical_summary[col] = [
            {"label": str(k), "count": int(v), "percentage": round(float(v / total_rows_sample) * 100, 2)}
            for k, v in dist.items()
        ]

# Matriz de Correlación
df_num = df_clean_sample[features_numericas].dropna()
correlation_data = {"columns": features_numericas, "matrix": []}
if not df_num.empty:
    corr_matrix = df_num.corr(method='pearson')
    correlation_data["matrix"] = [[round(float(corr_matrix.loc[r, c]), 3) if not pd.isna(corr_matrix.loc[r, c]) else 0 for c in features_numericas] for r in features_numericas]

# Estructurar resultado JSON
eda_out = {
    "dimensions": {
        "total_rows_raw_est": int(df.shape[0]),
        "sample_rows": total_rows_sample,
        "total_columns": total_cols,
        "filtered_rows": int(df_clean.shape[0])
    },
    "nulls": null_summary,
    "estado_prestamo_distribution": estado_prestamo_summary,
    "target_distribution": target_summary,
    "descriptive_stats": descriptive_stats,
    "categorical_distribution": categorical_summary,
    "correlation": correlation_data
}

save_file(eda_out, output_eda_path, is_csv=False)
print(f"[*] Preprocesamiento y análisis EDA finalizados con éxito.")
