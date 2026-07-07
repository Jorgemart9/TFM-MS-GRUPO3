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


resource "google_cloudbuild_trigger" "model_test_trigger" {
  project     = var.project_id
  name        = "ejecutar-test-calidad-y-drift"
  description = "Trigger para analizar calidad, calcular PSI/EDA, persistir en BQ y disparar reentrenamiento en Vertex AI usando training-repo"
  location    = "europe-west1"

  # Vinculamos el trigger a la nueva cuenta de servicio
  service_account = google_service_account.sa_cloudbuild_v2.id

  # Aseguramos que el registro de artefactos "training_repo" exista antes de configurar el trigger
  depends_on = [google_artifact_registry_repository.training_repo]

  # Configuración del repositorio origen (GitHub)
  source_to_build {
    uri       = "https://github.com/tu-usuario-o-organizacion/TFM-MS-GRUPO3"
    ref       = "refs/heads/main"
    repo_type = "GITHUB"
  }

  filename = "cloudbuild-test.yaml"

  # Variables de entorno inyectadas dinámicamente al pipeline de Cloud Build
  substitutions = {
    _PROJECT_ID        = var.project_id
    _LOCATION          = "europe-west1"
    _BQ_DATASET_DASH   = "gubernatura_modelos"
    _BQ_DATASET_RAW    = "analytics_warehouse"
    _GCS_BUCKET        = "models-artifacts-tfm"
    _SA_VERTEX_TRAIN   = "sa-vertex-train@${var.project_id}.iam.gserviceaccount.com"
  }
}