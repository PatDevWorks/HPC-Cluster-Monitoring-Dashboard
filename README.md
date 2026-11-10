# Sol Plaatje A HPC Dashboard

**HPC Predictive Monitoring and AIOps Platform**

A monitoring and operational support platform developed for the Sol Plaatje University HPC development cluster. The application brings together cluster telemetry, node health monitoring, workload visibility, diagnostics, alert management and machine-learning-assisted anomaly detection.

---

## 1. Project Overview

The dashboard provides a central interface for observing and analysing the operational state of an HPC cluster.

It connects to Prometheus-based telemetry services, processes incoming node metrics, maintains rolling feature information, evaluates node health and distributes monitoring updates to connected dashboard clients.

The current development environment is designed around a four-node cluster:

- One head node.
- Three compute nodes.

The system is intended to support HPC administrators and authorised team members with cluster visibility, diagnostics and operational decision-making.

## 2. Core Capabilities

| Module | Description |
|---|---|
| Cluster Overview | Displays cluster health and operational indicators. |
| Cluster Topology | Provides a view of the configured cluster nodes. |
| Live Monitoring | Displays incoming telemetry and historical monitoring information. |
| AI & Predictions | Presents anomaly and failure-risk information from the configured ML engine. |
| Job Management | Provides Slurm workload and job-management functionality. |
| Node Logs & Diagnostics | Retrieves node logs and diagnostic information. |
| Instance Terminal | Provides an authenticated, restricted terminal interface. |
| Alerts & Incidents | Tracks, acknowledges, silences and resolves alert episodes. |
| Performance Analytics | Provides historical performance analysis. |
| Reports | Supports report previews and data exports. |
| Settings | Allows authorised administrators to configure supported services and monitoring settings. |

Some capabilities depend on external services, cluster connectivity, permissions and available model artefacts.

## 3. Technology Stack

### Frontend

| Technology | Purpose |
|---|---|
| React 18.3.1 | Component-based user interface. |
| Vite 6.2.0 | Frontend development server and production build tooling. |
| Tailwind CSS 4.1.0 | Interface styling. |
| Recharts 2.15.1 | Monitoring charts and data visualisation. |
| Lucide React 0.475.0 | Interface icons. |

### Backend

| Technology | Purpose |
|---|---|
| Python | Backend implementation and data processing. |
| FastAPI | REST API and WebSocket communication. |
| Uvicorn | ASGI application server. |
| Pydantic | Request validation and data modelling. |
| SQLite | Persistent application and monitoring records. |
| Prometheus Client | Prometheus metric exposition. |
| NumPy and Pandas | Numerical processing and data manipulation. |
| Scikit-learn | Machine-learning algorithms. |
| Joblib | Loading and managing saved model artefacts. |
| Requests | HTTP communication with external services. |

### Infrastructure and Monitoring

- Prometheus
- Prometheus Node Exporter
- Slurm Workload Manager
- SSH
- Linux systemd

### Why These Technologies?

**React and Vite:** React provides a component-based interface that allows dashboard modules to be developed and maintained independently. Vite provides a fast development environment and production build process.

**FastAPI:** FastAPI provides the backend API and asynchronous communication capabilities while allowing the application to use Python's data-processing and machine-learning ecosystem.

**Prometheus:** Prometheus provides an established monitoring and metrics collection system. Node Exporter exposes operating-system metrics from the cluster nodes.

**SQLite:** SQLite provides lightweight persistent storage for application settings, telemetry history, alert episodes, audit records and authentication data. It is not intended to replace Prometheus as the primary metrics collection system.

**WebSockets:** WebSockets allow the backend to distribute live monitoring updates to connected frontend clients without relying exclusively on repeated HTTP polling.

**Slurm:** Slurm integration provides workload and scheduler context relevant to HPC operations.

**Scikit-learn:** Scikit-learn provides machine-learning functionality used by the existing model engine and its supporting feature-processing workflow.

---

## 4. System Architecture

The application follows a modular architecture in which the frontend, backend, monitoring infrastructure and persistence layer work together.

### High-Level Data Flow

```text
              HPC CLUSTER
                   |
        +----------+----------+
        |          |          |
     Head Node  Compute 01  Compute 02/03
        |          |          |
        +----------+----------+
                   |
             Node Exporter
                   |
               Prometheus
                   |
                   v
        BACKEND - FASTAPI
                   |
          Cluster Connector
                   |
          Feature Pipeline
                   |
            ML Engine
                   |
            Alert Engine
                   |
          Pipeline Orchestrator
                   |
          +--------+--------+
          |                 |
       SQLite           WebSocket
          |                 |
          |                 v
          |          REACT FRONTEND
          |                 |
          +----------> Dashboard
```

