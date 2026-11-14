from datetime import datetime, timezone
import re
import shlex
import time
from typing import Any, Dict, List, Optional, Tuple

from .database import add_system_log, record_slurm_action
from .ssh_bridge import (
    execute_restricted_cluster_command,
    redact_sensitive_text,
    validate_safe_identifier,
)

# Forbidden shell metacharacters (excluding a single validated '| head/tail/grep' filter handled in Python)
FORBIDDEN_METACHARS_RE = re.compile(r"[;&`><$\n\r]")

# Sensitive file/directory substrings strictly blocked from cat / ls / head / tail
SENSITIVE_PATH_SUBSTRINGS = (
    "shadow",
    "gshadow",
    "sudoers",
    ".ssh",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "authorized_keys",
    "private",
    ".pem",
    ".key",
    "munge",
    ".env",
    "hpc_aiops.db",
    "..",
)

ALLOWED_READ_PREFIXES = (
    "/proc/",
    "/sys/",
    "/etc/os-release",
    "/etc/lsb-release",
    "/etc/hosts",
    "/etc/hostname",
    "/etc/slurm",
    "/etc/prometheus",
    "/var/log",
    "/scratch",
    "/shared",
    "/tmp",
    "~",
    ".",
    "/",
)

ALLOWED_BINARIES = {
    "help",
    "status",
    "nodes",
    "uname",
    "uptime",
    "hostname",
    "whoami",
    "id",
    "date",
    "pwd",
    "lscpu",
    "lsmem",
    "lsblk",
    "lspci",
    "lsmod",
    "free",
    "df",
    "vmstat",
    "iostat",
    "mpstat",
    "sensors",
    "ps",
    "top",
    "ip",
    "ss",
    "ethtool",
    "nfsstat",
    "mount",
    "ping",
    "sinfo",
    "squeue",
    "sacct",
    "sdiag",
    "sprio",
    "sshare",
    "scontrol",
    "systemctl",
    "journalctl",
    "dmesg",
    "cat",
    "ls",
    "head",
    "tail",
    "nvidia-smi",
}

TERMINAL_PRESET_GROUPS: List[Dict[str, Any]] = [
    {
        "group": "System & Hardware",
        "commands": [
            {"label": "Uptime & Load", "cmd": "uptime"},
            {"label": "Kernel & Arch", "cmd": "uname -a"},
            {"label": "CPU Topology", "cmd": "lscpu"},
            {"label": "Sensors / Temp", "cmd": "sensors"},
        ],
    },
    {
        "group": "Memory, Storage & PSI",
        "commands": [
            {"label": "Memory (free -h)", "cmd": "free -h"},
            {"label": "Filesystems (df -h)", "cmd": "df -h"},
            {"label": "Top CPU Processes", "cmd": "ps aux --sort=-%cpu | head -n 12"},
            {"label": "Top RAM Processes", "cmd": "ps aux --sort=-%mem | head -n 12"},
            {"label": "Linux PSI CPU/IO", "cmd": "cat /proc/pressure/io"},
        ],
    },
    {
        "group": "Slurm & Interconnect",
        "commands": [
            {"label": "Slurm Nodes (sinfo)", "cmd": "sinfo"},
            {"label": "Job Queue (squeue)", "cmd": "squeue"},
            {"label": "Node Detail (scontrol)", "cmd": "scontrol show node"},
            {"label": "Network Links (ip -br a)", "cmd": "ip -br addr"},
            {"label": "Socket Summary (ss -s)", "cmd": "ss -s"},
        ],
    },
    {
        "group": "Services & Kernel Logs",
        "commands": [
            {"label": "Node Exporter Status", "cmd": "systemctl status prometheus-node-exporter"},
            {"label": "Slurmd Daemon Status", "cmd": "systemctl status slurmd"},
            {"label": "Recent Journal (30)", "cmd": "journalctl -n 30 --no-pager"},
            {"label": "Kernel Ring (dmesg)", "cmd": "dmesg -T | tail -n 25"},
        ],
    },
]


