# CUENTA DE SERVICIO PREPROCESAMIENTO
resource "google_service_account" "sa_preprocess" {
  account_id   = "sa-preprocess"
  display_name = "Identity for Preprocessing Cloud Run Service"
}

# CUENTA DE SERVICIO CLOUD RUN DASHBOARD
resource "google_service_account" "sa_dash" {
  account_id   = "sa-dash"
  display_name = "Identity for Dashboard Visualisation Service"
}

# CUENTA DE SERVICIO CLOUD RUN MONITOREO
resource "google_service_account" "sa_monitoring" {
  account_id   = "sa-monitoring"
  display_name = "Identity for Monitoring Cloud Run Service"
}

#CUENTA DE SERVICIO VERTEX AI
resource "google_service_account" "sa_vertex" {
  account_id   = "sa-vertex-train"
  display_name = "Vertex AI Training Service Account"
  project      = var.project_id
}

#CUENTA DE SERVICIO PARA EL CLOUD BUILD 
resource "google_service_account" "sa_cloudbuild" {
  account_id   = "sa-cloudbuild-evaluator"
  display_name = "Cloud Build Model Evaluator Service Account"
  project      = var.project_id
}

#CUENTA DE SERVICIO PARA CLOUD BUILD EXPORT METRICS
resource "google_service_account_iam_member" "github_act_as_cloudbuild" {
  service_account_id = google_service_account.sa_cloudbuild.id
  role   = "roles/iam.serviceAccountUser"
  member = "serviceAccount:${google_service_account.github_deployer.email}"
}

# CUENTA DE SERVICIO PARA TEST QUALITY
resource "google_service_account" "sa_cloudbuild_v2" {
  project      = var.project_id
  account_id   = "sa-mlops-evaluator-v2" # <-- Identificador único nuevo en GCP
  display_name = "Cloud Build Evaluator and Drift Controller V2"
}