
# 1.Permiso para leer la imagen de su respectivo repositorio
resource "google_artifact_registry_repository_iam_member" "preprocess_registry_reader" {
  location   = google_artifact_registry_repository.preprocess_repo.location
  repository = google_artifact_registry_repository.preprocess_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.sa_preprocess.email}"
}

# 2.Permiso para LEER los datos sucios (CSV) del Bucket de entrada
resource "google_storage_bucket_iam_member" "preprocess_read_dirty" {
  bucket = google_storage_bucket.input_bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.sa_preprocess.email}"
}


# 3.Permiso para leer el cloud run dek Dashboard
resource "google_artifact_registry_repository_iam_member" "dash_registry_reader" {
  location   = google_artifact_registry_repository.dash_repo.location
  repository = google_artifact_registry_repository.dash_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.sa_dash.email}"
}

# 4.Permiso para leer datos consolidados de BigQuery
resource "google_project_iam_member" "dash_bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.sa_dash.email}"
}

# 5.Permiso para ejecutar consultas/jobs dentro de BigQuery
resource "google_project_iam_member" "dash_bq_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa_dash.email}"
}

# 6.Permiso para leer en el cloud run de monitoring
resource "google_artifact_registry_repository_iam_member" "monitoring_registry_reader" {
  location   = google_artifact_registry_repository.monitoring_repo.location
  repository = google_artifact_registry_repository.monitoring_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.sa_monitoring.email}"
}

# 7.Permiso para leer analíticas de BigQuery e identificar anomalías de ejecución
resource "google_project_iam_member" "monitoring_bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.sa_monitoring.email}"
}

# 8.Permiso a bq ara que pueda leer de buckets
resource "google_storage_bucket_iam_member" "bigquery_storage_reader" {
  bucket = "clean-data-tfm"
  role   = "roles/storage.objectViewer" # Permiso de lectura de objetos básico y seguro
  member = "serviceAccount:sa-preprocess@tfm-ms-3.iam.gserviceaccount.com"
}

# 9.Permiso para que pueda escribir en un bucket
resource "google_storage_bucket_iam_member" "preprocess_write_clean" {
  bucket = "clean-data-tfm"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:sa-preprocess@tfm-ms-3.iam.gserviceaccount.com"
}

# 10.Permiso para que pueda escribir en su propio bucket de stagging (VertexAI)
resource "google_storage_bucket_iam_member" "vertex_bucket_admin" {
  bucket = google_storage_bucket.vertex_pipeline_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.sa_vertex_pipelines.email}"
}

# 11.Permiso para registrar los metadatos de los experimentos (Model Registry, Lineage)
resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.sa_vertex_pipelines.email}"
}

resource "google_storage_bucket_iam_member" "github_storage_admin" {
  bucket = "vertex-pipelines-staging-tfm-ms-3"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:sa-github-deployer@tfm-ms-3.iam.gserviceaccount.com"
}