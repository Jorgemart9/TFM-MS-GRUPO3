resource "google_cloudbuild_trigger" "model_evaluation_trigger" {
  name        = "evaluar-y-exportar-metricas-modelo"
  description = "Trigger para ejecutar export_metrics.py tras el entrenamiento"
  project     = var.project_id
  location    = "europe-west1"

  # Vinculamos la cuenta de servicio con permisos que creamos antes
  service_account = google_service_account.sa_cloudbuild.id

  # CAMBIADO: Configuración para ejecución manual/remota (Ideal para lanzar desde GitHub Actions)
  source_to_build {
    uri       = "https://github.com/tu-usuario-o-organizacion/TFM-MS-GRUPO3" # Reemplaza con la URL real de tu repo
    ref       = "refs/heads/main"
    repo_type = "GITHUB"
  }

  filename = "cloudbuild.yaml"

  substitutions = {
    _PROJECT_ID      = var.project_id
    _BQ_DATASET      = "analytics_warehouse"
    _VERTEX_LOCATION = "europe-west1"
  }
}