### Backend Responsibilities

The backend is responsible for:

1. Retrieving telemetry from Prometheus or the configured alternative data source.
2. Processing and normalising incoming node metrics.
3. Maintaining rolling feature information.
4. Evaluating node observations through the configured ML engine.
5. Evaluating operational conditions and generating alert episodes.
6. Recording relevant monitoring and operational information.
7. Distributing updated cluster snapshots to connected clients.
8. Providing authenticated API endpoints for dashboard functionality.

### Frontend Responsibilities

The React frontend provides the user-facing interface for:

- Cluster monitoring.
- Node-level performance analysis.
- Prediction and anomaly visualisation.
- Slurm workload management.
- Log inspection and diagnostics.
- Alert management.
- Report generation.
- Administrative configuration.

The frontend communicates with the backend through REST API requests and an authenticated WebSocket connection.

For more information, see [Architecture Documentation](docs/ARCHITECTURE.md).

---

## 5. Repository Structure

```text
hpc-aiops-dashboard/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── cluster_connector.py
│   │   ├── prometheus_service.py
│   │   ├── feature_pipeline.py
│   │   ├── ml_engine.py
│   │   ├── ml_engine_v6.py
│   │   ├── alert_engine.py
│   │   ├── auth_service.py
│   │   ├── auth_security.py
│   │   ├── auth_dependencies.py
│   │   ├── slurm_service.py
│   │   ├── ssh_bridge.py
│   │   ├── terminal_service.py
│   │   ├── logs_diagnostics.py
│   │   └── reports_service.py
│   │
│   ├── requirements.txt
│   ├── create_admin.py
│   ├── reset_member_password.py
│   ├── hpc_aiops.db
│   └── tests/
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── context/
│   │   ├── pages/
│   │   ├── App.jsx
│   │   ├── api.js
│   │   ├── index.css
│   │   └── main.jsx
│   │
│   ├── package.json
│   └── index.html
│
├── grafana/
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── INSTALLATION.md
│   ├── AUTHENTICATION.md
│   ├── MACHINE_LEARNING.md
│   ├── DEPLOYMENT.md
│   └── CONTRIBUTING.md
│
├── deploy-headnode.sh
├── start-dashboard.ps1
├── .gitignore
└── README.md
```

The structure highlights the principal application files. Additional files and generated artefacts may exist in individual directories. The `tests/` directory shown above is a logical reference to the authentication test files in the backend; check its actual location before relying on this tree as an exact directory listing.

### Important Backend Components

| File | Responsibility |
|---|---|
| `main.py` | FastAPI application, API endpoints and pipeline orchestration. |
| `config.py` | Application configuration, cluster topology and monitoring defaults. |
| `database.py` | SQLite database initialisation and persistence operations. |
| `cluster_connector.py` | Retrieves live, simulated or replayed cluster telemetry. |
| `prometheus_service.py` | Queries Prometheus metrics and checks service availability. |
| `feature_pipeline.py` | Maintains rolling features and derived metrics. |
| `ml_engine.py` | Existing machine-learning inference engine. |
| `ml_engine_v6.py` | Client for the separate V6 inference API. |
| `alert_engine.py` | Evaluates monitoring conditions and alert episodes. |
| `auth_service.py` | Account authentication and session operations. |
| `auth_security.py` | Password hashing and security-related operations. |
| `auth_dependencies.py` | Authentication, role and CSRF dependencies. |
| `slurm_service.py` | Slurm-related operations. |
| `ssh_bridge.py` | SSH connectivity and related functionality. |
| `terminal_service.py` | Backend terminal operations. |
| `logs_diagnostics.py` | Node log retrieval and diagnostics. |
| `reports_service.py` | Report generation and export functionality. |

---

## 6. Monitoring Data Modes

The application supports three configured monitoring modes.

| Mode | Description | Intended Use |
|---|---|---|
| `live_prometheus` | Retrieves live metrics from Prometheus. | Actual cluster monitoring. |
| `live_cluster_sim` | Uses simulated cluster telemetry. | Development and demonstrations. |
| `scc_dataset_replay` | Replays the configured SCC dataset. | Historical analysis and controlled testing. |

### Important Distinction

Live telemetry, simulated telemetry and replayed datasets must remain distinguishable.

A dashboard displaying simulated or replayed information does not necessarily represent the current physical state of the HPC cluster.

When Prometheus is unavailable in live mode, the connector reports unavailable node metrics rather than silently presenting fabricated measurements as live observations.

---

## 7. Database and Persistence

