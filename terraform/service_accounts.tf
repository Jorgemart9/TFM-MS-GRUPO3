# Cuenta de servicio para Cloud Run Preprocesamiento
resource "google_service_account" "sa_preprocess" {
  account_id   = "sa-preprocess"
  display_name = "Identity for Preprocessing Cloud Run Service"
}

# Cuenta de servicio para Cloud Run Dashboard
resource "google_service_account" "sa_dash" {
  account_id   = "sa-dash"
  display_name = "Identity for Dashboard Visualisation Service"
}

# Cuenta de servicio para Cloud Run Monitoreo
resource "google_service_account" "sa_monitoring" {
  account_id   = "sa-monitoring"
  display_name = "Identity for Monitoring Cloud Run Service"
}

#Cuenta de servicio para CICD
resource "google_service_account" "github_deployer" {
  account_id   = "sa-github-deployer"
  display_name = "GitHub Actions CI/CD Deployer"
  description  = "Cuenta de servicio utilizada por GitHub Actions para compilar imagenes en Artifact Registry y actualizar Cloud Run"
}

