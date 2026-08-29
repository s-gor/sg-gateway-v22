from __future__ import annotations

import json
import shutil
from types import ModuleType


def install(restore: ModuleType) -> None:
    original = restore._local_panel_health

    def health(full: ModuleType) -> None:
        original(full)

        hostd = full._probe(
            ["systemctl", "is-active", "--quiet", "sg-hostd.service"],
            timeout=15,
        )
        if hostd.returncode != 0:
            detail = (hostd.stderr or hostd.stdout or "").strip()[-800:]
            suffix = f": {detail}" if detail else ""
            raise RuntimeError("SG-Gateway hostd is not active after restore" + suffix)

        curl = shutil.which("curl")
        if not curl:
            raise RuntimeError("Cannot validate SG-Gateway hostd health: curl missing")
        sg_env = full._read_env(full.CONFIG_DIR / "sg-gateway.env")
        hostd_url = str(
            sg_env.get("SG_GATEWAY_HOSTD_URL") or "http://127.0.0.1:8090"
        ).strip().rstrip("/")
        response = full._probe(
            [curl, "-fsS", "--max-time", "8", f"{hostd_url}/health"],
            timeout=12,
        )
        if response.returncode != 0:
            detail = (response.stderr or response.stdout or "").strip()[-800:]
            raise RuntimeError("SG-Gateway hostd health check failed: " + detail)
        try:
            payload = json.loads(response.stdout or "{}")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("SG-Gateway hostd returned invalid health JSON") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("service") != "sg-hostd"
            or payload.get("status") != "ok"
        ):
            raise RuntimeError("SG-Gateway hostd health status is not ok")

    restore._local_panel_health = health
