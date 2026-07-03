variable "gcp_apis" {
  type = list(string)

  default = [
    # Infraestructura
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",

    # IAM
    "iam.googleapis.com",

    # Secret Manager
    "secretmanager.googleapis.com",

    # Storage
    "storage.googleapis.com",

    # BigQuery
    "bigquery.googleapis.com",

    # Cloud Run
    "run.googleapis.com",

    # Cloud Functions
    "cloudfunctions.googleapis.com",

    # Cloud Build
    "cloudbuild.googleapis.com",

    # Artifact Registry
    "artifactregistry.googleapis.com",

    # Vertex AI
    "aiplatform.googleapis.com",

    # Logging y Monitoring
    "logging.googleapis.com",
    "monitoring.googleapis.com",

    # Trace
    "cloudtrace.googleapis.com",

    # Dataform
    "dataform.googleapis.com"
  ]
}

resource "google_project_service" "enabled_apis" {
  for_each = toset(var.gcp_apis)

  project = var.project_id
  service = each.value

  disable_on_destroy = false
}