resource "random_id" "suffix" {
  byte_length = 4
}

resource "google_storage_bucket" "input_bucket" {
  name                        = "raw-data-tfm"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true # Permite vaciarlo automáticamente al hacer destroy
  depends_on                  = [google_project_service.enabled_apis]
}

resource "google_storage_bucket_object" "csv_inicial" {
  name   = "df_completo_cr.csv" # El nombre que conservará dentro de los buckets de Google Cloud
  bucket = google_storage_bucket.input_bucket.name

  # SOLUCIÓN: Ruta absoluta usando barras inclinadas hacia la derecha ( format compatible )
  source = "C:/Users/gbala/Desktop/BDD Data Drift 2/df_completo_cr.csv"
}

# Bucket para datos limpios e intermedios
resource "google_storage_bucket" "output_bucket" {
  name                        = "clean-data-tfm"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
  depends_on                  = [google_project_service.enabled_apis]
}
