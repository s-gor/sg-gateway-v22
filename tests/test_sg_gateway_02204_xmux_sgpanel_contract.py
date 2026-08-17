from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from app.xray import xmux
from app.xray.sg_panel_vless import xhttp_reality_inbound

ROOT = Path(__file__).resolve().parents[1]


def test_standard_preset_matches_current_sg_panel_contract() -> None:
    extra = xmux.effective_client_extra({"xhttp_xmux_mode": "auto"})
    assert extra["xmux"] == {
        "maxConnections": "2-4",
        "cMaxReuseTimes": "300-600",
        "hMaxRequestTimes": "1000-2000",
        "hMaxReusableSecs": "1200-2400",
        "hKeepAlivePeriod": 600,
    }


def test_reduced_preset_matches_current_sg_panel_contract() -> None:
    extra = xmux.effective_client_extra({"xhttp_xmux_mode": "reduced"})
    assert extra["xmux"] == {
        "maxConcurrency": 0,
        "maxConnections": "6",
        "cMaxReuseTimes": 0,
        "hMaxRequestTimes": "600-900",
        "hMaxReusableSecs": "1800-3000",
        "hKeepAlivePeriod": 0,
    }
    xmux.validate_xmux_conflicts(extra)


def test_expert_mode_requires_xmux_and_preserves_unrelated_client_extra() -> None:
    with pytest.raises(xmux.XmuxError, match="нужен объект xmux"):
        xmux.effective_client_extra(
            {
                "xhttp_xmux_mode": "expert",
                "xhttp_extra_client_json": {"headers": {"X-Test": "kept"}},
            }
        )

    source = {
        "headers": {"X-Test": "kept"},
        "xmux": {
            "maxConcurrency": "8-16",
            "maxConnections": 0,
            "cMaxReuseTimes": "64-128",
            "hMaxRequestTimes": "600-900",
            "hMaxReusableSecs": "1800-3000",
            "hKeepAlivePeriod": 0,
        },
    }
    assert xmux.effective_client_extra(
        {"xhttp_xmux_mode": "expert", "xhttp_extra_client_json": source}
    ) == source


def test_only_two_positive_xmux_controllers_conflict() -> None:
    with pytest.raises(xmux.XmuxError, match="положительные maxConnections и maxConcurrency"):
        xmux.validate_xmux_conflicts(
            {"xmux": {"maxConcurrency": "2-4", "maxConnections": 6}}
        )
    xmux.validate_xmux_conflicts(
        {"xmux": {"maxConcurrency": 0, "maxConnections": 6}}
    )


def test_xhttp_server_inbound_never_gets_client_xmux() -> None:
    inbound = xhttp_reality_inbound(
        clients=[{"id": "00000000-0000-0000-0000-000000000001"}],
        port=8444,
        path="/sg-xhttp-reality",
        decryption="test-encryption",
        dest="www.microsoft.com:443",
        server_name="www.microsoft.com",
        private_key="private",
        short_id="0123456789abcdef",
    )
    stream = inbound["streamSettings"]
    assert stream["xhttpSettings"]["mode"] == "auto"
    assert "extra" not in stream["xhttpSettings"]
    assert "xmux" not in stream["xhttpSettings"]


def test_export_rewriter_forces_reality_stream_one_and_preserves_full_extra() -> None:
    from app.clients.exports import _rewrite_xhttp_link

    source = "vless://u@example.com:8444?type=xhttp&security=reality&mode=packet-up&extra=%7B%7D#Reality"
    config = {
        "xhttp_xmux_mode": "auto",
        "xhttp_extra_client_json": {"headers": {"X-Test": "kept"}},
    }
    rewritten = _rewrite_xhttp_link(source, "xhttp_reality", config)
    query = parse_qs(urlsplit(rewritten).query)
    assert query["mode"] == ["stream-one"]
    extra = json.loads(query["extra"][0])
    assert extra["headers"] == {"X-Test": "kept"}
    assert extra["xmux"] == xmux.XMUX_STANDARD_PRESET


