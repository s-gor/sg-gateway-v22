from __future__ import annotations

from pathlib import Path

from app.mihomo import service

ROOT = Path(__file__).resolve().parents[1]


def test_mihomo_tls_ready_uses_public_state(monkeypatch):
    monkeypatch.setattr(
        service,
        "_tls_state",
        lambda: {
            "domain": "vpn.example.com",
            "https_ready": True,
            "certificate": {
                "subject": "CN=vpn.example.com",
                "not_after": "2030-01-01T00:00:00+00:00",
            },
        },
    )

    assert service._tls_ready("vpn.example.com") is True
    assert service._tls_ready("other.example.com") is False
    assert service._tls_ready("") is False


def test_mihomo_tls_ready_does_not_inspect_letsencrypt():
    source = (ROOT / "app/mihomo/service.py").read_text(encoding="utf-8")
    function = source.split("def _tls_ready", 1)[1].split(
        "def _deployment_config", 1
    )[0]

    assert "_tls_state()" in function
    assert "_tls_paths(" not in function
    assert "is_file()" not in function