The application uses SQLite for lightweight persistent storage.

The database is configured at:

```text
backend/hpc_aiops.db
```

### Current Database Tables

| Table | Purpose |
|---|---|
| `users` | Stores dashboard accounts and roles. |
| `sessions` | Stores hashed server-side session tokens and session metadata. |
| `auth_events` | Records authentication and account-related events. |
| `invitations` | Stores invitation records and their token hashes. |
| `app_settings` | Stores configurable application settings. |
| `telemetry_history` | Stores historical node telemetry and prediction information. |
| `alert_episodes` | Stores alert and incident records. |
| `slurm_actions_audit` | Records Slurm operational actions. |
| `system_logs` | Stores application-generated system log events. |
| `ml_engine_settings` | Stores a separate ML engine enabled/disabled setting. |

### Data Retention

The current implementation applies bounded retention to certain tables:

- Telemetry history is limited to approximately 12,000 records.
- System logs retain the latest 500 records.

SQLite is intended for application persistence and historical dashboard records. It should not be treated as a replacement for a dedicated time-series monitoring platform.

---

## 8. Authentication and Access Control

The application uses authenticated sessions and role-based permissions.

### Available Roles

**Senior Administrator (`senior_admin`)**

Provides access to administrative settings and privileged operational functionality.

**Member (`member`)**

Provides authorised dashboard access subject to the permissions enforced by the backend.

### Authentication Flow

1. The user submits an email address and password.
2. The frontend obtains a CSRF token.
3. The login request is sent to the backend.
4. The backend validates the supplied credentials.
5. A server-side session is created.
6. The session cookie is used for subsequent authenticated requests.
7. The backend checks account status and permissions before granting access.

The frontend sends cookies using `credentials: include` and includes CSRF tokens with state-changing requests.

### Current Implementation Status

The database contains an invitations table, but invitation creation and member-registration endpoints have not been verified as implemented.

Consequently, the presence of invitation-related database structures should not be interpreted as a completed invitation-management workflow.

For account setup and security details, see [Authentication Documentation](docs/AUTHENTICATION.md).

---

## 9. Machine Learning and Predictive Monitoring

The application contains a feature-processing pipeline and a machine-learning engine used to evaluate node observations.

### Feature Processing

The rolling feature pipeline maintains information derived from incoming telemetry, including:

- CPU utilisation.
- CPU I/O wait.
- System load.
- Memory utilisation.
- Disk read and write activity.
- Network traffic.
- Rolling statistical information.
- Node-to-node comparisons.
- Cluster-level workload indicators.

These features provide additional context beyond individual raw metric values.

### Existing ML Engine

The current engine supports saved model artefacts, including:

- Isolation Forest.
- One-Class SVM.
- Local Outlier Factor.
- K-Means.
- A supervised failure prediction model.

The engine can fall back to statistical or heuristic evaluation when the required model artefacts are unavailable.

The actual operating mode depends on which model artefacts are present and successfully loaded.

### V6 Inference Integration

A separate `ml_engine_v6.py` module provides a client for communicating with an external V6 inference API.

This is an API client, not a real-time model training implementation.

Its existence does not mean that the external model is already fully integrated into the active dashboard pipeline.

### Future Development

The intended direction includes:

- Integrating validated real-time telemetry with model workflows.
- Establishing consistent observation windows.
- Supporting controlled model training and evaluation.
- Improving anomaly and failure prediction.
- Maintaining clear distinctions between normal operation, progressive degradation and abnormal operating conditions.

See [Machine Learning Documentation](docs/MACHINE_LEARNING.md).

---

## 10. Running the Development Environment

### Requirements

The development environment requires:

- Python.
- Node.js and npm.
- Git.
- Access to the repository.
- Access to Prometheus and the cluster if live monitoring is required.

The exact supported runtime versions should be confirmed against the deployment environment before upgrading dependencies.

### Windows Startup

From the repository root, execute:

```powershell
.\start-dashboard.ps1
```

The startup script:

1. Checks for the backend virtual environment.
2. Creates it when necessary.
3. Installs backend Python dependencies when setting up the environment.
4. Checks for frontend dependencies.
5. Runs `npm install` when `node_modules` is missing.
6. Starts the backend in a separate PowerShell window.
7. Starts the frontend in another PowerShell window.

### Default Development Addresses

| Service | Address |
|---|---|
| Dashboard frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |

### Manual Startup

Backend:

```powershell
cd backend

python -m venv .venv

.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend, in a separate terminal:

```powershell
cd frontend

npm install

