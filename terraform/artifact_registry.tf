# 1.Repositorio para el Preprocesamiento de datos
resource "google_artifact_registry_repository" "preprocess_repo" {
  location      = var.region
  repository_id = "preprocess-repo"
  format        = "DOCKER"
  description   = "Repositorio Docker para el Cloud Run de Preprocesamiento"
  depends_on    = [google_project_service.enabled_apis]
}

# 2.Repositorio para la aplicación del Dashboard
resource "google_artifact_registry_repository" "dash_repo" {
  location      = var.region
  repository_id = "dash-repo"
  format        = "DOCKER"
  description   = "Repositorio Docker para el Cloud Run del Dashboard (Flask/Dash)"
  depends_on    = [google_project_service.enabled_apis]
}

# 3.Repositorio para el microservicio de Monitoreo
resource "google_artifact_registry_repository" "monitoring_repo" {
  location      = var.region
  repository_id = "monitoring-repo"
  format        = "DOCKER"
  description   = "Repositorio Docker para el Cloud Run de Monitoreo"
  depends_on    = [google_project_service.enabled_apis]
}

# 4. Trigger
resource "google_cloudbuildv2_repository" "tfm_repository" {
  name              = "TFM-MS-GRUPO3"
  location          = var.region
  parent_connection = google_cloudbuildv2_connection.github_connection.id
  remote_uri        = "https://github.com/Jorgemart9/TFM-MS-GRUPO3.git"
}
 