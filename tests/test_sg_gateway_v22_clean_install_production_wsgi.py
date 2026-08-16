from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"


def test_clean_installer_smoke_and_systemd_target_use_production_wsgi() -> None:
    text = INSTALL.read_text(encoding="utf-8")
    assert text.count("from app.production import app") == 1
    assert "from app.main import create_app" not in text
    assert text.count("app.production:app") == 1
    assert "app.main:app" not in text


def test_production_wsgi_exposes_v4_subscription_contract(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    sys.modules.pop("app.production", None)
    production = importlib.import_module("app.production")
    app = production.app
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    assert endpoints.count("sg_subscription_v1") == 1
    assert endpoints.count("sg_subscription_v1_info") == 1
    assert endpoints.count("sg_subscription_v1_qr") == 1
    assert endpoints.count("sg_subscription_v1_universal_qr") == 1
    assert app.view_functions["sg_subscription_v1"].__module__ == "app.clients.sg_subscription_http_v4"

def test_static_systemd_and_deploy_runtime_sources_use_production_wsgi() -> None:
    unit = (ROOT / "deploy/systemd/sg-gateway.service").read_text(encoding="utf-8")
    assert unit.count("app.production:app") == 1
    assert "app.main:app" not in unit

    checked = [ROOT / "install.sh", ROOT / "deploy/systemd/sg-gateway.service"]
    checked.extend(sorted((ROOT / "deploy").glob("*.sh")))
    checked.extend(sorted((ROOT / "hostd/sg_hostd").glob("*update*.py")))
    stale = []
    for candidate in checked:
        if not candidate.is_file():
            continue
        body = candidate.read_text(encoding="utf-8", errors="replace")
        if "app.main:app" in body:
            stale.append(candidate.relative_to(ROOT).as_posix())
    assert stale == []

