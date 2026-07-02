resource "google_cloud_run_v2_job" "preprocess_job" {
  name     = "preprocess"
  location = var.region

  template {
    template {
      service_account = google_service_account.sa_preprocess.email

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.preprocess_repo.name}/preprocess-pipeline:latest"

        resources {
          limits = {
            cpu    = "2"
            memory = "8Gi" # 👈 Subido a 8Gi para evitar OOM con el archivo de 1GB
          }
        }

        # 🚀 EL TRUCO: Mapea las variables a los argumentos que tu script de Python parsea
        args = [
          "--input-path", "gs://raw-data-tfm/df_completo_cr.csv",
          "--output-clean-path", "gs://clean-data-tfm/df_completo_cr_clean.csv",
          "--output-eda-path", "gs://clean-data-tfm/eda_results.json",
          "--sample-fraction", "0.10",
          "--gcp-project", var.project_id
        ]
        
        # Puedes mantener u omitir los bloques env {}, pero con 'args' ya es suficiente.
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
