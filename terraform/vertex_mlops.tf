
# 2.Recurso físico en Vertex AI donde se alojará el modelo para servir predicciones en producción (si el Quality Gate da PASS).
resource "google_vertex_ai_endpoint" "model_production_endpoint" {
  name         = "modelo-produccion-endpoint"
  display_name = "Endpoint de Producción - TFM Grupo 3"
  location     = var.region
  description  = "Endpoint gestionado para servir el modelo entrenado"
}