variable "project" {
  description = "ID del proyecto de GCP del TFM."
  type        = string
}

variable "region" {
  description = "Region por defecto (region simple para abaratar almacenamiento)."
  type        = string
  default     = "europe-southwest1"
}

variable "raw_bucket_name" {
  description = "Nombre del bucket de aterrizaje de datos crudos (capa raw / 'datos sucios')."
  type        = string
}
