#LEVANTAMOS DATABASE

data "google_bigquery_dataset" "analytics_warehouse" {
  dataset_id = "analytics_warehouse"
  project    = var.project_id
}

