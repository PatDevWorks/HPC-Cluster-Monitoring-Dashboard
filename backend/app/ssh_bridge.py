from pathlib import Path
import platform
import re
import shlex
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from .config import HPC_SSH_HOST, HPC_SSH_KEY_PATH, HPC_SSH_PORT, HPC_SSH_USER
from .database import get_app_settings

SAFE_NODE_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
MAX_OUTPUT_BYTES = 512 * 1024  # 512 KB hard ceiling per command output

# Redaction patterns ensuring credentials, keys, tokens, or secrets never leak in logs/bundles
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"(?i)(password|passwd|secret|api[_-]?key|bearer|authorization|munge[_-]?key)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"\b([A-Za-z0-9+/]{64,}={0,2})\b"), "[REDACTED_TOKEN]"),
]


def redact_sensitive_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text[:MAX_OUTPUT_BYTES]
    for pattern, repl in SECRET_PATTERNS:
        cleaned = pattern.sub(repl, cleaned)
    return cleaned


def validate_safe_identifier(value: str) -> bool:
    return bool(value and SAFE_NODE_RE.match(value))


def _resolve_ssh_connection() -> Dict[str, Any]:
    """
    Resolve backend-only SSH gateway config without exposing any secret key paths or material.
    """
    settings = get_app_settings()
    host = (settings.get("ssh_host") or HPC_SSH_HOST or "").strip()
    user = (settings.get("ssh_user") or HPC_SSH_USER or "ubuntu").strip()
    port = int(settings.get("ssh_port") or HPC_SSH_PORT or 22)

    key_candidates: List[Path] = []
    if HPC_SSH_KEY_PATH:
        key_candidates.append(Path(HPC_SSH_KEY_PATH).expanduser())
    home = Path.home()
    key_candidates.extend(
        [
            home / ".ssh" / "id_ed25519",
            home / ".ssh" / "id_rsa",
            home / "Downloads" / "id_ed25519",
        ]
    )
    resolved_key: Optional[str] = None
    for cand in key_candidates:
        try:
            if cand.is_file():
                resolved_key = str(cand)
                break
        except Exception:
            continue

    return {
        "is_linux_local": platform.system().lower() == "linux",
        "host": host,
        "user": user,
        "port": port,
        "key_path": resolved_key,
    }


def get_ssh_public_status() -> Dict[str, Any]:
    """Safe status summary for Settings UI (never exposes key paths or credentials)."""
    cfg = _resolve_ssh_connection()
    return {
        "local_linux_execution": cfg["is_linux_local"],
        "ssh_gateway_configured": bool(cfg["host"]),
        "ssh_host": cfg["host"] or ("localhost (Head Node)" if cfg["is_linux_local"] else ""),
        "ssh_user": cfg["user"],
        "ssh_port": cfg["port"],
        "key_detected": bool(cfg["key_path"]),
    }


def execute_restricted_cluster_command(
    command_args: List[str],
    target_node_ip: str = "localhost",
    timeout_sec: float = 6.0,
) -> Tuple[bool, str, str]:
    """
    Execute an allowlisted command array either:
      1. Directly on the Linux Head Node (or via internal SSH to a compute node IP), OR
      2. Via OpenSSH from a remote workstation to the configured Head Node gateway.
    Never accepts arbitrary user shell strings.
    """
    if target_node_ip and target_node_ip != "localhost" and not validate_safe_identifier(target_node_ip):
        return False, "", "Rejected unsafe node target identifier"

    cfg = _resolve_ssh_connection()
    remote_cmd_str = " ".join(shlex.quote(a) for a in command_args)

    # Case 1: Running directly on Linux Head Node
    if cfg["is_linux_local"] and not cfg["host"]:
        try:
            if target_node_ip in ("localhost", "127.0.0.1", "head-node"):
                proc = subprocess.run(
                    command_args,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                    errors="replace",
                )
            else:
                ssh_cmd = [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-o",
                    "ConnectTimeout=4",
                    target_node_ip,
                    remote_cmd_str,
                ]
                proc = subprocess.run(
                    ssh_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                    errors="replace",
                )
            out = redact_sensitive_text(proc.stdout or "")
            err = redact_sensitive_text(proc.stderr or "")
            if proc.returncode == 0 or out.strip():
                return True, out, "live_local_cluster"
            return False, err or "Command returned empty output", "live_local_cluster"
        except Exception as exc:
            return False, str(exc).split("\n")[0][:120], "live_local_cluster"

    # Case 2: Remote SSH gateway configured (e.g. Windows laptop -> Ubuntu Head Node)
    if cfg["host"]:
        if not validate_safe_identifier(cfg["host"]) or not validate_safe_identifier(cfg["user"]):
            return False, "", "Invalid SSH host/user configuration"

        ssh_base = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=4",
            "-p",
            str(cfg["port"]),
        ]
        if cfg["key_path"]:
            ssh_base.extend(["-i", cfg["key_path"]])

        ssh_base.append(f"{cfg['user']}@{cfg['host']}")

        if target_node_ip in ("localhost", "127.0.0.1", "head-node", cfg["host"]):
            ssh_base.append(remote_cmd_str)
        else:
            # Hop from Head Node to internal compute node (10.100.0.x)
            hop_cmd = (
                f"ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=3 "
                f"{shlex.quote(target_node_ip)} {shlex.quote(remote_cmd_str)}"
            )
            ssh_base.append(hop_cmd)

        try:
            proc = subprocess.run(
                ssh_base,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                errors="replace",
            )
            out = redact_sensitive_text(proc.stdout or "")
            err = redact_sensitive_text(proc.stderr or "")
            if proc.returncode == 0 or out.strip():
                return True, out, "live_ssh_gateway"
            return False, err or "SSH command failed", "live_ssh_gateway"
        except Exception as exc:
            return False, str(exc).split("\n")[0][:120], "live_ssh_gateway"

    return False, "Live Linux/SSH gateway not connected (configure Head Node SSH host in Settings or run on Head Node)", "offline"
