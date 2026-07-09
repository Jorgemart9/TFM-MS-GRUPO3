# SERVICIO PREPROCESAMIENTO
resource "google_cloud_run_v2_job" "preprocess_job" {
  name     = "preprocess"
  location = var.region

  template {
    template {
      service_account = google_service_account.sa_preprocess.email

      containers {
        # Ajustado a 'preprocess-pipeline' según tu docker push real
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.preprocess_repo.name}/preprocess-pipeline:latest"
        
        resources {
          limits = {
            memory = "32 Gi"
            cpu    = "8"
          }
        }

        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "BQ_DATASET"
          value = "analytics_warehouse"
        }
        env {
          name  = "BQ_LOCATION"
          value = var.region
        }
        env {
          name  = "INPUT_BUCKET"
          value = "raw-data-tfm" 
        }
        env {
          name  = "OUTPUT_BUCKET"
          value = "clean-data-tfm" 
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
          value = "0.10" 
        }
      }
    }
  }
}

# SERVICIO DASHBOARD
resource "google_cloud_run_v2_service" "dash_service" {
  name     = "dash"
  location = var.region
  
  template {
    service_account = google_service_account.sa_dash.email
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.dash_repo.name}/dash-app:latest"

      ports {
        container_port = 8080
      }
    }
  }
}


# SERVICIO MONITOREO
# SERVICIO MONITOREO
resource "google_cloud_run_v2_job" "monitoring_job" {
  name     = "monitoring"
  location = var.region

  template {
    template {
      service_account = google_service_account.sa_monitoring.email

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.monitoring_repo.name}/monitoring-app:latest"

        # 1. FORZAMOS EL COMANDO BASE (Ignora el ENTRYPOINT del Dockerfile si estaba corrupto)
        command = ["python"]
        
        # 2. PASAMOS EL SCRIPT COMO PRIMER ARGUMENTO, SEGUIDO DE SUS FLAGS
        args = [
          "test_model_quality.py",
          "--gcp-project", var.project_id,
          "--gcp-location", var.region,
          "--gcs-bucket", "models-artifacts-tfm",
          "--cloud-build-trigger-url", "https://cloudbuild.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/triggers/evaluar-y-exportar-metricas-modelo:run"
        ]

        # Mantienes tus variables de entorno actuales
        env {
          name  = "GCP_PROJECT"
          value = var.project_id
        }

        env {
          name  = "BQ_DATASET"
          value = "gubernatura_modelos"
        }

        env {
          name  = "GCS_BUCKET"
          value = "models-artifacts-tfm"
        }
      }
    }
  }
}