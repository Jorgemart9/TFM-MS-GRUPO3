# SERVICE ACCOUNT - GITHUB ACTIONS
resource "google_service_account" "github_deployer" {
  account_id   = "sa-github-deployer-v2"
  display_name = "GitHub Actions Deployer"
  project      = var.project_id
}

# WORKLOAD IDENTITY FEDERATION
resource "google_iam_workload_identity_pool" "github_pool1"{
  workload_identity_pool_id = "github-wif-pool"
  display_name              = "GitHub Actions Pool"
  description               = "Identity pool for GitHub Actions CI/CD"
}

resource "google_iam_workload_identity_pool_provider" "github_provider" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool1.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Provider"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  attribute_condition = "assertion.repository != ''"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_wif_binding" {
  service_account_id = google_service_account.github_deployer.id
  role               = "roles/iam.workloadIdentityUser"

  member = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool1.name}/*"
}

# PERMISOS DEL DEPLOYER
resource "google_project_iam_member" "github_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_project_iam_member" "github_cloud_run" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_project_iam_member" "github_vertex_ai" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

# ACT AS SOBRE SERVICE ACCOUNTS
resource "google_service_account_iam_member" "github_act_as_preprocess" {
  service_account_id = google_service_account.sa_preprocess.id
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_service_account_iam_member" "github_act_as_dash" {
  service_account_id = google_service_account.sa_dash.id
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_service_account_iam_member" "github_act_as_monitoring" {
  service_account_id = google_service_account.sa_monitoring.id
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_service_account_iam_member" "github_act_as_vertex" {
  service_account_id = google_service_account.sa_vertex.id
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_deployer.email}"
}

# STORAGE
resource "google_storage_bucket_iam_member" "github_storage_admin" {
  bucket = google_storage_bucket.models_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.github_deployer.email}"
}
