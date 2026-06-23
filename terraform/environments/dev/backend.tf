# Estado remoto en GCS (el bucket de tfstate se crea una sola vez, fuera de Terraform).
# Bucket: gs://tfm-ms-3-tfstate  (region europe-southwest1, versionado + UBLA)
terraform {
  backend "gcs" {
    bucket = "tfm-ms-3-tfstate"
    prefix = "tfm/dev"
  }
}
