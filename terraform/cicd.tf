# ============================================================================
# CI/CD: Workload Identity Federation (WIF) para GitHub Actions
# ----------------------------------------------------------------------------
# Permite que los workflows de GitHub Actions se autentiquen contra GCP SIN
# claves JSON de larga duracion: GitHub emite un token OIDC y GCP lo canjea
# por credenciales temporales impersonando a la SA "sa-github-deployer".
#
# IMPORTANTE (bootstrap): estos recursos hay que crearlos UNA VEZ con un
# `terraform apply` local (con credenciales de un humano) ANTES de que el CD
# pueda funcionar. Ver SETUP.md.
# ============================================================================

data "google_project" "current" {
  project_id = var.project_id
}

# Pool de identidades federadas
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions Pool"
  description               = "Identidades federadas para los workflows de GitHub Actions del TFM"
}

# Proveedor OIDC de GitHub dentro del pool
resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }

  # Restringe el canje de tokens EXCLUSIVAMENTE a este repositorio.
  attribute_condition = "assertion.repository == '${var.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Service Account que asumen los workflows para construir/desplegar
resource "google_service_account" "github_deployer" {
  account_id   = "sa-github-deployer"
  display_name = "GitHub Actions Deployer (CI/CD)"
}

# Permite que las ejecuciones del repo impersonen la SA deployer
resource "google_service_account_iam_member" "deployer_wif_user" {
  service_account_id = google_service_account.github_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

# --- Roles de la SA deployer -------------------------------------------------

# Publicar imagenes en Artifact Registry
resource "google_project_iam_member" "deployer_artifactregistry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

# Desplegar servicios y jobs de Cloud Run
resource "google_project_iam_member" "deployer_run" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

# Leer/escribir el estado remoto de Terraform en GCS
resource "google_project_iam_member" "deployer_storage" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

# --- Roles adicionales para `terraform apply` completo (workflow en main) ----
# La raiz terraform/ gestiona red, BigQuery, SAs, APIs y bindings IAM, asi que
# la SA deployer necesita permisos amplios para aplicar TODA la infra.
# En un entorno productivo conviene acotarlos; para el TFM usamos editor +
# admin de IAM de proyecto (necesario para los google_project_iam_member).
resource "google_project_iam_member" "deployer_editor" {
  project = var.project_id
  role    = "roles/editor"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_project_iam_member" "deployer_project_iam_admin" {
  project = var.project_id
  role    = "roles/resourcemanager.projectIamAdmin"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

# Permite a la SA deployer "actuar como" las SAs de runtime al desplegar en
# Cloud Run (necesario porque cada servicio/job corre con su propia SA).
resource "google_service_account_iam_member" "deployer_act_as" {
  for_each = {
    dash       = google_service_account.sa_dash.name
    monitoring = google_service_account.sa_monitoring.name
    preprocess = google_service_account.sa_preprocess.name
  }
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_deployer.email}"
}
