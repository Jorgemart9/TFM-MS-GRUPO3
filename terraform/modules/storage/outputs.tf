output "name" {
  description = "Nombre del bucket creado."
  value       = google_storage_bucket.this.name
}

output "url" {
  description = "URL gs:// del bucket."
  value       = google_storage_bucket.this.url
}

output "self_link" {
  description = "Self link del bucket."
  value       = google_storage_bucket.this.self_link
}
