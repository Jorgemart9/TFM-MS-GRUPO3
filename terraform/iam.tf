# PERMISOS: CLOUD RUN PREPROCESAMIENTO

# Permiso para leer la imagen de su respectivo repositorio
resource "google_artifact_registry_repository_iam_member" "preprocess_registry_reader" {
  location   = google_artifact_registry_repository.preprocess_repo.location
  repository = google_artifact_registry_repository.preprocess_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.sa_preprocess.email}"
}

# Permiso para LEER los datos sucios (CSV) del Bucket de entrada
resource "google_storage_bucket_iam_member" "preprocess_read_dirty" {
  bucket = google_storage_bucket.input_bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.sa_preprocess.email}"
}


# PERMISOS: CLOUD RUN DASH (DASHBOARD)
resource "google_artifact_registry_repository_iam_member" "dash_registry_reader" {
  location   = google_artifact_registry_repository.dash_repo.location
  repository = google_artifact_registry_repository.dash_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.sa_dash.email}"
}

# Permiso para leer datos consolidados de BigQuery
resource "google_project_iam_member" "dash_bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.sa_dash.email}"
}

# Permiso para ejecutar consultas/jobs dentro de BigQuery
resource "google_project_iam_member" "dash_bq_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa_dash.email}"
}

# PERMISOS: CLOUD RUN MONITORING
resource "google_artifact_registry_repository_iam_member" "monitoring_registry_reader" {
  location   = google_artifact_registry_repository.monitoring_repo.location
  repository = google_artifact_registry_repository.monitoring_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.sa_monitoring.email}"
}

# Permiso para leer analíticas de BigQuery e identificar anomalías de ejecución
resource "google_project_iam_member" "monitoring_bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.sa_monitoring.email}"
}

resource "google_storage_bucket_iam_member" "preprocess_write_clean" {
  bucket = "clean-data-tfm"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:sa-preprocess@tfm-ms-3.iam.gserviceaccount.com"
}
