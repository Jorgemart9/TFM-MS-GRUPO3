# Red principal
resource "google_compute_network" "vpc" {
  name                    = "gemma-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.enabled_apis]
}

# Subred con acceso privado para Dataflow y Cloud SQL
resource "google_compute_subnetwork" "subnet" {
  name                     = "gemma-subnet-compute"
  ip_cidr_range            = "10.0.1.0/24"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  private_ip_google_access = true
}

# Conexión Privada para Cloud SQL (VPC Peering interno)
resource "google_compute_global_address" "private_ip_alloc" {
  name          = "gemma-private-ip-alloc"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_alloc.name]

  depends_on = [google_project_service.enabled_apis]
}

# Secret Manager para almacenar la contraseña de Cloud SQL de forma segura
resource "google_secret_manager_secret" "db_password" {
  secret_id  = "gemma-db-password"
  depends_on = [google_project_service.enabled_apis]
  replication {
    auto {}
  }
}

resource "random_password" "pwd" {
  length  = 16
  special = false
}

resource "google_secret_manager_secret_version" "db_password_version" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.pwd.result
}
