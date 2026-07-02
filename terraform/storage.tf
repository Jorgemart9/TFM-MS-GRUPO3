resource "random_id" "suffix" {
  byte_length = 4
}

resource "google_storage_bucket" "input_bucket" {
  name                        = "raw-data-tfm"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true 
  depends_on                  = [google_project_service.enabled_apis]
}

resource "google_storage_bucket" "output_bucket" {
  name                        = "clean-data-tfm"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  depends_on = [
    google_project_service.enabled_apis
  ]
}

# CORRECCIÓN: Este recurso sube el CSV sucio de la raíz al bucket de entrada (raw)
resource "google_storage_bucket_object" "raw_data_csv" {
  name   = "df_completo_cr.csv" # Nombre con el que se guardará en GCS
  bucket = google_storage_bucket.input_bucket.name # <-- CAMBIADO al bucket RAW
  
  # Si tu estructura es:
  # / (Raíz)
  # ├── data/df_completo_cr.csv
  # └── terraform/main.tf
  # El path correcto saliendo de terraform es:
  source = "${path.module}/../data/df_completo_cr.csv"

  depends_on = [
    google_storage_bucket.input_bucket
  ]
}