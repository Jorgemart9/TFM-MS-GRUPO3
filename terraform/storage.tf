resource "random_id" "suffix" {
  byte_length = 4
}

#1. bucket de datos sucios
resource "google_storage_bucket" "input_bucket" {
  name                        = "raw-data-tfm"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true 
  depends_on                  = [google_project_service.enabled_apis]
}

#2. Sube el csv SUCIO al input bucket (Datos Crudos)
resource "google_storage_bucket_object" "raw_data_csv" {
  name   = "df_completo_cr.csv"                 # Nombre real que espera tu Cloud Run
  bucket = google_storage_bucket.input_bucket.name # <--- BUCKET SUCIO (Input)
  source = "${path.module}/../data/df_completo_cr.csv"

  depends_on = [
    google_storage_bucket.input_bucket
  ]
}

#3. bucket de datos limpios
resource "google_storage_bucket" "output_bucket" {
  name                        = "clean-data-tfm"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  depends_on = [
    google_project_service.enabled_apis
  ]
}

#4. Un bucket para VertexAI
resource "google_storage_bucket" "vertex_pipeline_bucket" {
  name                     = "vertex-pipelines-staging-${var.project_id}"
  location                 = var.region
  force_destroy            = true
  public_access_prevention = "enforced"

  uniform_bucket_level_access = true
}