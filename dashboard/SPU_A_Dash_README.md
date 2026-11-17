# Sol Plaatje A Dev Cluster Dashboard

## 📖 Overview

The **Sol Plaatje A Dev Cluster Dashboard** is a modern, real‑time monitoring and AI‑ops platform for a four‑node HPC cluster (1 head node + 3 compute nodes). It:

* **Shows live Prometheus metrics** (CPU, memory, disk I/O, network, load, temperature, etc.)
* **Runs a rolling‑feature pipeline** that creates temporal statistics (means, std‑devs, slopes, peer‑differences) on‑the‑fly.
* **Scores each node** with unsupervised anomaly detectors (Isolation Forest, One‑Class SVM, LOF, K‑Means) and an optional supervised failure‑prediction model (`.pkl`).
* **Generates alerts** (P1/P2/P3) through a state‑machine that respects persistence rules and a 30 min webhook cooldown.
* **Provides a clean React UI** with 10 navigation tabs (Overview, Topology, Live Monitoring, AI & Predictions, Job Management, Node Logs, Node Terminal, Alerts & Incidents, Performance Analytics, Settings).
* **Allows the ML engine to be toggled on/off** via the Settings page (or API).
* **Uses a tiny SQLite DB** for UI‑level state (model enable flag, alert episodes, system logs) while heavy telemetry lives in Prometheus and historic data is stored in DuckDB.

The whole project lives under:
```
dashboard/
```

---

## 📂 Repository layout

| Path | Description |
|------|-------------|
| `frontend/` | React + Vite UI source code. |
| `frontend/src/pages/` | One component per navigation tab (`OverviewPage.jsx`, `TopologyPage.jsx`, …). |
| `frontend/src/components/` | Shared UI widgets (`HeaderBar.jsx`, `ThemeContext.jsx`, `ModelToggleCard.jsx`). |
| `frontend/public/` | Static assets (logo images, favicons). |
| `backend/` | FastAPI backend (Python). |
| `backend/app/` | Core modules:
|  `main.py` | FastAPI entry point, registers routers and background tasks. |
|  `config.py` | Global constants, PromQL queries, alert policy, collector thresholds. |
|  `prometheus_service.py` | Pulls the instant metrics from Prometheus. |
|  `feature_pipeline.py` | `RollingFeaturePipeline` – per‑node ring buffers and engineered features. |
|  `ml_engine.py` | Loads `.pkl` artefacts, runs unsupervised + supervised scoring, returns a rich prediction dict. |
|  `alert_engine.py` | `SmartAlertEngine` – persistence counters, alert‑episode DB writes, webhook dispatch. |
|  `database.py` | Thin SQLite wrapper (`app.db`). Creates tables for alerts, system logs, app settings, and the ML‑engine flag. |
|  `ssh_bridge.py`, `slurm_service.py` | SSH helpers for node diagnostics, job management, and terminal access. |
| `backend/models/` | **Hot‑swap model directory** – drop any of the artefacts listed in `README_DROP_MODELS_HERE.md` and the backend will pick them up automatically. |
| `backend/models/README_DROP_MODELS_HERE.md` | Instructions for teammates on what files to copy. |
| `backend/.venv/` | Virtual‑env (created locally for development). |
| `hpc_aiops_dashboard/` | (optional) generated `dist/` folder after `npm run build`. |
| `data/` | DuckDB historical DB (`hpc_exploration.duckdb`) and optional feature‑engineering parquet checkpoints. |
| `HPC_Feature_Engineering_DuckDB_v6.ipynb` | Jupyter notebook that reproduces the exact same feature pipeline on historic data for model training and validation. |
| `Dockerfile` (not shipped yet) | Template for containerising the backend + UI. |

---

## 🛠️ How the dashboard was built – step by step

### 1️⃣  Project scaffolding
1. Created the repo folder `hpc-aiops-dashboard`.
2. Ran `npm create vite@latest frontend --template react` → generated a React + Vite app.
3. Created a Python virtual‑env under `backend/.venv` and installed:
   ```bash
   pip install fastapi uvicorn[standard] duckdb pandas numpy pyarrow matplotlib tzdata
   ```
4. Added a **FastAPI** entry point (`backend/app/main.py`) and wired it to the Vite dev server via CORS.

