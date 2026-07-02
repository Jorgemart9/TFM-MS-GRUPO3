# 1. Servicio de Preprocesamiento (Cloud Run Job)
resource "google_cloud_run_v2_job" "preprocess_job" {
  name     = "preprocess"
  location = var.region

  template {
    template {
      service_account = google_service_account.sa_preprocess.email

      containers {
        # Ajustado a 'preprocess-pipeline' según tu docker push real
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.preprocess_repo.name}/preprocess-pipeline:latest"
        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "INPUT_BUCKET"
          value = "raw-data-tfm" # Solo el nombre plano que pide tu os.environ["INPUT_BUCKET"]
        }
        env {
          name  = "OUTPUT_BUCKET"
          value = "clean-data-tfm" # Solo el nombre plano para tu salida
        }

        env {
          name  = "INPUT_PATH"
          value = "gs://raw-data-tfm/df_completo_cr.csv"
        }
        env {
          name  = "OUTPUT_CLEAN_PATH"
          value = "gs://clean-data-tfm/df_completo_cr_clean.csv"
        }
        env {
          name  = "OUTPUT_EDA_PATH"
          value = "gs://clean-data-tfm/eda_results.json"
        }
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "REGION"
          value = var.region
        }
        env {
          name  = "SAMPLE_FRACTION"
          value = "0.10" # Puedes convertir esto también en una variable de Terraform si quieres
        }
      }
    }
  }
}

# 2. Servicio del Dashboard
resource "google_cloud_run_v2_service" "dash_service" {
  name     = "dash"
  location = var.region

  template {
    service_account = google_service_account.sa_dash.email
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.dash_repo.name}/dash-app:latest"
    }
  }
}

# 3. Servicio de Monitoreo
resource "google_cloud_run_v2_service" "monitoring_service" {
  name     = "monitoring"
  location = var.region

  template {
    service_account = google_service_account.sa_monitoring.email
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.monitoring_repo.name}/monitoring-app:latest"
    }
  }
}
