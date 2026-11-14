import os
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "").strip()

AUTH_SESSION_HOURS = int(os.getenv("AUTH_SESSION_HOURS", "12"))

AUTH_COOKIE_NAME = os.getenv(
    "AUTH_COOKIE_NAME",
    "spu_aiops_session"
).strip()

AUTH_COOKIE_SECURE = (
    os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
)

FRONTEND_BASE_URL = os.getenv(
    "FRONTEND_BASE_URL",
    "http://localhost:5173"
).rstrip("/")
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"
DB_PATH = BASE_DIR / "hpc_aiops.db"
FRONTEND_DIST_DIR = BASE_DIR.parent / "frontend" / "dist"

# Default path to the SCC synthetic/historical dataset sitting alongside hpc-aiops-dashboard
SCC_DATASET_DIR = Path(
    os.getenv(
        "SCC_DATASET_DIR",
        str(BASE_DIR.parent / "scc_hpc_dataset"),
    )
)


# Infrastructure Endpoints (configurable at runtime via Settings API & persisted in SQLite)
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000")
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
# Gemini AI reporting configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
# Backend-only SSH configuration for remote Slurm & Node Log retrieval.
# Credentials/key paths are NEVER exposed to the frontend API responses.
HPC_SSH_HOST = os.getenv("HPC_SSH_HOST", "").strip()
HPC_SSH_USER = os.getenv("HPC_SSH_USER", "ubuntu").strip()
HPC_SSH_PORT = int(os.getenv("HPC_SSH_PORT", "22"))
HPC_SSH_KEY_PATH = os.getenv("HPC_SSH_KEY_PATH", "").strip()

# Optional admin token for protected destructive operations when exposed on a shared network
HPC_ADMIN_TOKEN = os.getenv("HPC_ADMIN_TOKEN", "").strip()

# Baseline 4-node cluster topology metadata (dynamically overridden/enriched by live Prometheus discovery)
LIVE_CLUSTER_NODES = [
    {
        "node_id": "head-node",
        "display_name": "Head Node",
        "instance": "127.0.0.1:9100",
        "ip": "127.0.0.1",
        "ssh_target": "localhost",
        "role": "management",
        "rack_id": "rack-0",
        "cpu_model": "x86_64 Server Processor",
        "cpu_cores": 8,
        "memory_gib": 16,
    },
    {
        "node_id": "compute-01",
        "display_name": "Compute-001",
        "instance": "10.100.0.198:9100",
        "ip": "10.100.0.198",
        "ssh_target": "10.100.0.198",
        "role": "compute",
        "rack_id": "rack-1",
        "cpu_model": "x86_64 Compute Node",
        "cpu_cores": 8,
        "memory_gib": 16,
    },
    {
        "node_id": "compute-02",
        "display_name": "Compute-002",
        "instance": "10.100.0.167:9100",
        "ip": "10.100.0.167",
        "ssh_target": "10.100.0.167",
        "role": "compute",
        "rack_id": "rack-1",
        "cpu_model": "x86_64 Compute Node",
        "cpu_cores": 8,
        "memory_gib": 16,
    },
    {
        "node_id": "compute-03",
        "display_name": "Compute-003",
        "instance": "10.100.0.66:9100",
        "ip": "10.100.0.66",
        "ssh_target": "10.100.0.66",
        "role": "compute",
        "rack_id": "rack-1",
        "cpu_model": "x86_64 Compute Node",
        "cpu_cores": 8,
        "memory_gib": 16,
    },
]

# V7 Isolation Forest cluster API integration (credentials stay backend-only)
V7_API_URL = os.getenv("V7_API_URL", "").strip()
V7_API_KEY = os.getenv("V7_API_KEY", "").strip()
V7_TIMEOUT = float(os.getenv("V7_TIMEOUT", "5.0"))

# LSTM V8 cluster API integration (credentials stay backend-only)
LSTM_V8_API_URL = os.getenv("LSTM_V8_API_URL", "").strip()
LSTM_V8_API_KEY = os.getenv("LSTM_V8_API_KEY", "").strip()
LSTM_V8_TIMEOUT = float(os.getenv("LSTM_V8_TIMEOUT", "5.0"))

# Operational telemetry & detection alert policy defaults
# Note: Hardware sensors (temperature, fan speed, power/energy) are not exposed via
# cluster hwmon interfaces and are intentionally excluded from alert thresholds.
ALERT_POLICY = {
    "cpu_warning_percent": 95.0,        # Sustained CPU saturation warning threshold
    "iowait_warning_percent": 35.0,     # Sustained storage wait warning threshold
    "memory_warning_percent": 88.0,     # Memory usage warning threshold
    "memory_critical_percent": 95.0,    # Memory exhaustion critical threshold
    "scratch_critical_percent": 90.0,   # Shared /scratch pool critical threshold
    "root_critical_percent": 90.0,      # Root filesystem critical threshold
    "normalized_load_warning": 1.25,    # Load1 / CPU cores sustained warning
    "net_error_warning_per_sec": 1.0,   # Interface RX/TX error rate warning
    "mpi_straggler_warning": 0.45,      # Peer CPU/network asymmetry threshold
    "persistence_ticks": 2,             # Consecutive observations before raising episode
    "cooldown_minutes": 30,             # Repeat alert suppression window
    "stale_telemetry_seconds": 120,     # Age at which node telemetry is marked stale
    "enable_v7_alerts": True,           # Raise incident when V7 anomaly exceeds threshold
    "enable_lstm_alerts": True,         # Raise incident when LSTM V8 warning fires
}

APP_METADATA = {
    "name": "Sol Plaatje A Dev Cluster Dashboard",
    "subtitle": "Monitor • Analyse • Predict • Optimise",
    "version": "2.0.0",
    "organization": "Sol Plaatje University — HPC Student Cluster Competition Team",
}
