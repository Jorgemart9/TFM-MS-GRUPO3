resource "google_service_account" "github_deployer" {
  account_id   = "sa-github-deployer-v2" 
  display_name = "GitHub Actions Deployer v2"
  project      = "tfm-ms-3"
}

resource "google_service_account_iam_member" "github_wif_binding" {
  service_account_id = google_service_account.github_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/jorgemart9/tfm-ms-grupo3"
}

# 1. Crear el Pool de Identidad
resource "google_iam_workload_identity_pool" "github_pool" {
  workload_identity_pool_id = "github-wif-pool" 
  display_name              = "GitHub Actions Pool"
  description               = "Identity pool for GitHub Actions CI/CD"
}

# 2. Crear el Proveedor OIDC
resource "google_iam_workload_identity_pool_provider" "github_provider" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Provider"
  
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }
  
  # CORREGIDO: Condición ajustada a tu usuario
  attribute_condition = "attribute.repository.contains('jorgemart9')"
  
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# 4. Permiso para escribir en Artifact Registry
resource "google_project_iam_member" "github_deployer_artifact_writer" {
  project = "tfm-ms-3"
  role    = "roles/artifactregistry.writer"
  # CORREGIDO: Apunta dinámicamente a la cuenta v2
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

# 5. Permiso para ejecutar el deploy de Cloud Run
resource "google_project_iam_member" "github_deployer_run_admin" {
  project = "tfm-ms-3"
  role    = "roles/run.admin"
  # CORREGIDO: Apunta dinámicamente a la cuenta v2
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}