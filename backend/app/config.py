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
        "ip": "10.100.0.198",
        "ssh_target": "localhost",
        "role": "management",
        "rack_id": "rack-0",
        "cpu_model": "Intel Xeon-Silver 4514Y",
        "cpu_cores": 16,
        "memory_gib": 32,
        "psu_watts": 500,
        "peak_draw_watts": 190,
    },
    {
        "node_id": "compute-01",
        "display_name": "Compute-001",
        "instance": "10.100.0.66:9100",
        "ip": "10.100.0.66",
        "ssh_target": "10.100.0.66",
        "role": "compute",
        "rack_id": "rack-1",
        "cpu_model": "Intel Xeon-Gold 5412Y",
        "cpu_cores": 24,
        "memory_gib": 64,
        "psu_watts": 800,
        "peak_draw_watts": 325,
    },
    {
        "node_id": "compute-02",
        "display_name": "Compute-002",
        "instance": "10.100.0.167:9100",
        "ip": "10.100.0.167",
        "ssh_target": "10.100.0.167",
        "role": "compute",
        "rack_id": "rack-1",
        "cpu_model": "Intel Xeon-Gold 5412Y",
        "cpu_cores": 24,
        "memory_gib": 64,
        "psu_watts": 800,
        "peak_draw_watts": 325,
    },
    {
        "node_id": "compute-03",
        "display_name": "Compute-003",
        "instance": "10.100.0.198:9100",
        "ip": "10.100.0.198",
        "ssh_target": "10.100.0.198",
        "role": "compute",
        "rack_id": "rack-1",
        "cpu_model": "Intel Xeon-Gold 5412Y",
        "cpu_cores": 24,
        "memory_gib": 64,
        "psu_watts": 800,
        "peak_draw_watts": 325,
    },
]

# Unsupervised 10-feature baseline contract from Modelling_Predictive_HPC_Cleaned.ipynb
UNSUPERVISED_BASE_FEATURES = [
    "cpu_utilization_percent",
    "cpu_iowait_percent",
    "load1",
    "load5",
    "load15",
    "memory_used_percent",
    "disk_read_bytes_per_second",
    "disk_write_bytes_per_second",
    "network_receive_bytes_per_second",
    "network_transmit_bytes_per_second",
]

# Default Smart Priority, Resource Threshold & Persistence Alert Policy
ALERT_POLICY = {
    "p3_watch_prob": 0.015,           # Validated >=94% event-recall threshold from notebook
    "p2_warning_prob": 0.18,          # Elevated 1h failure probability
    "p1_critical_prob": 0.40,         # High-confidence impending failure threshold
    "persistence_p1_p3": 2,           # 2-of-2 consecutive observations required
    "persistence_p2_anomaly": 3,      # 3-of-3 consecutive observations for pure unsupervised alerts
    "cooldown_minutes": 30,           # 30-minute repeat alert suppression (STUDENT_GUIDE Sec 5)
    "scratch_critical_percent": 90.0, # Shared /scratch pool critical threshold
    "cpu_warning_percent": 95.0,      # Sustained CPU saturation warning threshold
    "memory_warning_percent": 88.0,   # Memory threshold violation warning
    "memory_critical_percent": 95.0,  # Memory threshold violation critical
    "temp_warning_celsius": 78.0,     # Package thermal warning threshold
    "temp_critical_celsius": 86.0,    # Package thermal critical threshold
}

APP_METADATA = {
    "name": "Sol Plaatje A Dev Cluster Dashboard",
    "subtitle": "Monitor • Analyse • Predict • Optimise",
    "version": "2.0.0",
    "organization": "Sol Plaatje University — HPC Student Cluster Competition Team",
}
