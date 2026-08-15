from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from app.config import load_config

_LOCK = threading.RLock()
_START_LOCK = threading.Lock()
_STARTED = False
_STATE = None
_SAMPLE_INTERVAL = 10.0


def _primary_interface():
    try:
        for raw in Path("/proc/net/route").read_text(encoding="utf-8").splitlines()[1:]:
            fields = raw.split()
            if len(fields) >= 4 and fields[1] == "00000000":
                try:
                    flags = int(fields[3], 16)
                except ValueError:
                    flags = 0
                if flags & 0x1:
                    return fields[0]
    except OSError:
        pass
    try:
        for path in sorted(Path("/sys/class/net").iterdir()):
            if path.name != "lo":
                return path.name
    except OSError:
        pass
    return None


def _network_totals():
    interface = _primary_interface()
    if not interface:
        return 0, 0
    base = Path("/sys/class/net") / interface / "statistics"
    try:
        rx = int((base / "rx_bytes").read_text(encoding="utf-8").strip())
        tx = int((base / "tx_bytes").read_text(encoding="utf-8").strip())
        return max(0, rx), max(0, tx)
    except (OSError, ValueError):
        return 0, 0


def _boot_id():
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _state_path():
    return load_config().data_dir / "system-activity.json"


def _blank_state():
    return {
        "version": 1,
        "boot_id": "",
        "last_rx": None,
        "last_tx": None,
        "last_sample_at": 0.0,
        "days": {},
        "months": {},
        "hours": {},
    }


def _load_state_unlocked():
    global _STATE
    if _STATE is not None:
        return _STATE
    state = _blank_state()
    path = _state_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            state.update(raw)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    for name in ("days", "months", "hours"):
        if not isinstance(state.get(name), dict):
            state[name] = {}
    _STATE = state
    return state


def _write_state_unlocked(state):
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(tmp, path)
    except OSError:
        pass


def _bucket(container, key):
    item = container.get(key)
    if not isinstance(item, dict):
        item = {"rx": 0, "tx": 0, "peak_bps": 0}
        container[key] = item
    return item


def _prune(state):
    for name, keep in (("hours", 72), ("days", 45), ("months", 15)):
        data = state.get(name, {})
        if not isinstance(data, dict):
            state[name] = {}
            continue
        for key in sorted(data)[:-keep]:
            data.pop(key, None)


def _sample_once():
    now_ts = time.time()
    now = datetime.now().astimezone()
    rx, tx = _network_totals()
    boot = _boot_id()

    with _LOCK:
        state = _load_state_unlocked()
        old_rx = state.get("last_rx")
        old_tx = state.get("last_tx")
        old_boot = str(state.get("boot_id") or "")
        old_at = float(state.get("last_sample_at") or 0.0)

        if old_rx is None or old_tx is None:
            delta_rx = 0
            delta_tx = 0
        elif old_boot != boot or rx < int(old_rx) or tx < int(old_tx):
            delta_rx = 0
            delta_tx = 0
        else:
            delta_rx = max(0, rx - int(old_rx))
            delta_tx = max(0, tx - int(old_tx))

        elapsed = max(0.25, now_ts - old_at) if old_at else _SAMPLE_INTERVAL
        peak_bps = int(((delta_rx + delta_tx) * 8) / elapsed) if elapsed else 0

        for container_name, key in (
            ("days", now.strftime("%Y-%m-%d")),
            ("months", now.strftime("%Y-%m")),
            ("hours", now.strftime("%Y-%m-%dT%H")),
        ):
            item = _bucket(state[container_name], key)
            item["rx"] = int(item.get("rx", 0)) + delta_rx
            item["tx"] = int(item.get("tx", 0)) + delta_tx
            item["peak_bps"] = max(int(item.get("peak_bps", 0)), peak_bps)

        state["last_rx"] = rx
        state["last_tx"] = tx
        state["last_sample_at"] = now_ts
        state["boot_id"] = boot
        _prune(state)
        _write_state_unlocked(state)


def _collector():
    while True:
        try:
            _sample_once()
        except Exception:
            pass
        time.sleep(_SAMPLE_INTERVAL)


def start_system_activity_collector():
    global _STARTED
    with _START_LOCK:
        if _STARTED:
            return
        _STARTED = True
        try:
            _sample_once()
        except Exception:
            pass
        threading.Thread(
            target=_collector,
            name="sg-system-activity",
            daemon=True,
        ).start()


def _format_bytes(value):
    amount = float(max(0, int(value or 0)))
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if amount < 1024 or unit == "PB":
            if unit == "B":
                return f"{int(amount)} B"
            digits = 0 if amount >= 100 else 1 if amount >= 10 else 2
            return f"{amount:.{digits}f} {unit}"
        amount /= 1024
    return "0 B"


def _format_rate(value):
    amount = float(max(0, int(value or 0)))
    for unit in ("bps", "Kbps", "Mbps", "Gbps"):
        if amount < 1000 or unit == "Gbps":
            digits = 0 if amount >= 100 else 1 if amount >= 10 else 2
            return f"{amount:.{digits}f} {unit}"
        amount /= 1000
    return "0 bps"


def collect_system_activity():
    start_system_activity_collector()
    now = datetime.now().astimezone()
    hour_floor = now.replace(minute=0, second=0, microsecond=0)

    with _LOCK:
        state = _load_state_unlocked()
        today = dict(state["days"].get(now.strftime("%Y-%m-%d")) or {})
        month = dict(state["months"].get(now.strftime("%Y-%m")) or {})
        raw_hours = []
        for offset in range(23, -1, -1):
            moment = hour_floor - timedelta(hours=offset)
            item = dict(state["hours"].get(moment.strftime("%Y-%m-%dT%H")) or {})
            rx = max(0, int(item.get("rx", 0)))
            tx = max(0, int(item.get("tx", 0)))
            raw_hours.append({
                "label": moment.strftime("%H:00"),
                "rx": rx,
                "tx": tx,
                "total": rx + tx,
                "peak_bps": max(0, int(item.get("peak_bps", 0))),
            })

    today_rx = max(0, int(today.get("rx", 0)))
    today_tx = max(0, int(today.get("tx", 0)))
    month_rx = max(0, int(month.get("rx", 0)))
    month_tx = max(0, int(month.get("tx", 0)))
    last24_rx = sum(item["rx"] for item in raw_hours)
    last24_tx = sum(item["tx"] for item in raw_hours)
    peak_24h = max((item["peak_bps"] for item in raw_hours), default=0)
    max_hour = max((item["total"] for item in raw_hours), default=0)

    hourly = []
    for item in raw_hours:
        level = round(item["total"] * 100 / max_hour) if max_hour else 0
        hourly.append({
            "label": item["label"],
            "level": max(4, level) if item["total"] else 0,
            "total_text": _format_bytes(item["total"]),
        })

    return {
        "today_total": _format_bytes(today_rx + today_tx),
        "today_rx": _format_bytes(today_rx),
        "today_tx": _format_bytes(today_tx),
        "month_total": _format_bytes(month_rx + month_tx),
        "month_rx": _format_bytes(month_rx),
        "month_tx": _format_bytes(month_tx),
        "last24_total": _format_bytes(last24_rx + last24_tx),
        "peak_24h": _format_rate(peak_24h),
        "hourly": hourly,
        "interface": _primary_interface() or "—",
    }

# Start once when SG-Gateway imports this module.
start_system_activity_collector()
