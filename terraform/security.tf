# Red principal
resource "google_compute_network" "vpc" {
  name                    = "gemma-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.enabled_apis]
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
