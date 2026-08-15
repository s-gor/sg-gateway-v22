from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("/opt/sg-gateway/deploy/configure-panel-access.sh")
STATE_DIR = Path(
    os.getenv("SG_GATEWAY_SECURITY_STATE_DIR", "/var/lib/sg-gateway/security")
)


def _request() -> dict:
    try:
        value = json.loads((STATE_DIR / "tls-request.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "issue":
        request = _request()
        domain = str(request.get("domain") or "").strip()
        port = int(request.get("public_port") or request.get("panel_port") or 0)
        if not domain or not port:
            print(
                json.dumps(
                    {"ok": False, "message": "Сначала проверьте домен"},
                    ensure_ascii=False,
                )
            )
            return 1
        command = [
            "/bin/bash",
            str(SCRIPT),
            "--mode",
            "https",
            "--host",
            domain,
            "--port",
            str(port),
        ]
    elif action in {"renew", "rollback"}:
        command = ["/bin/bash", str(SCRIPT), "--mode", action]
    else:
        print(
            json.dumps(
                {"ok": False, "message": "Допустимые действия: issue, renew, rollback"},
                ensure_ascii=False,
            )
        )
        return 1

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    output = (result.stdout or result.stderr or "").strip()
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    message = lines[-1] if lines else "HTTPS command completed"
    print(
        json.dumps(
            {
                "ok": result.returncode == 0,
                "message": message,
                "output": output[-20000:],
            },
            ensure_ascii=False,
        )
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