npm run dev
```

The manual backend commands assume that the environment is being prepared from the repository's backend directory.

For more detailed instructions, see [Installation Documentation](docs/INSTALLATION.md).

---

## 11. Deployment

The repository includes a Linux deployment script:

```bash
./deploy-headnode.sh
```

The script is intended for an Ubuntu 24.04 head-node environment.

Its current responsibilities include:

1. Building the React frontend.
2. Creating the backend Python virtual environment.
3. Installing Python dependencies.
4. Creating a systemd service.
5. Configuring the service to start the FastAPI application.
6. Enabling and starting the service.

The backend can also serve the built frontend when the frontend distribution directory exists.

### Deployment Considerations

The current script is a deployment starting point, not a complete production security configuration.

Before exposing the dashboard beyond a trusted development environment, review:

- HTTPS and reverse-proxy configuration.
- Secure cookie configuration.
- Firewall rules.
- SSH key management.
- API key and secret management.
- Database backup and recovery.
- Account administration.
- Logging and service monitoring.
- Access restrictions for administrative operations.

See [Deployment Documentation](docs/DEPLOYMENT.md).

---

## 12. API Overview

The backend exposes REST endpoints for the principal dashboard operations.

| Area | Example Endpoint | Purpose |
|---|---|---|
| Authentication | `/api/auth/login` | Authenticate a dashboard user. |
| Authentication | `/api/auth/me` | Retrieve the current user. |
| Authentication | `/api/auth/logout` | End the current session. |
| Cluster state | `/api/state` | Retrieve the current cluster snapshot. |
| Monitoring | `/api/monitoring/history` | Retrieve historical monitoring information. |
| Machine learning | `/api/models/status` | Retrieve model engine status. |
| Machine learning | `/api/models/reload` | Reload supported model artefacts. |
| Slurm | `/api/slurm/drain` | Drain a node. |
| Slurm | `/api/slurm/resume` | Resume a node. |
| Diagnostics | `/api/logs` | Retrieve node logs. |
| Terminal | `/api/terminal/exec` | Execute supported terminal operations. |
| Analytics | `/api/analytics/summary` | Retrieve analytics summaries. |
| Reports | `/api/reports/export` | Export supported reports. |
| Settings | `/api/settings` | Retrieve administrative configuration. |
| Metrics | `/metrics` | Expose backend Prometheus metrics. |
| Live updates | `/ws/live` | Authenticated WebSocket monitoring stream. |

Access to endpoints depends on authentication, permissions and CSRF requirements.

---

## 13. Security and Operational Considerations

The following practices should be observed when developing, testing or deploying the application.

- Never commit passwords, API keys, private SSH keys or production secrets.
- Do not expose administrative or terminal functionality to untrusted networks.
- Use HTTPS and secure cookies when deploying behind a production reverse proxy.
- Restrict SSH access to authorised cluster nodes and accounts.
- Protect the SQLite database and create backups before maintenance.
- Keep simulation and replay data distinguishable from live cluster telemetry.
- Review destructive Slurm operations before execution.
- Do not expose external machine-learning API keys in frontend code.
- Ensure that only authorised users can access sensitive diagnostics and operational functionality.
- Validate external service connectivity before interpreting monitoring failures as cluster failures.

---

## 14. Development and Contribution

Developers working on the project should:

1. Understand the existing architecture before modifying core services.
2. Preserve the distinction between live, simulated and replayed data.
3. Avoid changing API contracts without coordinating frontend and backend updates.
4. Test authentication and role permissions after security-related changes.
5. Validate frontend production builds.
6. Avoid committing generated databases, secrets or private model artefacts.
7. Document new endpoints, configuration variables and dependencies.
8. Test changes against the development cluster before considering deployment.

See [Contributing Documentation](docs/CONTRIBUTING.md).

---

## 15. Project Status and Future Direction

The dashboard is an active development project.

Its current implementation provides a foundation for:

- Centralised HPC cluster monitoring.
- Prometheus-based telemetry collection.
- Node-level diagnostics.
- Slurm operational integration.
- Machine-learning-assisted monitoring.
- Alert and incident management.
- Authenticated dashboard access.
- Historical analytics and reporting.

Future development is expected to focus on:

- Completing administrative account and invitation management.
- Strengthening security and deployment practices.
- Improving model integration and validation.
- Implementing and evaluating real-time model training workflows.
- Improving cluster failure detection and progressive degradation analysis.
- Preparing a more robust deployment architecture.

The distinction between implemented functionality, partially integrated components and planned functionality should be maintained throughout future development.

---

**Sol Plaatje University**  
**HPC Student Cluster Competition Team**  
**Sol Plaatje A Development Cluster**
