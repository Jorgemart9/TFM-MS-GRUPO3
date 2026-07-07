terraform {
  required_version = ">= 1.5.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.11.0"
    }
  }

  backend "gcs" {
    bucket = "terraform-tfm"  
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}