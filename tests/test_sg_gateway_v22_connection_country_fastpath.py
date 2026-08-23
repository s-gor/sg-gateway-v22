from types import SimpleNamespace

from app.connections import service as service_module


def _settings(country_code: str = "unknown", host: str = "203.0.113.10"):
    return SimpleNamespace(
        host=host,
        port=443,
        enabled=True,
        config={"country_code": country_code},
    )


def test_configured_country_skips_geoip_lookup(monkeypatch):
    def unexpected_lookup(_host):
        raise AssertionError("configured country must not trigger GeoIP parsing")

    monkeypatch.setattr(service_module, "lookup_country_code", unexpected_lookup)

    assert service_module._country_for(_settings("de")) == "de"


def test_unknown_country_uses_geoip_fallback(monkeypatch):
    calls = []

    def fake_lookup(host):
        calls.append(host)
        return "fr"

    monkeypatch.setattr(service_module, "lookup_country_code", fake_lookup)

    assert service_module._country_for(_settings("unknown", "198.51.100.20")) == "fr"
    assert calls == ["198.51.100.20"]