def test_export_rewriter_keeps_tls_client_mode() -> None:
    from app.clients.exports import _rewrite_xhttp_link

    source = "vless://u@example.com:8445?type=xhttp&security=tls&mode=packet-up#TLS"
    rewritten = _rewrite_xhttp_link(source, "xhttp_tls", {"xhttp_xmux_mode": "reduced"})
    query = parse_qs(urlsplit(rewritten).query)
    assert query["mode"] == ["packet-up"]
    assert json.loads(query["extra"][0])["xmux"] == xmux.XMUX_REDUCED_PRESET


def test_save_normalises_reality_mode_without_touching_server_runtime(monkeypatch) -> None:
    captured: dict[str, object] = {}
    settings = SimpleNamespace(
        host="203.0.113.10",
        port=443,
        config={
            "xhttp_reality_mode": "packet-up",
            "xhttp_tls_mode": "auto",
            "unrelated": {"keep": True},
        },
    )
    monkeypatch.setattr(xmux, "get_connection_settings", lambda engine: settings)

    def fake_update(engine, host, port, config):
        captured.update(engine=engine, host=host, port=port, config=config)
        return True

    monkeypatch.setattr(xmux, "update_connection_settings", fake_update)
    xmux.update_from_form(
        {
            "xhttp_xmux_mode": "auto",
            "xhttp_extra_client_json": '{"headers":{"X-Test":"kept"}}',
        }
    )
    config = captured["config"]
    assert config["xhttp_reality_mode"] == "stream-one"
    assert config["unrelated"] == {"keep": True}
    assert config["xhttp_extra_client_json"] == {"headers": {"X-Test": "kept"}}


def test_connections_ui_exposes_exact_sg_panel_modes_in_full_02204_template() -> None:
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    partial = (ROOT / "app/web/templates/_xray_xmux_settings.html").read_text(encoding="utf-8")
    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")
    js = (ROOT / "app/web/static/sg-xmux-settings-v1.js").read_text(encoding="utf-8")
    assert 'extends "base.html"' in template
    assert 'include "_xray_xmux_settings.html"' in template
    assert "sg-xmux-settings-v1.css" in template
    assert "sg-xmux-settings-v1.js" in template
    # Historical source markers stay in the real template; only the old
    # fixed-RF presentation is hidden in favour of the SG-Panel mode selector.
    assert "xps2-xmux" in template
    assert "XMUX для XHTTP" in partial
    assert "Стандартный" in partial
    assert "Для РФ — уменьшенный" in partial
    assert "Ручной" in partial
    assert "maxConnections 2-4" in partial
    assert "maxConcurrency 0" in partial
    assert ".xps2-xmux" in css and "display: none" in css
    assert '<input type="hidden" name="{{ profile.id }}_mode" value="stream-one">' in template
    assert "Reality XHTTP mode is rendered by the main form as a hidden stream-one" in js
    assert "label.replaceWith" not in js

def test_compact_xmux_uses_mode_dialog_instead_of_permanent_contract_row() -> None:
    partial = (ROOT / "app/web/templates/_xray_xmux_settings.html").read_text(encoding="utf-8")
    js = (ROOT / "app/web/static/sg-xmux-settings-v1.js").read_text(encoding="utf-8")
    publication = (ROOT / "PUBLICATION-02204.md").read_text(encoding="utf-8")

    assert 'class="xmux1-contract"' not in partial
    assert 'data-xmux-dialog' in partial
    assert 'data-xmux-dialog-panel="auto"' in partial
    assert 'data-xmux-dialog-panel="reduced"' in partial
    assert 'data-xmux-dialog-panel="expert"' in partial
    assert '<code>maxConnections</code><strong>2-4</strong>' in partial
    assert '<code>maxConcurrency</code><strong>0</strong>' in partial
    assert 'Параметры сохранятся только по кнопке «Сохранить XMUX»' in partial
    assert "showModeDetails" in js
    assert "dialog.showModal" in js
    assert "if (input.checked) showModeDetails(input.value)" in js
    assert "checks required disk space before stopping panel/HostD" in publication
    assert "bounded history (two by default)" in publication
    assert "parameter dialog with the exact preset values before save" in publication

