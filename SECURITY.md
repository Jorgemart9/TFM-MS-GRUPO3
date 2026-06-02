# Seguridad

## Principio basico
El codigo **nunca** contiene credenciales. Los secretos viven fuera:

- **En GCP:** usa Secret Manager.
- **En local:** `gcloud auth application-default login` (no descargues
  claves JSON de cuenta de servicio).
- **En CI/CD (GitHub Actions):** usa Workload Identity Federation, o en su
  defecto los *Secrets* cifrados del repositorio. Nunca claves en el codigo.
- **Terraform:** el estado va en un backend remoto (bucket de GCS con
  versionado y cifrado), nunca en el repo. Ver `terraform/backend.tf.example`.

## Si se filtra un secreto por error

El orden importa. Borrarlo del historial NO basta: hay que asumir que ya
esta comprometido.

1. **Rota/invalida la credencial inmediatamente** (genera una nueva y
   revoca la antigua en GCP / GitHub / donde corresponda).
2. Despues, **borra el secreto del historial de Git** con `git filter-repo`
   o BFG Repo-Cleaner.
3. Avisa al resto del grupo para que hagan `git pull` del historial reescrito.

## Capas de proteccion activas en este repo
- `pre-commit` + `gitleaks`: bloquea secretos antes del commit.
- Workflow de Actions: vuelve a escanear en cada Pull Request.
- `.gitignore`: excluye estado de Terraform, `.tfvars`, claves y `.env`.
