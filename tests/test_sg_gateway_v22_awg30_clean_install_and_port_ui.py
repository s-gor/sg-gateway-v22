from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_clean_installers_pin_independent_awg30_runtime_assets() -> None:
    for path in ("install.sh", "deploy/install-core.sh"):
        installer = _read(path)

        assert 'AWG3_TOOLS_VERSION="3.0.20260805"' in installer
        assert 'AWG3_GO_VERSION="v3.0.0"' in installer
        assert (
            'AWG3_TOOLS_VENDOR_FILE="amneziawg-tools-3.0.20260805.tar.gz"'
            in installer
        )
        assert (
            'AWG3_GO_VENDOR_FILE="amneziawg-go-linux-amd64-v3.0.0"'
            in installer
        )
        assert 'AWG3_TOOLS_VENDOR_FILE="amneziawg-tools-3.1.20260812.tar.gz"' not in installer
        assert 'AWG3_GO_VENDOR_FILE="amneziawg-go-linux-amd64-v3.1.20260814"' not in installer


def test_connections_hide_core_xray_ports_but_keep_fingerprint_selector() -> None:
    template = _read("app/web/templates/connections.html")

    assert "<strong>Client Fingerprint</strong>" in template
    assert 'name="fingerprint"' in template

    guard = "{% if profile.id not in ['reality_tcp', 'xhttp_reality'] %}"
    assert guard in template
    guard_start = template.index(guard)
    guard_end = template.index("{% endif %}", guard_start)
    guarded_port_block = template[guard_start:guard_end]

    assert 'name="{{ profile.id }}_port"' in guarded_port_block
    assert "xps2-system-port" not in template
    assert "Системный порт SG-Gateway" not in template
