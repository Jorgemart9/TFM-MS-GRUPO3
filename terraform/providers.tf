terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  # Estado remoto compartido en GCS. Mismo bucket que environments/dev
  # (gs://tfm-ms-3-tfstate) pero con prefix distinto para no colisionar.
  backend "gcs" {
    bucket = "tfm-ms-3-tfstate"
    prefix = "tfm/app"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
