terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  # Configura tu backend remoto aquí para producción (GCS)
  # backend "gcs" {
  #   bucket  = "bucket-datos-sucios"
  #   prefix  = "terraform/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}