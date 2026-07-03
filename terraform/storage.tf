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

# NOTA: la carga del CSV inicial NO vive en Terraform. Antes habia aqui un
# google_storage_bucket_object con una ruta local absoluta de una maquina
# concreta, que rompia cualquier `terraform plan/apply` en CI. La ingesta de
# datos se hace fuera del IaC (subida manual / pipeline de datos).

resource "google_storage_bucket" "output_bucket" {
  name                        = "clean-data-tfm"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  depends_on = [
    google_project_service.enabled_apis
  ]
}

resource "google_storage_bucket_object" "datos_limpios_csv" {
  name   = "df_completo_limpio.csv"
  bucket = google_storage_bucket.output_bucket.name
  source = "${path.module}/../data/df_completo_cr.csv"

  depends_on = [
    google_storage_bucket.output_bucket
  ]
}