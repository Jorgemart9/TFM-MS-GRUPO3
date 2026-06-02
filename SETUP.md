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