def _extract_safe_post_filter(raw_cmd: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Allow a single safe trailing pipe to `head`, `tail`, or `grep` and execute the filter
    purely in Python so shell=True is NEVER needed on the cluster host.
    """
    if "|" not in raw_cmd:
        return raw_cmd.strip(), None

    parts = raw_cmd.split("|")
    if len(parts) > 2:
        raise ValueError("Only a single trailing '| head', '| tail', or '| grep' filter is permitted.")

    primary = parts[0].strip()
    pipe_expr = parts[1].strip()
    tokens = shlex.split(pipe_expr, posix=True)
    if not tokens:
        raise ValueError("Empty pipe expression.")

    prog = tokens[0]
    if prog in ("head", "tail"):
        n_lines = 15
        if len(tokens) == 2 and tokens[1].startswith("-") and tokens[1][1:].isdigit():
            n_lines = max(1, min(200, int(tokens[1][1:])))
        elif len(tokens) >= 3 and tokens[1] == "-n" and tokens[2].isdigit():
            n_lines = max(1, min(200, int(tokens[2])))
        return primary, {"type": prog, "lines": n_lines}

    if prog == "grep":
        case_insensitive = "-i" in tokens[1:]
        terms = [t for t in tokens[1:] if not t.startswith("-")]
        if len(terms) != 1 or len(terms[0]) > 64:
            raise ValueError("Pipe grep supports a single search term (e.g. '| grep -i error').")
        return primary, {"type": "grep", "term": terms[0], "ignore_case": case_insensitive}

    raise ValueError("Only '| head', '| tail', or '| grep' post-filters are permitted by security policy.")


def _apply_post_filter(text: str, post_filter: Optional[Dict[str, Any]]) -> str:
    if not post_filter or not text:
        return text
    lines = text.splitlines()
    ftype = post_filter["type"]
    if ftype == "head":
        return "\n".join(lines[: post_filter["lines"]])
    if ftype == "tail":
        return "\n".join(lines[-post_filter["lines"] :])
    if ftype == "grep":
        term = post_filter["term"]
        if post_filter.get("ignore_case"):
            term_l = term.lower()
            matched = [ln for ln in lines if term_l in ln.lower()]
        else:
            matched = [ln for ln in lines if term in ln]
        return "\n".join(matched) if matched else f"(no lines matched '{term}')"
    return text


def _validate_path_arg(arg: str) -> None:
    low = arg.lower()
    for bad in SENSITIVE_PATH_SUBSTRINGS:
        if bad in low:
            raise ValueError(f"Access to path '{arg}' is restricted by security policy.")
    if not arg.startswith("-") and not any(arg.startswith(p) for p in ALLOWED_READ_PREFIXES):
        raise ValueError(
            f"Path '{arg}' is outside permitted diagnostic directories (/proc, /sys, /var/log, /scratch, /etc/slurm)."
        )


def parse_and_validate_command(
    raw_command: str,
    confirmed: bool = False,
) -> Tuple[List[str], Optional[Dict[str, Any]], bool, str]:
    """
    Validate and normalize a terminal command string into a safe argument vector.
    Returns (argv, post_filter, requires_confirmation, confirmation_prompt).
    """
    cleaned = (raw_command or "").strip()
    if not cleaned:
        raise ValueError("Empty command.")
    if len(cleaned) > 240:
        raise ValueError("Command exceeds maximum allowed length (240 chars).")
    if FORBIDDEN_METACHARS_RE.search(cleaned):
        raise ValueError(
            "Shell chaining, redirection, and subshell operators (; && || ` $ > <) are disabled by security policy."
        )

    primary_str, post_filter = _extract_safe_post_filter(cleaned)
    try:
        argv = shlex.split(primary_str, posix=True)
    except ValueError as exc:
        raise ValueError(f"Malformed command quoting: {exc}") from exc

    if not argv:
        raise ValueError("Empty command.")

    binary = argv[0]
    if binary not in ALLOWED_BINARIES:
        raise ValueError(
            f"Command '{binary}' is restricted in the web terminal. Type 'help' to list permitted HPC diagnostic commands."
        )

    # Binary-specific safety & non-interactive normalization
    if binary in ("cat", "head", "tail", "ls"):
        path_args = [a for a in argv[1:] if not a.startswith("-")]
        if binary in ("cat", "head", "tail") and not path_args:
            raise ValueError(f"'{binary}' requires an explicit file path (e.g. 'cat /proc/loadavg').")
        for pa in path_args:
            _validate_path_arg(pa)

    elif binary == "top":
        argv = ["top", "-b", "-n", "1"]

    elif binary == "ping":
        targets = [a for a in argv[1:] if not a.startswith("-")]
        if len(targets) != 1 or not validate_safe_identifier(targets[0]):
            raise ValueError("Usage: ping <hostname-or-ip> (automatically bounded to 3 packets).")
        argv = ["ping", "-c", "3", "-W", "2", targets[0]]

    elif binary == "journalctl":
        if "--no-pager" not in argv:
            argv.append("--no-pager")
        if "-n" not in argv and "--lines" not in argv:
            argv.extend(["-n", "60"])
        if "-f" in argv or "--follow" in argv:
            raise ValueError("Streaming '-f' follow flag is not supported in bounded command mode; use '-n 60'.")

    elif binary == "dmesg":
        # Avoid multi-megabyte raw dmesg dumps if no tail filter is attached
        if post_filter is None:
            post_filter = {"type": "tail", "lines": 60}

    elif binary == "systemctl":
        if len(argv) < 2:
            argv = ["systemctl", "list-units", "--type=service", "--state=running", "--no-pager"]
        else:
            sub = argv[1]
            if "--no-pager" not in argv:
                argv.append("--no-pager")
            if sub in ("status", "is-active", "is-enabled", "list-units", "show"):
                pass
            elif sub in ("restart", "reload"):
                allowed_svcs = {"prometheus-node-exporter", "node_exporter", "slurmd", "slurmctld"}
                svc = argv[2] if len(argv) >= 3 else ""
                if svc not in allowed_svcs:
                    raise ValueError(
                        f"systemctl {sub} is only permitted for cluster daemons: {', '.join(sorted(allowed_svcs))}"
                    )
                if not confirmed:
                    return (
                        argv,
                        post_filter,
                        True,
                        f"Restarting service '{svc}' may briefly interrupt telemetry or job scheduling on this node.",
                    )
            else:
                raise ValueError(f"systemctl subcommand '{sub}' is blocked by security policy.")

    elif binary == "scontrol":
        if len(argv) < 2:
            argv = ["scontrol", "show", "node"]
        else:
            sub = argv[1].lower()
            if sub in ("show", "ping", "version"):
                pass
            elif sub == "update":
                if not confirmed:
                    return (
                        argv,
                        post_filter,
                        True,
                        "Applying 'scontrol update' modifies live Slurm node/job scheduling state.",
                    )
            else:
                raise ValueError(f"scontrol subcommand '{sub}' is restricted.")

    return argv, post_filter, False, ""


def _render_help_text() -> str:
    return (
        "Sol Plaatje A Dev Cluster Dashboard — Audited Instance Console\n"
        "----------------------------------------------------------------------\n"
        "System & Hardware : uname -a | uptime | hostname | lscpu | lsblk | sensors\n"
        "Memory & Storage  : free -h | df -h | vmstat | iostat | cat /proc/meminfo\n"
        "Processes & PSI   : ps aux --sort=-%cpu | top | cat /proc/pressure/{cpu,memory,io}\n"
        "Network & Fabric  : ip -br addr | ip -s link | ss -s | ping <node-ip> | nfsstat\n"
        "Slurm Workload    : sinfo | squeue | sacct | sdiag | scontrol show node\n"
        "Daemons & Logs    : systemctl status <svc> | journalctl -n 40 | dmesg -T\n"
        "Console Built-ins : status (live node telemetry) | nodes | clear | help\n"
        "Post-Filters      : Append '| head -n 15', '| tail -n 20', or '| grep -i <term>'\n"
        "----------------------------------------------------------------------\n"
        "Note: Unrestricted shells, credential reads, and destructive commands (rm, reboot,\n"
        "mkfs, sudo) are blocked. All commands are logged to the administrative audit trail."
    )


def _render_builtin_or_emulated(
    argv: List[str],
    node: Dict[str, Any],
    all_nodes: List[Dict[str, Any]],
    slurm_jobs: List[Dict[str, Any]],
    allow_emulation: bool,
) -> Optional[str]:
    binary = argv[0]
    nid = node.get("node_id", "head-node")
    ip = node.get("ip", "127.0.0.1")
    cores = int(node.get("cpu_cores") or 24)
    mem_gib = float(node.get("memory_gib") or 64.0)
    cpu_pct = float(node.get("cpu_utilization_percent") or 0.0)
    iowait_pct = float(node.get("cpu_iowait_percent") or 0.0)
    mem_pct = float(node.get("memory_used_percent") or 0.0)
    swap_pct = float(node.get("swap_used_percent") or 0.0)
    load1 = float(node.get("load1") or 0.0)
    load5 = float(node.get("load5") or 0.0)
    load15 = float(node.get("load15") or 0.0)
    root_pct = float(node.get("root_used_percent") or 31.0)
    scratch_pct = float(node.get("scratch_used_percent") or 46.0)
    uptime_s = float(node.get("node_uptime_seconds") or 432000.0)
    temp_c = node.get("cpu_temperature_celsius")
    now_utc = datetime.now(timezone.utc)

    # Built-ins that always work
    if binary == "help":
        return _render_help_text()
    if binary == "status":
        v7 = node.get("v7_detection") or {}
        lstm = node.get("lstm_v8_status") or {}
        v7_str = (
            f"score={v7.get('anomaly_score'):.4f} (thr={v7.get('threshold')}, anom={v7.get('is_anomaly')})"
            if isinstance(v7.get("anomaly_score"), (int, float))
            else str(v7.get("status", "not_configured"))
        )
        lstm_warn = lstm.get("latest_warning") or {}
        lstm_str = (
            f"warn={lstm_warn.get('is_warning')} (score={lstm_warn.get('warning_score')})"
            if lstm_warn
            else ("pending" if lstm else "unavailable")
        )
        return (
            f"Instance       : {node.get('display_name') or nid} ({nid})\n"
            f"IP / Exporter  : {ip} ({node.get('instance', 'n/a')})\n"
            f"Availability   : {'ONLINE' if node.get('up') == 1 else 'OFFLINE'} | Slurm: {node.get('slurm_state', 'IDLE')}\n"
            f"Operational    : {node.get('health_classification', 'Healthy')} ({node.get('health_status', 'healthy')}) | Alert: {node.get('alert_priority', 'OK')}\n"
            f"CPU / I/O Wait : {cpu_pct:.1f}% / {iowait_pct:.1f}%  (Load: {load1:.2f}, {load5:.2f}, {load15:.2f})\n"
            f"Memory / Swap  : {mem_pct:.1f}% of {mem_gib:.0f} GiB / Swap {swap_pct:.1f}%\n"
            f"Filesystems    : Root / {root_pct:.1f}% | /scratch {scratch_pct:.1f}%\n"
            f"V7 IF / LSTMV8 : V7[{v7_str}] | LSTM[{lstm_str}]"
        )
    if binary == "nodes":
        lines = ["NODE_ID        ROLE         IP              SLURM       STATUS      CPU%    MEM%"]
        for n in all_nodes:
            lines.append(
                f"{str(n.get('node_id', '')):<14} {str(n.get('role', '')):<12} {str(n.get('ip', '')):<15} "
                f"{str(n.get('slurm_state', '')):<11} {str(n.get('health_status', 'healthy')):<11} "
                f"{str(n.get('cpu_utilization_percent', '--')):>5}%  {str(n.get('memory_used_percent', '--')):>5}%"
            )
        return "\n".join(lines)

    if not allow_emulation:
        return None

    # Telemetry-driven emulation when running in Simulator / Dataset Replay mode without live SSH
    days = int(uptime_s // 86400)
    hrs = int((uptime_s % 86400) // 3600)
    mins = int((uptime_s % 3600) // 60)

    if binary == "uptime":
        return f" {now_utc.strftime('%H:%M:%S')} up {days} days, {hrs:2d}:{mins:02d},  1 user,  load average: {load1:.2f}, {load5:.2f}, {load15:.2f}"
    if binary == "hostname":
        return nid
    if binary == "whoami":
        return "ubuntu"
    if binary == "id":
        return "uid=1000(ubuntu) gid=1000(ubuntu) groups=1000(ubuntu),4(adm),27(sudo),998(slurm)"
    if binary == "pwd":
        return "/home/ubuntu"
    if binary == "date":
        return now_utc.strftime("%a %b %d %H:%M:%S UTC %Y")
    if binary == "uname":
        return f"Linux {nid} {node.get('kernel_release') or '6.8.0-48-generic'} #48-Ubuntu SMP PREEMPT_DYNAMIC x86_64 GNU/Linux"
    if binary == "lscpu":
        return (
            f"Architecture:             x86_64\n"
            f"CPU op-mode(s):           32-bit, 64-bit\n"
            f"CPU(s):                   {cores}\n"
            f"Model name:               {node.get('cpu_model') or 'Intel Xeon Gen11'}\n"
            f"Thread(s) per core:       2\n"
            f"Core(s) per socket:       {max(1, cores // 2)}\n"
            f"Socket(s):                1\n"
            f"NUMA node(s):             1"
        )
    if binary == "free":
        used_gib = round(mem_gib * (mem_pct / 100.0), 1)
        avail_gib = round(max(0.1, mem_gib - used_gib), 1)
        swap_tot = 8.0
        swap_used = round(swap_tot * (swap_pct / 100.0), 2)
        return (
            f"               total        used        free      shared  buff/cache   available\n"
            f"Mem:           {mem_gib:>4.0f}Gi      {used_gib:>4.1f}Gi       2.4Gi       0.2Gi       4.1Gi      {avail_gib:>4.1f}Gi\n"
            f"Swap:           8.0Gi      {swap_used:>4.2f}Gi      {8.0 - swap_used:>4.2f}Gi"
        )
    if binary == "df":
        return (
            f"Filesystem              Size  Used Avail Use% Mounted on\n"
            f"/dev/nvme0n1p2          120G  {120 * root_pct / 100:4.0f}G  {120 * (100 - root_pct) / 100:4.0f}G  {root_pct:2.0f}% /\n"
            f"head-node:/srv/scratch  600G  {600 * scratch_pct / 100:4.0f}G  {600 * (100 - scratch_pct) / 100:4.0f}G  {scratch_pct:2.0f}% /scratch"
        )
    if binary == "sensors":
        t_val = f"+{temp_c:.1f}°C" if temp_c is not None else "N/A (sensor unexported)"
        return (
            f"coretemp-isa-0000\n"
            f"Adapter: ISA adapter\n"
            f"Package id 0:  {t_val}  (high = +86.0°C, crit = +96.0°C)"
        )
    if binary in ("ps", "top"):
        node_jobs = [j for j in slurm_jobs if nid in (j.get("nodes") or []) and j.get("state") == "RUNNING"]
        proc_lines = [
            "USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND",
            f"root           1  0.1  0.2 168940 13200 ?        Ss   Oct24   0:19 /sbin/init",
            f"prometheus   912  0.4  0.3 742100 24800 ?        Ssl  Oct24   4:11 /usr/bin/prometheus-node-exporter",
            f"root        1084  0.2  0.4 318400 28400 ?        Sl   Oct24   2:05 /usr/sbin/{'slurmctld' if node.get('role') == 'management' else 'slurmd'}",
        ]
        for idx, jb in enumerate(node_jobs):
            proc_lines.append(
                f"{jb.get('user', 'hpc'):<10} {14200 + idx * 37:>5} {max(5.0, cpu_pct / max(1, len(node_jobs))):>4.1f} "
                f"{max(4.0, mem_pct * 0.7):>4.1f} 8942100 4120000 ?     Rl   10:12  84:20 mpirun ./{jb.get('name', 'solver')}"
            )
        return "\n".join(proc_lines)
    if binary == "sinfo":
        lines = ["PARTITION AVAIL  TIMELIMIT  NODES  STATE NODELIST"]
        for n in all_nodes:
            if n.get("role") != "management":
                lines.append(
                    f"compute*     up   infinite      1  {str(n.get('slurm_state', 'idle')).lower():<5} {n.get('node_id')}"
                )
        return "\n".join(lines)
    if binary == "squeue":
        lines = ["             JOBID PARTITION     NAME     USER ST       TIME  NODES NODELIST(REASON)"]
        for j in slurm_jobs:
            if j.get("state") in ("RUNNING", "PENDING"):
                st_code = "R" if j.get("state") == "RUNNING" else "PD"
                nlist = ",".join(j.get("nodes") or []) or "(Priority)"
                lines.append(
                    f"{str(j.get('job_id')):>18} {str(j.get('partition', 'compute')):>9} {str(j.get('name', 'job'))[:8]:>8} "
                    f"{str(j.get('user', 'user'))[:8]:>8} {st_code:>2}    {j.get('elapsed_hours', 0):.2f}h "
                    f"{max(1, len(j.get('nodes') or [])):>6} {nlist}"
                )
        return "\n".join(lines)
    if binary == "scontrol":
        return (
            f"NodeName={nid} Arch=x86_64 CoresPerSocket={max(1, cores // 2)} "
            f"CPUAlloc={int(round(cores * cpu_pct / 100.0))} CPUTot={cores} CPULoad={load1:.2f}\n"
            f"   RealMemory={int(mem_gib * 1024)} AllocMem={int(mem_gib * 1024 * mem_pct / 100.0)} "
            f"State={node.get('slurm_state', 'IDLE')} NodeAddr={ip}"
        )
    if binary == "ip":
        return (
            f"lo               UNKNOWN        127.0.0.1/8 ::1/128\n"
            f"eth0             UP             {ip}/24 metric 100"
        )
    if binary == "ss":
        return (
            f"Total: {int(node.get('procs_running') or 4) * 38}\n"
            f"TCP:   28 (estab 14, closed 4, orphaned 0, timewait 3)"
        )
    if binary == "cat":
        target_p = next((a for a in argv[1:] if not a.startswith("-")), "")
        if "loadavg" in target_p:
            return f"{load1:.2f} {load5:.2f} {load15:.2f} {int(node.get('procs_running') or 2)}/412 19482"
        if "pressure/cpu" in target_p:
            p = float(node.get("psi_cpu_percent") or 0.2)
            return f"some avg10={p:.2f} avg60={p*0.8:.2f} avg300={p*0.6:.2f} total=184290"
        if "pressure/memory" in target_p:
            p = float(node.get("psi_memory_percent") or 0.05)
            return f"some avg10={p:.2f} avg60={p*0.8:.2f} avg300={p*0.5:.2f} total=41200\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0"
        if "pressure/io" in target_p:
            p = float(node.get("psi_io_percent") or iowait_pct * 0.5)
            return f"some avg10={p:.2f} avg60={p*0.9:.2f} avg300={p*0.7:.2f} total=921400\nfull avg10={p*0.3:.2f} avg60={p*0.2:.2f} avg300=0.10 total=210400"
        if "os-release" in target_p:
            return 'PRETTY_NAME="Ubuntu 24.04.1 LTS"\nNAME="Ubuntu"\nVERSION_ID="24.04"\nID=ubuntu'
    if binary == "systemctl":
        svc = argv[2] if len(argv) >= 3 else "slurmd"
        return (
            f"● {svc}.service - HPC Cluster Service ({svc})\n"
            f"     Loaded: loaded (/lib/systemd/system/{svc}.service; enabled)\n"
            f"     Active: active (running) since {days}d {hrs}h ago\n"
            f"   Main PID: 1084 ({svc})"
        )
    if binary in ("journalctl", "dmesg"):
        return (
            f"{now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')} {nid} kernel: [  0.000000] Linux version 6.8.0-48-generic (Ubuntu 24.04)\n"
            f"{now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')} {nid} node_exporter[912]: Listening on :9100\n"
            f"{now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')} {nid} aiops-agent[1204]: Status={node.get('health_status', 'healthy')} Slurm={node.get('slurm_state', 'IDLE')}"
        )

    return f"[{nid}] Executed '{' '.join(argv)}' (simulated telemetry mode — configure SSH in Settings for live host shell)."


def execute_instance_terminal_command(
    node: Dict[str, Any],
    all_nodes: List[Dict[str, Any]],
    slurm_jobs: List[Dict[str, Any]],
    pipeline_mode: str,
    raw_command: str,
    confirmed: bool = False,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    nid = str(node.get("node_id", "head-node"))
    if not validate_safe_identifier(nid):
        raise ValueError("Invalid node identifier.")

    argv, post_filter, needs_confirm, confirm_msg = parse_and_validate_command(
        raw_command=raw_command,
        confirmed=confirmed,
    )
    if needs_confirm:
        return {
            "requires_confirmation": True,
            "confirmation_message": confirm_msg,
            "node_id": nid,
            "command": raw_command,
        }

    # Check console built-ins ('help', 'status', 'nodes') first
    if argv[0] in ("help", "status", "nodes"):
        out = _render_builtin_or_emulated(argv, node, all_nodes, slurm_jobs, allow_emulation=True) or ""
        out = _apply_post_filter(out, post_filter)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        return {
            "requires_confirmation": False,
            "ok": True,
            "node_id": nid,
            "command": raw_command,
            "output": out,
            "execution_mode": "console_builtin",
            "elapsed_ms": elapsed_ms,
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    target_ip = str(node.get("ssh_target") or node.get("ip") or "localhost")
    ok, raw_out, source = execute_restricted_cluster_command(
        command_args=argv,
        target_node_ip=target_ip,
        timeout_sec=6.0,
    )

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record_slurm_action(
        node_id=nid,
        action="TERMINAL_CMD",
        reason=f"cmd: {' '.join(argv)[:72]}",
        jobs_protected=0,
        core_hours_saved=0.0,
        kwh_saved=0.0,
        executed_mode=source,
    )

    if source in ("live_local_cluster", "live_ssh_gateway"):
        filtered = _apply_post_filter(redact_sensitive_text(raw_out), post_filter)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        add_system_log(
            timestamp_utc=now_iso,
            node_id=nid,
            source="instance-terminal",
            severity="INFO" if ok else "WARNING",
            event_type="terminal_exec",
            message=f"Executed '{' '.join(argv)}' on {nid} via {source} ({elapsed_ms}ms)",
        )
        return {
            "requires_confirmation": False,
            "ok": ok,
            "node_id": nid,
            "command": raw_command,
            "output": filtered or "(command completed with no output)",
            "execution_mode": source,
            "elapsed_ms": elapsed_ms,
            "timestamp_utc": now_iso,
        }

    # SSH Gateway is offline
    if pipeline_mode == "live_prometheus":
        return {
            "requires_confirmation": False,
            "ok": False,
            "node_id": nid,
            "command": raw_command,
            "output": (
                f"[SSH GATEWAY NOT CONNECTED] Live Prometheus mode is active, so host output is never fabricated.\n"
                f"To execute live commands on '{nid}' ({target_ip}):\n"
                f"  1. Open Settings -> SSH Diagnostic Gateway and save SSH Host (e.g. 196.24.241.73) & SSH User (ubuntu), OR\n"
                f"  2. Deploy the backend directly onto the Linux Head Node.\n"
                f"Tip: You can still run built-in telemetry commands 'status', 'nodes', or 'help' right now."
            ),
            "execution_mode": "ssh_offline",
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "timestamp_utc": now_iso,
        }

    # Simulator or SCC Dataset Replay mode -> provide clearly-badged telemetry-driven console output
    emulated = _render_builtin_or_emulated(argv, node, all_nodes, slurm_jobs, allow_emulation=True) or ""
    filtered = _apply_post_filter(emulated, post_filter)
    return {
        "requires_confirmation": False,
        "ok": True,
        "node_id": nid,
        "command": raw_command,
        "output": filtered,
        "execution_mode": "telemetry_emulated",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 1),
        "timestamp_utc": now_iso,
    }
