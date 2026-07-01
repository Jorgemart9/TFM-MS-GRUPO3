# ==========================================================
# BASE DE DATOS TRANSACCIONAL: CLOUD SQL (POSTGRESQL)
# ==========================================================
resource "google_sql_database_instance" "db_instance" {
  name                = "app-postgres-${random_id.suffix.hex}"
  database_version    = "POSTGRES_15"
  region              = var.region
  deletion_protection = false

  depends_on = [google_service_networking_connection.private_vpc_connection]

  settings {
    tier = "db-f1-micro"

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.self_link

      # SOLUCIÓN: Quitamos el bloque authorized_networks redundante que causaba el error 400
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
  }
}

# Base de datos lógica
resource "google_sql_database" "main_db" {
  name     = "app_tx_db"
  instance = google_sql_database_instance.db_instance.name
}

# Usuario administrador de PostgreSQL (Cambia root por postgres)
resource "google_sql_user" "db_user" {
  name     = "postgres"
  instance = google_sql_database_instance.db_instance.name
  password = google_secret_manager_secret_version.db_password_version.secret_data
}

# ==========================================================
# ALMACÉN DE DATOS ANALÍTICO: BIGQUERY
# ==========================================================
resource "google_bigquery_dataset" "dataset" {
  dataset_id                  = "analytics_warehouse"
  friendly_name               = "Analytics Warehouse"
  description                 = "Dataset analítico que recibe réplicas por CDC y cargas de Dataflow"
  location                    = var.region
  default_table_expiration_ms = 36000000

  depends_on = [google_project_service.enabled_apis]
}
