# Deployment Guide

This guide covers a restricted Linux deployment on an HPC head node or a host with controlled network access to the cluster. The included `deploy-headnode.sh` script builds the frontend, installs backend dependencies, and registers a systemd service. It is a deployment baseline; it does not configure HTTPS, a reverse proxy, firewall rules, backups, or production secrets.

## 1. Deployment layout

- The FastAPI application listens on port `8000`.
- The production frontend is built into `frontend/dist` and served by FastAPI from the same origin when that directory exists.
- SQLite data is stored in `backend/hpc_aiops.db`.
- The backend loads `backend/.env` at startup. The systemd service created by the script uses `backend` as its working directory.
- Prometheus, Slurm/SSH, optional model APIs, and optional AI or email providers must be reachable and configured separately.

For this reason, deploy on the HPC head node or a suitably controlled host. A general static frontend host cannot provide the backend's cluster integrations or SQLite persistence by itself.

## 2. Host prerequisites

Install and configure these on the deployment host before running the script:

- A supported Linux distribution with Python 3 and `venv` support.
- Node.js and npm.
- Git and access to this repository.
- Network access to the intended Prometheus service and any configured integrations.
- A dedicated, non-root service account with read access to the application and write access to `backend/` for the SQLite database.
- A TLS reverse proxy and firewall policy appropriate to the institution's network.

The deployment script uses `npm install`, installs Python requirements, and creates `/etc/systemd/system/spu-hpc-aiops.service` with `sudo`. Review the script and its service user before running it on a production host.

## 3. Configure secrets and integrations

Create `backend/.env` from `backend/.env.example`. Keep it out of Git and restrict its file permissions to the service account and administrators. Configure at least:

```dotenv
AUTH_SECRET_KEY=<long-random-secret>
AUTH_COOKIE_SECURE=true
FRONTEND_BASE_URL=https://<dashboard-hostname>
PROMETHEUS_URL=http://<reachable-prometheus-host>:9090
```

Generate a high-entropy authentication secret on the host, for example with Python's `secrets.token_urlsafe(48)`, and place the result in the environment file without committing it. Set only the integration credentials and SSH settings required by the deployment. Confirm SSH uses a dedicated restricted key and the expected host keys.

The script writes `PROMETHEUS_URL=http://localhost:9090` into the systemd unit. `backend/.env` is loaded by the application and takes precedence only when the corresponding variable is not already set by the process environment. If Prometheus is not local, edit the service configuration or the script so its hard-coded value matches the intended endpoint.

Create the initial administrator using the repository's bootstrap utility after dependencies and environment configuration are in place:

```bash
cd backend
./.venv/bin/python bootstrap_admin.py
```

Run the command interactively on the host and follow its prompts. Do not put administrator passwords in shell history, source files, or Git.

## 4. Build and install the service

From the repository root, run the reviewed deployment script as an administrator with `sudo` available:

```bash
./deploy-headnode.sh
```

The script binds Uvicorn to `0.0.0.0:8000`. Treat port 8000 as an internal application port: restrict it at the host/network firewall and expose the dashboard through a TLS reverse proxy. Configure the proxy to forward normal HTTP requests and WebSocket upgrades, including `/ws/live`, to the local application. Serve the frontend and API from one HTTPS origin where possible; this avoids having to add a production browser origin to the backend's current CORS allowlist.

The script's systemd unit runs as the invoking user (or `SUDO_USER`). Confirm that this is the intended non-root service account and that it owns or can write the database and any generated application files. Review the unit's filesystem, privilege, and restart settings against local operational policy before enabling it.

Useful service commands:

```bash
sudo systemctl status spu-hpc-aiops.service --no-pager
sudo journalctl -u spu-hpc-aiops.service -n 100 --no-pager
sudo systemctl restart spu-hpc-aiops.service
```

The unauthenticated health endpoint is `https://<dashboard-hostname>/api/health`. It only reports API process health; it does not prove Prometheus, SSH, Slurm, or model services are available.

## 5. Production checks

Before inviting users:

1. Verify HTTPS and WebSocket connections through the reverse proxy.
2. Confirm the secure session cookie is set and authentication, logout, and role permissions work.
3. Confirm the initial administrator can sign in and create the intended user accounts.
4. Verify live Prometheus telemetry and each required SSH, Slurm, diagnostics, email, and model integration from the service account.
5. Confirm simulation or replay data is not being presented as live cluster data.
6. Confirm the API port is not reachable from untrusted networks and administrative features are limited to authorized users.
7. Establish SQLite backup retention and access controls. Test restoring a backup while the service is stopped, and include the database and required model/configuration artefacts in the recovery plan.
8. Set up log review, disk-space monitoring, dependency update procedures, and an owner for service incidents.

The application currently stores SQLite data in the repository's `backend/` directory. Protect that directory accordingly, and include it in backup and restore procedures. For a multi-instance deployment or substantial concurrent writes, reassess SQLite and the single-process background polling architecture before scaling out.

## 6. Updating a deployment

Use a reviewed commit or release as the deployment source. Back up the SQLite database, update the checkout, rebuild/install dependencies with the deployment procedure, and restart the systemd service. Check the service journal, health endpoint, authentication, and live integrations after each update. Keep a tested rollback point and a matching database backup.

Do not deploy an unreviewed working tree or copy `.env`, database files, private SSH keys, or model credentials into a public repository.