### 2️⃣  Prometheus integration
* Defined the 10 **core metric PromQL expressions** in `backend/app/config.py` (`INSTANT_PROMQL_QUERIES`).
* Implemented `PrometheusService.fetch_prometheus_cluster_snapshot` to query Prometheus in one HTTP request per metric and return a list of dictionaries (`node_id`, `metric`, `value`, `timestamp`).
* Added health‑check endpoint (`/api/prometheus/health`).

### 3️⃣  Rolling feature pipeline
* Built `RollingFeaturePipeline` (file `feature_pipeline.py`).
  * Holds a `deque(maxlen=72)` per node → ~15 min of 15‑second samples.
  * On each scrape it:
    1. Appends the raw row.
    2. Computes rolling **mean12**, **std12**, **slope12**, **z‑score**, **peer‑diff** for every tracked metric (`cpu_utilization_percent`, `cpu_iowait_percent`, …).
    3. Adds **HPC context**: `normalized_load1`, `cluster_busy_mpi`, `mpi_straggler_score`.
* The enriched dict is handed to the ML engine.

### 4️⃣  Model hot‑swap design
* `backend/models/README_DROP_MODELS_HERE.md` enumerates the artefacts a teammate must provide (scaler, four unsupervised detectors, optional supervised XGBoost/RandomForest model, column‑order JSON, optional `model_metrics.json`).
* `ModelEngine.__init__` calls `reload_models()` which:
  * Scans the directory, loads any `.pkl` with `joblib.load`.
  * Reads `rf_feature_columns.json` if a supervised model exists.
* The **engine can be disabled** via a SQLite flag (`ml_engine_settings.enabled`). The UI toggles it with `POST /api/model/enabled`.

### 5️⃣  Scoring pipeline (`ModelEngine.score_node`)
1. **Gate 0** – checks maintenance flag & exporter availability (`up`). Returns early for maintenance or node‑down.
2. **Stage 1** – runs the four unsupervised detectors (scaled base features) and applies the **MPI guard** (suppresses false positives during heavy MPI jobs). Produces `anomaly_score` and `consensus_count`.
3. **Stage 2** – if a supervised model is present, calls `predict_proba`; otherwise falls back to a calibrated logistic baseline.
4. **Stage 3** – computes feature attributions (model importances or deviation‑based) and classifies the fault (`memory_exhaustion`, `thermal_shutdown`, …) using `PLAYBOOKS`.
5. **Stage 4** – deterministic node health score (0‑100) and returns a rich dict used by the UI and alert engine.

### 6️⃣  Alert engine (`SmartAlertEngine`)
* Reads `ALERT_POLICY` from `config.py` (or overrides from SQLite `app_settings`).
* Maintains per‑node streak counters (`p1`, `p2`, `p3`).
* When a priority threshold is met **and** the required consecutive ticks have passed, it:
  * Inserts/updates a row in `alert_episode` (SQLite).
  * Writes a line to `system_log`.
  * Sends a webhook (if `ALERT_WEBHOOK_URL` is set) respecting a 30 min per‑node cooldown.
* Auto‑resolves after three healthy ticks.

### 7️⃣  Front‑end wiring
* Each page fetches its data via a dedicated endpoint:
  * `/api/raw_metrics` (WebSocket) → Live Monitoring charts.
  * `/api/ml/status` → AI & Predictions KPI cards, top‑feature list, model‑enabled flag.
  * `/api/alerts` → Alerts & Incidents table.
  * `/api/model/enabled` (GET/POST) → Settings page toggle.
* UI uses **TailwindCSS** (optional) and **Recharts** for graphs.
* Added a **ThemeContext** + dark‑mode‑aware SPU logo (`SpuLogo.jsx`).
* Implemented a **ModelToggleCard** component (see `frontend/src/components/ModelToggleCard.jsx`).

### 8️⃣  Historical feature‑engineering notebook
* `HPC_Feature_Engineering_DuckDB_v6.ipynb` reads the historic DuckDB (`hpc_exploration.duckdb`).
* Re‑creates the exact same rolling pipeline (delta handling, negative‑reset detection, collector‑presence baseline) to produce:
  * `feat_15s.parquet` – 15‑second per‑node feature table (used for model training).
  * `feat_1m.parquet` – 1‑minute aggregated table.
  * Collector health reports, benchmark‑event alignment tables.
