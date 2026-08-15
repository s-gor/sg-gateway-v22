from __future__ import annotations

from pathlib import Path

_CACHE: dict[str, object] = {
    "total": None,
    "idle": None,
    "pids": {},
}


def _proc_group(comm: str, cmdline: str):
    text = f"{comm} {cmdline}".lower()
    comm_low = comm.lower()

    if comm_low == "xray" or "/xray" in text:
        return ("xray", "Xray", "#4f9bff")

    if (
        "sg-gateway" in text
        or "waitress" in text
        or "app.main:app" in text
        or "app.main:create_app" in text
    ):
        return ("gateway", "SG-Gateway", "#38c6c2")

    if comm_low.startswith("nginx") or " nginx" in text:
        return ("nginx", "Nginx", "#9b7bff")

    if comm_low == "mihomo" or "/mihomo" in text:
        return ("mihomo", "Mihomo", "#4ecb86")

    if comm_low == "sing-box" or "sing-box" in text:
        return ("singbox", "sing-box", "#e7c45b")

    return None


def _read_cpu_total() -> tuple[int, int]:
    try:
        fields = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()
        if not fields or fields[0] != "cpu":
            return (0, 0)
        values = [int(value) for value in fields[1:9]]
    except (OSError, ValueError, IndexError):
        return (0, 0)

    total = sum(values)
    idle = values[3] + values[4] if len(values) > 4 else values[3]
    return (total, idle)


def _format_uptime() -> str:
    try:
        seconds = int(float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0]))
    except (OSError, ValueError, IndexError):
        return "—"

    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60

    if days:
        return f"{days}д {hours}ч"
    if hours:
        return f"{hours}ч {minutes}м"
    return f"{minutes}м"


def collect_cpu_activity(cpu_count: int, load: tuple[float, float, float]) -> dict:
    total_now, idle_now = _read_cpu_total()

    previous_total = _CACHE.get("total")
    previous_idle = _CACHE.get("idle")
    previous_pids = _CACHE.get("pids")
    if not isinstance(previous_pids, dict):
        previous_pids = {}

    process_total = 0
    running_total = 0
    current_pids: dict[int, int] = {}
    group_ticks: dict[str, int] = {}
    group_meta: dict[str, tuple[str, str]] = {}
    group_present: set[str] = set()

    proc = Path("/proc")
    try:
        entries = list(proc.iterdir()) if proc.exists() else []
    except OSError:
        entries = []

    for item in entries:
        if not item.name.isdigit():
            continue

        try:
            raw_stat = (item / "stat").read_text(encoding="utf-8")
            right = raw_stat.rsplit(")", 1)[1].split()
            state = right[0]
            ticks = int(right[11]) + int(right[12])
            comm = (item / "comm").read_text(encoding="utf-8").strip()
            try:
                cmdline = (
                    (item / "cmdline")
                    .read_bytes()
                    .replace(b"\x00", b" ")
                    .decode("utf-8", errors="replace")
                )
            except OSError:
                cmdline = ""
        except (OSError, ValueError, IndexError):
            continue

        pid = int(item.name)
        process_total += 1
        if state == "R":
            running_total += 1

        current_pids[pid] = ticks

        group = _proc_group(comm, cmdline)
        if group is None:
            continue

        key, label, color = group
        group_present.add(key)
        group_meta[key] = (label, color)

        previous_ticks = previous_pids.get(pid)
        if isinstance(previous_ticks, int) and ticks >= previous_ticks:
            group_ticks[key] = group_ticks.get(key, 0) + (ticks - previous_ticks)

    delta_total = 0
    delta_idle = 0

    if isinstance(previous_total, int) and total_now >= previous_total:
        delta_total = total_now - previous_total
    if isinstance(previous_idle, int) and idle_now >= previous_idle:
        delta_idle = idle_now - previous_idle

    if delta_total > 0:
        cpu_percent = max(
            0.0,
            min(100.0, (delta_total - delta_idle) * 100.0 / delta_total),
        )
    else:
        cpu_percent = max(
            0.0,
            min(100.0, (load[0] / max(1, cpu_count)) * 100.0),
        )

    rows: list[dict] = []
    known_percent = 0.0

    for key in group_present:
        label, color = group_meta[key]
        ticks = group_ticks.get(key, 0)
        percent = ticks * 100.0 / delta_total if delta_total > 0 else 0.0
        percent = max(0.0, min(100.0, percent))
        known_percent += percent
        rows.append(
            {
                "key": key,
                "label": label,
                "percent_value": round(percent, 1),
                "percent": f"{percent:.1f}%",
                "bar_width": round(max(2.0, percent), 1) if percent > 0 else 0,
                "color": color,
            }
        )

    other_percent = max(0.0, cpu_percent - known_percent)
    rows.append(
        {
            "key": "other",
            "label": "Система и прочее",
            "percent_value": round(other_percent, 1),
            "percent": f"{other_percent:.1f}%",
            "bar_width": round(max(2.0, other_percent), 1) if other_percent > 0 else 0,
            "color": "#7890a8",
        }
    )

    rows.sort(key=lambda item: float(item["percent_value"]), reverse=True)

    _CACHE["total"] = total_now
    _CACHE["idle"] = idle_now
    _CACHE["pids"] = current_pids

    return {
        "percent": round(cpu_percent),
        "percent_value": round(cpu_percent, 1),
        "rows": rows,
        "uptime": _format_uptime(),
        "processes": process_total,
        "running": running_total,
    }
