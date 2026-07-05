# CLOUD RUN - PREPROCESS

# Leer imagen Docker
resource "google_artifact_registry_repository_iam_member" "preprocess_registry_reader" {
  location   = google_artifact_registry_repository.preprocess_repo.location
  repository = google_artifact_registry_repository.preprocess_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.sa_preprocess.email}"
}

# Leer CSV de entrada
resource "google_storage_bucket_iam_member" "preprocess_input_bucket_reader" {
  bucket = google_storage_bucket.input_bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.sa_preprocess.email}"
}

# Leer y escribir en BigQuery
resource "google_project_iam_member" "preprocess_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa_preprocess.email}"
}

resource "google_project_iam_member" "preprocess_bq_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.sa_preprocess.email}"
}

# CLOUD RUN - DASHBOARD

# Leer imagen Docker
resource "google_artifact_registry_repository_iam_member" "dash_registry_reader" {
  location   = google_artifact_registry_repository.dash_repo.location
  repository = google_artifact_registry_repository.dash_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.sa_dash.email}"
}

# Consultar BigQuery
resource "google_project_iam_member" "dash_bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.sa_dash.email}"
}

resource "google_project_iam_member" "dash_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa_dash.email}"
}

# CLOUD RUN - MONITORING

# Leer imagen Docker
resource "google_artifact_registry_repository_iam_member" "monitoring_registry_reader" {
  location   = google_artifact_registry_repository.monitoring_repo.location
  repository = google_artifact_registry_repository.monitoring_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.sa_monitoring.email}"
}

# Leer BigQuery
resource "google_project_iam_member" "monitoring_bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.sa_monitoring.email}"
}

# VERTEX AI TRAINING

# Permiso para ejecutar Jobs de Vertex AI
resource "google_project_iam_member" "vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.sa_vertex.email}"
}

# Consultar BigQuery
resource "google_project_iam_member" "vertex_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa_vertex.email}"
}

resource "google_project_iam_member" "vertex_bq_data_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.sa_vertex.email}"
}

# Leer imagen Docker del entrenamiento
resource "google_artifact_registry_repository_iam_member" "vertex_registry_reader" {
  location   = google_artifact_registry_repository.training_repo.location
  repository = google_artifact_registry_repository.training_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.sa_vertex.email}"
}

# Guardar modelos en Cloud Storage
resource "google_storage_bucket_iam_member" "vertex_storage_admin" {
  bucket = google_storage_bucket.models_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.sa_vertex.email}"
}

#CLOUD BUILD 
# 1. Permiso para leer experimentos, pipelines y gestionar modelos/endpoints en Vertex AI
resource "google_project_iam_member" "cloudbuild_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.sa_cloudbuild.email}"
}

# 2. Permiso para ejecutar consultas e insertar filas con los resultados en BigQuery
resource "google_project_iam_member" "cloudbuild_bq_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.sa_cloudbuild.email}"
}

resource "google_project_iam_member" "cloudbuild_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa_cloudbuild.email}"
}

# 3. Permiso para leer los artefactos del modelo guardados en tu Bucket de modelos
resource "google_storage_bucket_iam_member" "cloudbuild_storage_viewer" {
  bucket = google_storage_bucket.models_bucket.name 
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.sa_cloudbuild.email}"
}

# 4. Permiso necesario para generar logs de la ejecución en Cloud Logging
resource "google_project_iam_member" "cloudbuild_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.sa_cloudbuild.email}"
}

resource "google_project_iam_member" "github_cloudbuild_editor" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}