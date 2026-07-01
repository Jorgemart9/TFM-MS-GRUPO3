# Lista de todas las APIs requeridas por la arquitectura
variable "gcp_apis" {
  type = list(string)
  default = [
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",
    "secretmanager.googleapis.com",
    "bigquery.googleapis.com",
    "run.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudfunctions.googleapis.com" # Añadida para la función de trigger
  ]
}

# Recurso para activar las APIs de forma iterativa
resource "google_project_service" "enabled_apis" {
  for_each = toset(var.gcp_apis)
  project  = var.project_id
  service  = each.key

  disable_on_destroy = false
}
