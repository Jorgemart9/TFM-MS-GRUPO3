FROM python:3.9-slim

WORKDIR /app

# Copiar e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el script de métricas al contenedor
COPY export_metrics.py .

# Establecer el punto de entrada predeterminado
ENTRYPOINT ["python", "export_metrics.py"]
