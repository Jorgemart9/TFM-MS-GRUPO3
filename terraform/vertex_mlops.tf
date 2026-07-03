
# 1.conexión de cloud build con github
resource "google_cloudbuildv2_connection" "github_connection" {
  location = var.region
  name     = "github-connection"


# 1. Este trigger automatiza la ejecución de Cloud Build para validar el modelo
# antes de pasar al paso de despliegue (Endpoint de Vertex AI).
resource "google_cloudbuild_trigger" "model_quality_gate_trigger" {
  name     = "model-quality-gate"
  location = var.region

  repository_event_config {
    repository = google_cloudbuildv2_repository.tfm_repository.id

    push {
      branch = "^despliegue-modelos$"
    }
  }

  build {
    step {
      name       = "python:3.10-slim"
      entrypoint = "bash"

      args = [
        "-c",
        "pip install -r requirements-test.txt && python test_model_quality.py"
      ]
    }

    step {
      name = "gcr.io/cloud-builders/gcloud"

      args = [
        "ai",
        "models",
        "upload",
        "--region=${var.region}",
        "--display-name=modelo-tfm",
        "--container-image-uri=${var.region}-docker.pkg.dev/${var.project_id}/dash-repo/dash-pipeline:latest"
      ]
    }

    options {
      logging = "CLOUD_LOGGING_ONLY"
    }
  }

  depends_on = [
    google_cloudbuildv2_repository.tfm_repository
  ]
}
resource "google_cloudbuild_trigger" "model_quality_gate_trigger" {
  name        = "model-quality-gate"
  description = "Trigger que ejecuta las pruebas de calidad del modelo (Paso 4 del DAG)"
  location    = var.region

  github {
    owner = "Jorgemart9"
    name  = "TFM-MS-GRUPO3"

    push {
      branch = "^despliegue-modelos$"
    }
  }

  build {
    step {
      name       = "python:3.10-slim"
      entrypoint = "bash"

      args = [
        "-c",
        "pip install -r requirements-test.txt && python test_model_quality.py"
      ]
    }

    step {
      name = "gcr.io/cloud-builders/gcloud"

      args = [
        "ai",
        "models",
        "upload",
        "--region=${var.region}",
        "--display-name=modelo-tfm",
        "--container-image-uri=${var.region}-docker.pkg.dev/${var.project_id}/dash-repo/dash-pipeline:latest"
      ]
    }

    options {
      logging = "CLOUD_LOGGING_ONLY"
    }
  }
}

# 2.Recurso físico en Vertex AI donde se alojará el modelo para servir predicciones en producción (si el Quality Gate da PASS).
resource "google_vertex_ai_endpoint" "model_production_endpoint" {
  name         = "modelo-produccion-endpoint"
  display_name = "Endpoint de Producción - TFM Grupo 3"
  location     = var.region
  description  = "Endpoint gestionado para servir el modelo entrenado"
}