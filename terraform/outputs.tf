# Valores que hay que copiar a GitHub tras el bootstrap de WIF (ver SETUP.md).

output "wif_provider" {
  description = "Nombre completo del provider WIF. Va en la variable de repo WIF_PROVIDER."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deploy_sa_email" {
  description = "Email de la SA deployer. Va en la variable de repo DEPLOY_SA_EMAIL."
  value       = google_service_account.github_deployer.email
}
