from pathlib import Path
from types import SimpleNamespace

import pytest

from app.xray import profiles


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = (
    "chrome",
    "brave",
    "edge",
    "firefox",
    "safari",
    "ios",
    "android",
    "opera",
    "vivaldi",
    "360",
    "qq",
    "random",
    "randomized",
    "unsafe",
)


def _base_config(fingerprint: str = "firefox") -> dict:
    return {
        "fingerprint": fingerprint,
        "reality_tcp_enabled": True,
        "reality_tcp_port": 443,
        "xhttp_reality_enabled": False,
        "xhttp_reality_port": 8444,
        "xhttp_reality_path": "/sg-xhttp-reality",
        "xhttp_reality_mode": "stream-one",
        "xhttp_tls_enabled": False,
        "xhttp_tls_port": 8445,
        "xhttp_tls_path": "/sg-xhttp-tls",
        "xhttp_tls_mode": "auto",
        "hysteria2_enabled": False,
        "hysteria2_port": 8446,
        "hysteria2_obfs_mode": "none",
        "hysteria2_finalmask": {},
    }


def _form(fingerprint: str) -> dict:
    return {
        "host": "203.0.113.10",
        "fingerprint": fingerprint,
        "reality_tcp_enabled": "1",
        "reality_tcp_port": "443",
        "xhttp_reality_port": "8444",
        "xhttp_reality_path": "/sg-xhttp-reality",
        "xhttp_reality_mode": "stream-one",
        "xhttp_tls_port": "8445",
        "xhttp_tls_path": "/sg-xhttp-tls",
        "xhttp_tls_mode": "auto",
        "hysteria2_port": "8446",
        "hysteria2_obfs_mode": "none",
    }


def _patch_config(monkeypatch, fingerprint: str = "firefox") -> None:
    settings = SimpleNamespace(host="203.0.113.10", port=443)
    monkeypatch.setattr(
        profiles,
        "_config",
        lambda: (settings, _base_config(fingerprint), {"https_ready": False}),
    )


def test_fingerprint_contract_matches_sg_panel() -> None:
    assert profiles.FINGERPRINT_VALUES == EXPECTED
    assert profiles.FINGERPRINT_DEFAULT == "firefox"
    assert profiles._fingerprint(None) == "firefox"
    assert profiles._fingerprint("Chrome") == "chrome"
    assert profiles._fingerprint("legacy-custom") == "legacy-custom"


def test_known_fingerprint_is_saved_into_xray_candidate(monkeypatch) -> None:
    _patch_config(monkeypatch)

    prepared = profiles._prepare(_form("safari"))

    assert prepared.config["fingerprint"] == "safari"


def test_existing_unknown_legacy_fingerprint_is_preserved(monkeypatch) -> None:
    _patch_config(monkeypatch, "legacy-custom")

    prepared = profiles._prepare(_form("legacy-custom"))

    assert prepared.config["fingerprint"] == "legacy-custom"


def test_new_unknown_fingerprint_is_rejected(monkeypatch) -> None:
    _patch_config(monkeypatch)

    with pytest.raises(profiles.XrayProfilesError, match="Fingerprint"):
        profiles._prepare(_form("made-up-browser"))


def test_connections_ui_contains_full_sg_panel_selector() -> None:
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")

    assert 'name="fingerprint"' in template
    assert 'optgroup label="Браузеры"' in template
    assert 'optgroup label="Автоматический выбор"' in template
    assert 'optgroup label="Расширенные"' in template
    assert "Другое текущее значение" in template
    assert "По умолчанию Mozilla Firefox" in template
    for value in EXPECTED:
        assert f'<option value="{value}"' in template


def test_xray_exports_use_saved_fingerprint_with_firefox_fallback() -> None:
    exports = (ROOT / "app/clients/exports.py").read_text(encoding="utf-8")

    assert 'server_config.get("fingerprint") or "firefox"' in exports
    assert '"fp": fingerprint' in exports
