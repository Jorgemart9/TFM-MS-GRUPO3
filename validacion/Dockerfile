# 1. Imagen oficial ultra ligera de Python
FROM python:3.10-slim

# 2. Directorio de trabajo dentro del contenedor
WORKDIR /app

# 3. Copiar las dependencias e instalarlas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiar únicamente tu script de ejecución
COPY export_metrics.py .

# 5. Ejecutar el script por defecto
ENTRYPOINT ["python", "export_metrics.py"]