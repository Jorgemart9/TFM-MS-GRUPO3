# Como trabajamos en este repositorio

En el plan gratuito privado GitHub no puede **forzar** estas reglas, asi
que las cumplimos por acuerdo del equipo. Son la diferencia entre un repo
ordenado y un caos de conflictos.

## Reglas

1. **Nadie hace commits directos a `main`.** `main` siempre debe funcionar.
2. **Todo cambio va en una rama** con nombre descriptivo:
   - `feature/ingesta-bigquery`
   - `fix/error-en-preprocesado`
   - `docs/arquitectura`
3. **Todo se integra mediante Pull Request**, revisado por al menos otra
   persona del grupo antes de fusionar.
4. **No se fusiona un PR con la CI en rojo.**
5. **Ningun secreto entra en el repo.** Credenciales, claves y `.tfvars`
   van fuera (ver `SECURITY.md`).

## Flujo tipico

```bash
git checkout main
git pull
git checkout -b feature/mi-cambio
# ... trabajas y haces commits ...
git push -u origin feature/mi-cambio
# Abres el Pull Request en GitHub y pides revision
```

## Antes del primer commit (cada persona, una sola vez)

```bash
pip install pre-commit
pre-commit install
```

Esto activa los hooks que bloquean secretos antes de subir nada.
