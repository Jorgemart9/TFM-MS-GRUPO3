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
  dataset_id= data.google_bigquery_dataset.analytics_warehouse.dataset_id
  table_id="datos_limpios" # Cámbialo si tu tabla tiene otro nombre
  deletion_protection = false

  external_data_configuration {
    autodetect    = true # Esto le dice a BQ que adivine si es INT, FLOAT, STRING, etc.
    source_format = "CSV"
    source_uris = [
        "gs://clean-data-tfm/df_completo_limpio.csv"
    ]

    csv_options {
      quote             = "\""

      # 1. Le decimos que la primera fila son los nombres de las columnas (puntuacion_c, ingresos_anuales...)
      skip_leading_rows = 1

      # 2. Forzamos a que el separador de columnas sea el punto y coma
      field_delimiter   = ";"
    }
  }
}
