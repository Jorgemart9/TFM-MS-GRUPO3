terraform {
  required_version = ">= 1.5.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.11.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.11.0"
    }
  }
  backend "gcs" {
    bucket = "models-artifacts-tfm"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = "tfm-ms-3"
  region  = "europe-west1"
}

provider "google-beta" {
  project = "tfm-ms-3"
  region  = "europe-west1"
}
