# Deployment and operations

## Configuration

Run `./scripts/configure.sh` before the first Docker start. It creates `.env` with random credentials and directories owned by your account. Compose runs the application with the recorded host UID/GID so it can write the bind-mounted files. If moving to a different host, update those IDs and storage ownership before starting.

When configuration is generated as root, the script assigns UID/GID 10001 to the storage directories and container instead. Existing files from an older installation must also be owned by the configured runtime user.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ADMIN_EMAIL` | `admin` | Initial administrator login. |
| `ADMIN_PASSWORD` | Generated | Initial administrator password, 12–72 UTF-8 bytes. |
| `SECRET_KEY` | Generated | Shared session-signing secret for the app and tile workers. |
| `BIND_ADDRESS` | `127.0.0.1` | Host interface published by Docker. |
| `PORT` | `8000` | Host HTTP port. |
| `SESSION_COOKIE_SECURE` | `0` | Set to `1` when serving over HTTPS. |
| `SPARE_UID`, `SPARE_GID` | Host user/group | Ownership for bind-mounted storage. |
| `GUNICORN_WORKERS` | `1` | Application workers; uploads are shared across workers. |
| `SEED_DEMO_DATA` | `0` | Set to `1` to create a sample study on startup. |
| `ENABLE_JUPYTER` | `0` | Set to `1` and rebuild to install/start notebooks. |
| `JUPYTER_TOKEN` | Generated | Notebook authentication token; required when enabled. |

Bootstrap credentials only create the first administrator. Changing `.env` does **not** reset an existing account's password. Change passwords through the profile or administrator user-management page. Renaming the initial administrator does not recreate a second account.

The supported deployment uses SQLite on local persistent disk. Do not put the database on NFS or share it between independent application deployments. `DATABASE_URL` is available for development, but other database engines are not part of the tested 1.0 deployment.

## Public HTTPS hosting

The default listener is local to the Docker host. Put a TLS reverse proxy such as Caddy or Nginx in front of `127.0.0.1:8000`, preserve the original **Host header including its port**, and enable WebSocket forwarding if using notebooks. Set `SESSION_COOKIE_SECURE=1`, then recreate the services:

```bash
docker compose up -d
```

To expose the HTTP listener directly on a trusted network, set `BIND_ADDRESS=0.0.0.0`. Use HTTPS before inviting remote participants. Nginx limits login request rates and accepts requests up to 64 MiB; dataset uploads use smaller chunks and can exceed that size overall.

## Persistent data and backups

Keep these directories and `.env` together:

- `instance/`: SQLite database, generated secret-key fallback, thumbnail cache.
- `uploads/`: datasets, uploaded study PDFs, and temporary upload state.
- `notebooks/`: optional notebooks and exported CSV data.
- `.env`: bootstrap credentials, session secret, and deployment settings.

For a consistent backup, stop all services before copying the database and files:

```bash
docker compose stop
tar -czf "spare-backup-$(date +%Y%m%d-%H%M%S).tar.gz" .env instance uploads notebooks
docker compose start
```

Store backups privately outside the repository. Restore with the services stopped, preserve file ownership, and run `docker compose up -d --build --wait`. Losing the secret key invalidates sessions; losing the database loses studies and ratings.

Interrupted uploads can be retried using the same upload ID. Abandoned temporary files under `uploads/.uploads/` can be removed during maintenance while the services are stopped.

## Upgrading from a pre-1.0 checkout

1. Back up the existing storage and configuration, then run `docker compose down` from the old checkout before switching to the renamed services. This keeps the old proxy from holding the application port.
2. Review existing accounts. Older versions created `admin` and `test` with a shared password and seeded four demo participants. Change any retained passwords and remove unwanted demo/test accounts and studies through the UI. Version 1.0 does not delete existing data automatically.
3. Run `./scripts/configure.sh` if `.env` does not exist. If it does, add the variables listed above and create any missing storage directories.
4. Build and start with `docker compose up -d --build --wait`.
5. Confirm `/healthz` reports `1.0.0`, log in, and check an existing study and CSV export.

The existing additive migration for `default_image_viewer` is retained. Pending saves from older browser versions should be synced before upgrading; 1.0 scopes new browser save queues to the participant account.

### Renaming an existing SynEval installation

SPaRE uses the repository/image name `spare-pathology` and Compose services `spare`, `spare-tiles`, and `spare-proxy`. Keep `.env`, `instance/`, `uploads/`, and `notebooks/` when moving to the new checkout. Stop the old services first as described above; do not run both deployments against the same database.

Existing `instance/syneval.db` files are reused automatically, including when both database filenames exist. New installations use `instance/spare.db`. An explicit `DATABASE_URL` overrides this selection when running the app directly. Session keys and uploaded-file paths are unchanged. Existing `SYNEVAL_UID`/`SYNEVAL_GID` settings remain supported; `SPARE_UID`/`SPARE_GID` take precedence when set.

On the same browser origin, SPaRE migrates the theme and account-specific pending rating saves to its new storage keys. When both queue versions exist, the newest edit for each answer wins. Sync pending work before moving to a different hostname or port, since browsers keep local storage separately for each origin.

## Optional notebooks

Set `ENABLE_JUPYTER=1` and keep a strong `JUPYTER_TOKEN` in `.env`, then run:

```bash
docker compose up -d --build --wait
```

The evaluation page shows **Analysis Notebook** when enabled. Notebook traffic goes through `/jupyter/` on the same host; no separate public notebook port is needed. Jupyter keeps its normal token authentication and XSRF protection. Notebooks execute code with access to the application's mounted data, so give the notebook token only to trusted administrators.

## Troubleshooting

- **Missing ADMIN_PASSWORD or SECRET_KEY:** run `./scripts/configure.sh` or complete an existing `.env`.
- **Permission denied on storage:** verify `SPARE_UID`/`SPARE_GID` match the owners of the three bind-mounted directories.
- **Viewer unavailable:** inspect `docker compose logs spare`; XOpat must start alongside Gunicorn.
- **Cross-origin request rejected:** keep the browser and API on the same host, and preserve the Host header through reverse proxies.
- **Notebook unavailable:** enable the option and rebuild the image; restarting alone does not install the optional dependencies.
- **Health check failure:** inspect `docker compose logs spare spare-tiles spare-proxy` and check available disk space.
