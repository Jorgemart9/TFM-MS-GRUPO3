# Repositorio para el microservicio de Preprocesamiento de datos
resource "google_artifact_registry_repository" "preprocess_repo" {
  location      = var.region
  repository_id = "preprocess-repo"
  format        = "DOCKER"
  description   = "Repositorio Docker para el Cloud Run de Preprocesamiento"
  depends_on    = [google_project_service.enabled_apis]
}

# Repositorio para la aplicación del Dashboard
resource "google_artifact_registry_repository" "dash_repo" {
  location      = var.region
  repository_id = "dash-repo"
  format        = "DOCKER"
  description   = "Repositorio Docker para el Cloud Run del Dashboard (Flask/Dash)"
  depends_on    = [google_project_service.enabled_apis]
}

# Repositorio para el microservicio de Monitoreo
resource "google_artifact_registry_repository" "monitoring_repo" {
  location      = var.region
  repository_id = "monitoring-repo"
  format        = "DOCKER"
  description   = "Repositorio Docker para el Cloud Run de Monitoreo"
  depends_on    = [google_project_service.enabled_apis]
}