* The notebook is **read‑only**; it never writes back to the live dashboard DB.

### 9️⃣  SQLite usage (see README section **SQLite** below)
* Stores UI‑level mutable state: model flag, alert episodes, system logs, app settings.
* Small, fast, zero‑config – perfect for a container‑native service.

### 🔟  Deployment scaffolding (Dockerfile template)
A minimal `Dockerfile` (not yet built into the repo) would:
```dockerfile
FROM python:3.12-slim AS backend
WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/ ./
RUN npm install && npm run build
EXPOSE 5173
CMD ["npx", "serve", "-s", "dist", "-l", "5173"]
```
* In production you would run the two stages in separate containers behind a reverse‑proxy (NGINX) or combine them with a multi‑stage build.

---

## 📦 Prerequisites

| Tool | Minimum version | Why needed |
|------|----------------|------------|
| **Node.js** | 20.x | Build and run the React UI (`npm install`, `npm run dev`). |
| **Python** | 3.12 | FastAPI backend, DuckDB, Pandas, NumPy, joblib. |
| **Docker** (optional) | 24.x | Containerised deployment. |
| **Prometheus** | any | Must be scraping the node exporters in the cluster. |
| **DuckDB** (CLI or via Python) | 2.0 | Historical data for model training. |

---

## 🚀 Getting started (local development)

1. **Clone the repo** (or open the existing folder).
2. **Backend**
   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate   # PowerShell
   pip install -r requirements.txt   # (or install the packages listed in the code)
   # Initialise the SQLite DB (runs automatically on first start)
   python -c "import backend.app.database as db; db.init_app_db()"
   uvicorn backend.app.main:app --reload   # runs on http://localhost:8000
   ```
3. **Frontend**
   ```bash
   cd ../frontend
   npm install
   npm run dev   # Vite dev server on http://localhost:5173
   ```
4. **Open the dashboard** – navigate to `http://localhost:5173`. The UI talks to the backend at `http://localhost:8000` (CORS is pre‑configured).
5. **Verify Prometheus connectivity** – edit `backend/app/config.py` if your Prometheus host/port differ, then visit `http://localhost:8000/api/prometheus/health`.

---

## 📊 Adding / Updating a model (Team‑member workflow)

1. Export the following artefacts from the training notebook (`Modelling_Predictive_HPC_Cleaned.ipynb`):
   * `hpc_feature_scaler.pkl`
   * `isolation_forest_hpc.pkl`
   * `one_class_svm_hpc.pkl`
   * `lof_hpc.pkl`
   * `kmeans_hpc.pkl`
   * `kmeans_threshold.pkl`
   * **Either** `final_rf_failure_model.pkl` **or** `final_xgb_failure_model.pkl`
   * `rf_feature_columns.json` (ordered list of column names – must match the enriched feature dict)
   * *(optional)* `model_metrics.json` (precision/recall/F1 for UI display)
2. Copy **all** files into the backend model directory:
   ```bash
   cp *.pkl *.json "../backend/models/"
   ```
3. **Reload the models** from the UI (AI & Predictions → **Reload .pkl Models**) *or* simply restart the backend service.
4. The dashboard will now show `engine_mode: production_pkl_full` and start using the new model for live scoring.

### Disabling the model temporarily
* **Via UI:** Open **Settings** → **ML Engine** toggle.
* **Via API:**
  ```bash
  curl -X POST http://localhost:8000/api/model/enabled -H "Content-Type: application/json" -d '{"enabled": false}'
  ```
* When disabled, `ModelEngine.score_node` returns a neutral payload (all risks = 0, `prediction_source: engine_disabled`). Alerts will not fire.

---

## 🗄️ SQLite – what it stores and why

* `ml_engine_settings` – single row (`enabled` = 0/1) controlling the global ML toggle.
* `alert_episode` – open/closed incidents, priority, fault class, timestamps, playbook command, alert points, and last webhook time.
* `system_log` – chronological audit trail (webhook dispatches, playbook runs, auto‑resolves).
* `app_settings` – JSON key/value store for overridable configs (e.g., custom `ALERT_POLICY`).

