variable "project_id" {
  type        = string
  description = "tfm-ms-3"
}

variable "region" {
  type        = string
  default     = "europe-west1"
  description = "Región por defecto para los recursos"
}

variable "github_repository" {
  type        = string
  default     = "Jorgemart9/TFM-MS-GRUPO3"
  description = "Repositorio (owner/repo) autorizado a federar identidad con GCP vía WIF."
}

variable "repo_name" {
  description = "Nombre del Artifact Registry"
  type        = string
}