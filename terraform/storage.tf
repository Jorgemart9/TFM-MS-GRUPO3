resource "random_id" "suffix" {
  byte_length = 4
}

# BUCKET DATOS SUCIOS
resource "google_storage_bucket" "input_bucket" {
  name                        = "raw-data-tfm"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true 
  depends_on                  = [google_project_service.enabled_apis]
}

#SUBE CSV SUCIO
resource "google_storage_bucket_object" "raw_data_csv" {
  name   = "df_completo_cr.csv"                 # Nombre real que espera tu Cloud Run
  bucket = google_storage_bucket.input_bucket.name # <--- BUCKET SUCIO (Input)
  source = "${path.module}/../data/df_completo_cr.csv"

  depends_on = [
    google_storage_bucket.input_bucket
  ]
}

#BUCKET VERTEX AI
resource "google_storage_bucket" "models_bucket" {
  name                        = "models-artifacts-tfm" # Nombre único en GCP
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true 
  depends_on                  = [google_project_service.enabled_apis]
}




