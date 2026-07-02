# Puesta en marcha del repositorio (plan gratuito, privado)

## 1. Crear el repo en GitHub
- Boton **New repository** -> nombre del TFM -> visibilidad **Private**.
- NO marques "Add a README" si vas a subir estos ficheros desde local
  (para evitar conflictos). Si lo marcas, luego haz `git pull` primero.

## 2. Anadir a tu companera (y a quien proceda)
- Settings -> Collaborators -> Add people -> rol **Write**.
- Deja **Admin** solo a una persona mas como respaldo.

## 3. Activar 2FA (todos los miembros)
- Settings de cada cuenta -> Password and authentication -> 2FA.

## 4. Subir este kit
Coloca estos ficheros en la raiz del proyecto y:

```bash
git init
git add .
git commit -m "chore: estructura inicial y seguridad del repo"
git branch -M main
git remote add origin git@github.com:USUARIO/REPO.git
git push -u origin main
```

## 5. Cada persona activa los hooks (una sola vez)
```bash
pip install pre-commit
pre-commit install
```

## 6. Activar avisos de dependencias
- Settings -> Code security -> activa **Dependabot alerts** (gratis,
  tambien en repos privados).

## 7. (Opcional) Activar el escaneo de secretos nativo
- El escaneo de secretos con "push protection" de GitHub es gratis en
  repos **publicos**. En privados gratuitos NO esta disponible: por eso
  usamos gitleaks (pasos 5 y workflow de CI), que cubre lo mismo.

---

## Que SI y que NO tienes en gratuito + privado

| Capacidad                              | Disponible |
|----------------------------------------|------------|
| Repo privado, colaboradores ilimitados | Si         |
| Evitar que se suban secretos (gitleaks)| Si         |
| CI con chequeos en cada PR             | Si         |
| Dependabot (avisos de vulnerabilidades)| Si         |
| Forzar "prohibido push a main"         | No (*)     |
| Forzar revision obligatoria de PR      | No (*)     |

(*) Solo en repos publicos, o con un plan de pago, o con GitHub Pro gratis
del Student Developer Pack creando el repo bajo una **cuenta personal**
(no bajo una organizacion). Mientras tanto, esas dos reglas se cumplen por
acuerdo del equipo (ver CONTRIBUTING.md).

---

# CI / CD

El repo tiene tres piezas de automatizacion en `.github/workflows/`:

- **`security.yml`** (CI): en cada PR y push a main -> gitleaks, terraform
  fmt/validate, tfsec y ruff+pytest.
- **`deploy-services.yml`** (CD): al mergear a main, construye y publica en
  Artifact Registry SOLO las imagenes de los servicios que cambiaron
  (`dash`, `monitoring`, `preprocess`) y actualiza su recurso de Cloud Run.
- **`terraform-plan.yml`** / **`terraform-apply.yml`**: `plan` comentado en
  cada PR que toque `terraform/**`, y `apply` (con aprobacion manual) al
  mergear a main.

La autenticacion contra GCP es **sin claves** (Workload Identity Federation).

## Bootstrap de WIF (una sola vez, con credenciales de un humano)

Los recursos WIF viven en `terraform/cicd.tf`. Hay que crearlos ANTES de que
el CD funcione:

```bash
gcloud auth application-default login          # credenciales de un admin del proyecto
cd terraform
terraform init                                 # backend GCS gs://tfm-ms-3-tfstate (prefix tfm/app)
terraform apply -target=google_iam_workload_identity_pool.github \
                -target=google_iam_workload_identity_pool_provider.github \
                -target=google_service_account.github_deployer \
                -var="project_id=tfm-ms-3"
terraform output wif_provider      # -> variable de repo WIF_PROVIDER
terraform output deploy_sa_email   # -> variable de repo DEPLOY_SA_EMAIL
```

## Configuracion en GitHub (Settings del repo)

- **Secrets and variables -> Actions -> Variables** (repo):
  - `GCP_PROJECT_ID = tfm-ms-3`
  - `GCP_REGION = europe-west1`
  - `WIF_PROVIDER = <output wif_provider>`
  - `DEPLOY_SA_EMAIL = <output deploy_sa_email>`
- **Environments -> New environment `production`**: anade *Required reviewers*
  (tu usuario). Gatea el `deploy` de Cloud Run y el `terraform apply`.

## ⚠️ Reconciliacion de drift ANTES de habilitar `terraform apply`

Buckets (`raw-data-tfm`, `clean-data-tfm`), service accounts (`sa-*`), el
dataset `analytics_warehouse` y el Job `preprocess` se crearon FUERA de esta
raiz Terraform. Aplicar sobre un estado vacio dara conflictos 409 o propondra
destrucciones. Antes de dejar que corra `terraform-apply.yml`:

1. Ejecuta `terraform plan -var="project_id=tfm-ms-3"` en local y revisa que
   proponga (deberia querer CREAR recursos que ya existen -> hay que importarlos).
2. Importa lo que ya exista, p.ej.:
   ```bash
   terraform import google_storage_bucket.input_bucket raw-data-tfm
   terraform import google_storage_bucket.output_bucket clean-data-tfm
   terraform import google_service_account.sa_dash \
     projects/tfm-ms-3/serviceAccounts/sa-dash@tfm-ms-3.iam.gserviceaccount.com
   # ...idem sa_monitoring, sa_preprocess, dataset, repos AR, job/services de Cloud Run
   ```
3. Repite `terraform plan` hasta que salga **sin destrucciones**. Solo entonces
   es seguro dejar que el workflow aplique automaticamente.
