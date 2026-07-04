FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias para LightGBM y XGBoost
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Instalar las librerías de Python requeridas
RUN pip install --no-cache-dir \
    pandas \
    numpy \
    scikit-learn \
    xgboost \
    lightgbm \
    catboost \
    shap \
    joblib \
    google-cloud-aiplatform \
    google-cloud-storage \
    db-dtypes

# Copiar tu script de entrenamiento al contenedor con su nombre real
COPY train_pipeline.py /app/train_pipeline.py

# Definir el punto de entrada
ENTRYPOINT ["python", "/app/train_pipeline.py"]