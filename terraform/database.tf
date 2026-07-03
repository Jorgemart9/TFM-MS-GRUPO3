#Levantamos la base de datos y las tablas 

data "google_bigquery_dataset" "analytics_warehouse" {
  dataset_id = "analytics_warehouse"
  project    = var.project_id
}

resource "google_bigquery_dataset" "dataset" {
  dataset_id                  = "analytics_warehouse"
  friendly_name               = "Analytics Warehouse"
  description                 = "Dataset analítico que recibe réplicas por CDC y cargas de Dataflow"
  location                    = var.region
  default_table_expiration_ms = 36000000

  depends_on = [google_project_service.enabled_apis]
}

resource "google_bigquery_table" "bq_table" {
  # Cambia data.google_bigquery_dataset por google_bigquery_dataset (el que creas arriba) para evitar conflictos de lectura previos
  dataset_id          = google_bigquery_dataset.dataset.dataset_id
  table_id            = "datos_limpios"
  deletion_protection = false

  external_data_configuration {
    autodetect    = true 
    source_format = "CSV"
    
    # CORREGIDA LA URI: Sin doble barra diagonal y con el nombre real de tu archivo limpio
    source_uris = [
      "gs://clean-data-tfm/df_completo_cr_clean.csv"
    ]

    ignore_unknown_values = true

    csv_options {
      quote             = "\""
      skip_leading_rows = 1
      field_delimiter   = ";"
    }
  }
}