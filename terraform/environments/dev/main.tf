# Capa RAW: bucket de aterrizaje de datos crudos ("datos sucios" del diagrama).
# El CSV original se sube aqui tal cual (comprimido en gzip). El procesado y la
# carga a BigQuery se hacen en pasos posteriores del pipeline.
module "raw_landing" {
  source = "../../modules/storage"

  name          = var.raw_bucket_name
  project       = var.project
  location      = var.region
  storage_class = "STANDARD"
  versioning    = false # raw es reproducible desde origen: no versionamos para no duplicar coste
  force_destroy = true  # dev: permite recrear/limpiar facilmente

  # Abaratar el coste de almacenamiento del crudo a medida que envejece:
  # tras 30 dias -> Nearline, tras 90 -> Coldline. (1 GB en Standard ya cuesta
  # centimos/mes; estas reglas dejan el patron correcto para datos mayores.)
  lifecycle_rules = [
    { action_type = "SetStorageClass", storage_class = "NEARLINE", age = 30 },
    { action_type = "SetStorageClass", storage_class = "COLDLINE", age = 90 },
  ]

  labels = {
    proyecto = "tfm-ms-grupo3"
    capa     = "raw"
    entorno  = "dev"
  }
}
