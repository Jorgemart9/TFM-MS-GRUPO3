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

# Permiso para ESCRIBIR los datos limpios en el Bucket de salida (hacia Dataflow)
resource "google_storage_bucket_iam_member" "preprocess_write_clean" {
  bucket = google_storage_bucket.output_bucket.name
  role   = "roles/storage.objectUser"
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

# DATAFLOW
# Permiso base para que los Workers de Dataflow ejecuten el pipeline en el proyecto
resource "google_project_iam_member" "dataflow_worker" {
  project = var.project_id
  role    = "roles/dataflow.worker"
  member  = "serviceAccount:${google_service_account.sa_dataflow.email}"
}

# Permiso para interactuar con los Buckets de Cloud Storage (Leer datos limpios y escribir temporales)
resource "google_storage_bucket_iam_member" "dataflow_storage_clean" {
  bucket = google_storage_bucket.output_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.sa_dataflow.email}"
}

# Permiso para escribir los datos transformados en BigQuery
resource "google_project_iam_member" "dataflow_bq_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.sa_dataflow.email}"
}

resource "google_project_iam_member" "dataflow_bq_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa_dataflow.email}"
}

# Permiso para conectarse de forma privada a Cloud SQL (Cliente de Cloud SQL)
resource "google_project_iam_member" "dataflow_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.sa_dataflow.email}"
}
