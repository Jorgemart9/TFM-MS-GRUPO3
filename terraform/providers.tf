terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.50"
    }

    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.50"
    }
  }

  backend "gcs" {
    bucket = "tfm-ms-3-tfstate"
    prefix = "tfm/app"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
