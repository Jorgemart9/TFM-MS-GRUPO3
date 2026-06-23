output "raw_bucket_name" {
  description = "Nombre del bucket de aterrizaje de datos crudos."
  value       = module.raw_landing.name
}

output "raw_bucket_url" {
  description = "URL gs:// del bucket de aterrizaje."
  value       = module.raw_landing.url
}
