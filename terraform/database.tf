#Levantamos la base de datos y las tablas 

data "google_bigquery_dataset" "analytics_warehouse" {
  dataset_id = "analytics_warehouse"
  project    = var.project_id
}

