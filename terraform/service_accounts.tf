# 1.Cuenta de servicio para Cloud Run Preprocesamiento
resource "google_service_account" "sa_preprocess" {
  account_id   = "sa-preprocess"
  display_name = "Identity for Preprocessing Cloud Run Service"
}

# 2.Cuenta de servicio para Cloud Run Dashboard
resource "google_service_account" "sa_dash" {
  account_id   = "sa-dash"
  display_name = "Identity for Dashboard Visualisation Service"
}

# 3.Cuenta de servicio para Cloud Run Monitoreo
resource "google_service_account" "sa_monitoring" {
  account_id   = "sa-monitoring"
  display_name = "Identity for Monitoring Cloud Run Service"
}

# 4.Cuenta de servicio para desplegar el pipeline de VertexAI
# Cuenta de servicio con la que se ejecutarán los componentes del pipeline en GCP
resource "google_service_account" "sa_vertex_pipelines" {
  account_id   = "sa-vertex-pipelines"
  display_name = "Service Account para la ejecución de Vertex AI Pipelines"
}

