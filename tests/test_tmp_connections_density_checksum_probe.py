from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "app/web/static/sg-connections-unified-v1.css",
    "app/web/templates/connections.html",
    "tests/test_sg_gateway_02112_all_connections_domain_fix3.py",
    "tests/test_sg_gateway_v22_connections_density_polish.py",
)


def test_tmp_report_connections_density_sha256() -> None:
    rows = [
        f"{hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}  {path}"
        for path in TARGETS
    ]
    raise AssertionError("CONNECTIONS_DENSITY_SHA256\n" + "\n".join(rows))
