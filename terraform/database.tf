
resource "google_bigquery_dataset" "dataset" {
  dataset_id                  = "analytics_warehouse"
  friendly_name               = "Analytics Warehouse"
  description                 = "Dataset analítico que recibe réplicas por CDC y cargas de Dataflow"
  location                    = var.region
  default_table_expiration_ms = 36000000

  depends_on = [google_project_service.enabled_apis]
}
