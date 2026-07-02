# ===================================================================
# WORKLOAD IDENTITY FEDERATION (CI/CD GITHUB ACTIONS)
# ===================================================================
# Crear la cuenta de servicio con el ID exacto que requiere el pipeline
resource "google_service_account" "github_deployer" {
  account_id   = "sa-github-deployer"
  display_name = "GitHub Deployer Service Account"
  description  = "Cuenta de servicio utilizada por GitHub Actions para el despliegue de MLOps"
}
# 1. Crear el Pool de Identidad
resource "google_iam_workload_identity_pool" "github_pool" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions Pool"
  description               = "Pool de identidad para autenticar los flujos de GitHub Actions"
}

# 2. Crear el Proveedor OIDC Corregido con Condición de Atributo
resource "google_iam_workload_identity_pool_provider" "github_provider" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Provider"
  
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "attribute.repository.contains('tfm-ms-grupo3') || attribute.repository.contains('TFM-MS-GRUPO3')"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# 3. Vincular el repositorio de forma dinámica (Evita el Error 404)
resource "google_service_account_iam_member" "github_wif_binding" {
  service_account_id = google_service_account.github_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/jorgemart9/TFM-MS-GRUPO3"
}