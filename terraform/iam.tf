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

#Escribe los resultados
resource "google_storage_bucket_iam_member" "preprocess_bucket_writer" {
  bucket = google_storage_bucket.models_bucket.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:sa-preprocess@tfm-ms-3.iam.gserviceaccount.com"
}
# CLOUD RUN - DASHBOARD

# Leer imagen Docker
resource "google_artifact_registry_repository_iam_member" "dash_registry_reader" {
  location   = google_artifact_registry_repository.dash_repo.location
  repository = google_artifact_registry_repository.dash_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.sa_dash.email}"
}

resource "google_cloud_run_service_iam_member" "public_invoker" {
  service = google_cloud_run_v2_service.dash_service.name
  location = google_cloud_run_v2_service.dash_service.location
  role    = "roles/run.invoker"
  member  = "allUsers"
}

# Consultar y actualizar BigQuery (para escribir logs en t_quality_test_log)
resource "google_project_iam_member" "dash_bq_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
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

resource "google_storage_bucket_iam_member" "monitoring_gcs_access" {
  bucket = "models-artifacts-tfm"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.sa_monitoring.email}"
}

resource "google_project_iam_member" "monitoring_storage_admin" {
  project = "tfm-ms-3"
  role = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.sa_monitoring.email}"
}

resource "google_project_iam_member" "monitoring_storage_creator" {
  project = "tfm-ms-3"
  role = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.sa_monitoring.email}"

}

resource "google_project_iam_member" "monitoring_cloudbuild_editor" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.sa_monitoring.email}"
}

resource "google_project_iam_member" "monitoring_aiplatform_viewer" {
  project = var.project_id
  role    = "roles/aiplatform.viewer"
  member  = "serviceAccount:${google_service_account.sa_monitoring.email}"
}

# Leer BigQuery
resource "google_project_iam_member" "monitoring_bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.sa_monitoring.email}"
}

# Ejecutar consultas SQL
resource "google_project_iam_member" "monitoring_bq_jobuser" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
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

# CLOUD BUILD 

# Permiso para que Cloud Build pueda subir (push) imágenes a todos los repositorios
resource "google_project_iam_member" "cb_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.sa_cloudbuild_v2.email}"
}

# Permisos en BigQuery: Escribir métricas/drift (gubernatura_modelos) y leer datos de entrenamiento (analytics_warehouse)
resource "google_project_iam_member" "cb_bq_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.sa_cloudbuild_v2.email}"
}

resource "google_project_iam_member" "cb_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.user"
  member  = "serviceAccount:${google_service_account.sa_cloudbuild_v2.email}"
}

# Permiso para lanzar entrenamientos (CustomJobs) en Vertex AI
resource "google_project_iam_member" "cb_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.sa_cloudbuild_v2.email}"
}

# Permiso crítico: Permitir a Cloud Build actuar en nombre de la cuenta de entrenamiento de Vertex AI
resource "google_service_account_iam_member" "cb_act_as_vertex_sa" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/sa-vertex-train@${var.project_id}.iam.gserviceaccount.com"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.sa_cloudbuild_v2.email}"
}

# Permiso para leer y escribir artefactos en Cloud Storage (modelos, shap values, logs)
resource "google_project_iam_member" "cb_gcs_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.sa_cloudbuild_v2.email}"
}

# Permiso para que la cuenta de Vertex AI pueda descargar (pull) imágenes de "training-repo"
resource "google_artifact_registry_repository_iam_member" "vertex_reader" {
  project    = var.project_id
  location   = google_artifact_registry_repository.training_repo.location
  repository = google_artifact_registry_repository.training_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:sa-vertex-train@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_storage_bucket_iam_member" "sa_cloudbuild_bucket_admin" {
  bucket = "models-artifacts-tfm"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.sa_cloudbuild_v2.email}"
}

resource "google_service_account_iam_member" "monitoring_act_as_cloudbuild_evaluator" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/sa-cloudbuild-evaluator@${var.project_id}.iam.gserviceaccount.com"
  role                = "roles/iam.serviceAccountUser"
  member              = "serviceAccount:${google_service_account.sa_monitoring.email}"
}

resource "google_service_account_iam_member" "monitoring_act_as_cloudbuild_v2" {
  service_account_id = google_service_account.sa_cloudbuild_v2.id
  role                = "roles/iam.serviceAccountUser"
  member              = "serviceAccount:${google_service_account.sa_monitoring.email}"
}

