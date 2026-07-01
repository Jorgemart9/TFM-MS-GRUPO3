locals {
  env_vars = {
    # Agregamos .. para salir de la carpeta actual hacia la raíz del proyecto
    for line in split("\n", file("${path.module}/../preprocess/.env")) :
    split("=", line)[0] => split("=", line)[1]
    if length(regexall("^[^#=]+=.+", line)) > 0
  }
}

# =====================================================================
# 1. Servicio de Preprocesamiento (Cloud Run Job)
# =====================================================================
resource "google_cloud_run_v2_job" "preprocess_job" {
  name     = "preprocess"
  location = var.region

  template {
    template {
      service_account = google_service_account.sa_preprocess.email

      containers {
        # Ajustado a 'preprocess-pipeline' según tu docker push real
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.preprocess_repo.name}/preprocess-pipeline:latest"

        # SOLUCCIÓN AL OUT OF MEMORY: Ampliación de recursos
        resources {
          limits = {
            cpu    = "2000m" # 2 vCPUs
            memory = "2Gi"   # 2 Gigabytes de RAM
          }
        }

        # Carga dinámica de las variables del .env
        dynamic "env" {
          for_each = local.env_vars
          content {
            name  = env.key
            value = trimspace(env.value)
          }
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