The file lives at `backend/app/app.db`. You can inspect it with the SQLite CLI:
```bash
sqlite3 backend/app/app.db "SELECT * FROM alert_episode;"
```

---

## 🛡️ Security & Permissions

* **No secrets** are stored in the repo. The webhook URL (`ALERT_WEBHOOK_URL`) and any SSH keys are injected via environment variables at deployment time.
* The backend **does not expose** raw SSH commands; `ssh_bridge.py` only runs a white‑list of safe commands (see the `PLAYBOOKS` dictionary).
* CORS is restricted to `http://localhost:5173` (dev) or the production domain you configure.

---

## 📦 Production deployment checklist

1. **Build the frontend**:
   ```bash
   cd frontend
   npm run build   # creates ./dist
   ```
2. **Create a Docker image** (use the provided `Dockerfile` template or adapt to your CI). Ensure the built `dist/` folder is copied into the image or served via a separate Nginx container.
3. **Mount a persistent volume** for:
   * `backend/app/app.db` (SQLite state)
   * `backend/models/` (drop‑in models – can be updated without rebuilding the image)
   * `data/` (DuckDB historic DB, optional).
4. **Set environment variables**:
   * `PROMETHEUS_URL` – URL of the Prometheus instance.
   * `ALERT_WEBHOOK_URL` – optional webhook endpoint.
   * `EVENT_TIMEZONE_FOR_NAIVE` – usually `Africa/Johannesburg` unless you store UTC timestamps.
5. **Run the container** (example with Docker Compose):
   ```yaml
   version: "3.9"
   services:
     api:
       image: spau-backend:latest
       ports: ["8000:8000"]
       environment:
         - PROMETHEUS_URL=http://prometheus:9090
         - ALERT_WEBHOOK_URL=https://hooks.mycompany.com/aiops
       volumes:
         - ./backend/models:/app/models
         - ./backend/app/app.db:/app/app.db
   ```
6. **Expose the UI** – serve the `dist/` folder with Nginx or a CDN and point it to the API host.
7. **Verify** the health endpoint (`/api/prometheus/health`) and the `GET /api/model/enabled` flag.

---

## 🧑‍💻 Development workflow tips

* **Run the backend and frontend concurrently** (two terminals) for hot‑reloading.
* **Use the Jupyter notebook** to explore new feature ideas on historic data; the notebook mirrors exactly what the live pipeline does, so any change you make there can be back‑ported to `feature_pipeline.py`.
* **Add unit tests** under `backend/tests/` – the project ships a tiny smoke test (`scratch/smoke_test_backend.py`).
* **Lint** with `flake8` and format with `black` to keep the codebase clean.
* **When adding a new metric**:
  1. Extend `INSTANT_PROMQL_QUERIES` in `config.py`.
  2. Add the metric name to `RollingFeaturePipeline.TRACKED_METRICS`.
  3. Update `UNSUPERVISED_BASE_FEATURES` if it should be part of the unsupervised scaler input.
  4. Re‑train the model and drop the new artefacts into `backend/models/`.

---

## 📚 Glossary

| Term | Meaning |
|------|---------|
| **P1 / P2 / P3** | Alert priorities (Critical, Warning, Watch) defined in `SmartAlertEngine`. |
| **MPI guard** | Logic that suppresses false‑positive CPU spikes when the whole cluster is busy on an MPI job. |
| **Collector baseline** | 95 % presence rule that decides whether a Prometheus collector is considered healthy for that node. |
| **RollingFeaturePipeline** | In‑memory per‑node ring buffer that produces temporal statistics used by the ML models. |
| **ModelEngine** | Wrapper that loads hot‑swap `.pkl` artefacts and produces a `ModelResult` dictionary. |
| **SmartAlertEngine** | State machine that decides when an alert should be opened, persisted, and optionally webhook‑ed. |
| **SQLite `app.db`** | Small relational DB used for UI‑level mutable state; not for telemetry storage. |

---

## 📞 Contact / Contributing

* **Issue tracking** – open a GitHub issue in this repository.
* **Pull requests** – follow the existing code style, run `ruff`/`black` locally, and ensure `npm run build` succeeds before merging.

---

*Last updated: 2026‑11‑05*
