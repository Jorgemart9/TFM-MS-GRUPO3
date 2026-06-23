resource "google_storage_bucket" "this" {
  name          = var.name
  project       = var.project
  location      = var.location
  storage_class = var.storage_class

  # Seguridad: acceso uniforme (sin ACLs por objeto) y sin exposicion publica.
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # En dev permitimos que Terraform borre el bucket con objetos dentro.
  force_destroy = var.force_destroy

  versioning {
    enabled = var.versioning
  }

  # Reglas para abaratar almacenamiento: transicionar a clases mas frias
  # (Nearline/Coldline) o borrar segun antiguedad del objeto.
  dynamic "lifecycle_rule" {
    for_each = var.lifecycle_rules
    content {
      action {
        type          = lifecycle_rule.value.action_type
        storage_class = lifecycle_rule.value.storage_class
      }
      condition {
        age = lifecycle_rule.value.age
      }
    }
  }

  labels = var.labels
}
