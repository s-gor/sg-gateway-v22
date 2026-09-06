from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import main


ROOT = Path(__file__).resolve().parents[1]


def _xray_overview(*, xhttp_tls_ready: bool) -> dict:
    return {
        "profiles": [
            SimpleNamespace(
                id="reality_tcp",
                title="VLESS Reality TCP",
                ready=True,
            ),
            SimpleNamespace(
                id="xhttp_reality",
                title="VLESS XHTTP Reality",
                ready=True,
            ),
            SimpleNamespace(
                id="xhttp_tls",
                title="VLESS XHTTP TLS",
                ready=xhttp_tls_ready,
            ),
            SimpleNamespace(
                id="hysteria2",
                title="Hysteria 2",
                ready=False,
            ),
        ]
    }


def test_prepare_client_protocols_rejects_disabled_xray_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "xray_profiles_overview",
        lambda: _xray_overview(xhttp_tls_ready=False),
    )

    with pytest.raises(ValueError, match="VLESS XHTTP TLS.*выключен|не готов"):
        main._prepare_client_protocols(
            ["amneziawg", "xray_xhttp_tls", "mihomo"]
        )


def test_prepare_client_protocols_accepts_ready_xray_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "xray_profiles_overview",
        lambda: _xray_overview(xhttp_tls_ready=True),
    )

    assert main._prepare_client_protocols(
        ["amneziawg", "xray_xhttp_tls", "mihomo"]
    ) == ["amneziawg", "xray_xhttp_tls", "mihomo", "sgclient"]


def test_direct_post_with_disabled_xray_profile_does_not_create_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "load_config",
        lambda: SimpleNamespace(secret_key="test-secret"),
    )
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "register_awg31", lambda app: None)
    monkeypatch.setattr(main, "should_skip_auth", lambda endpoint: True)
    monkeypatch.setattr(
        main,
        "xray_profiles_overview",
        lambda: _xray_overview(xhttp_tls_ready=False),
    )

    created: list[dict] = []
    applied: list[bool] = []

    def capture_create_client(**kwargs):
        created.append(kwargs)
        return 99

    monkeypatch.setattr(main, "create_client", capture_create_client)
    monkeypatch.setattr(
        main,
        "apply_clients_runtime",
        lambda: applied.append(True) or {"message": "unexpected"},
    )

    app = main.create_app()
    response = app.test_client().post(
        "/clients",
        data={
            "name": "Test9",
            "protocols": ["amneziawg", "xray_xhttp_tls", "mihomo"],
        },
    )

    assert response.status_code == 302
    assert created == []
    assert applied == []


def test_edit_dialog_does_not_resubmit_selected_disabled_xray_profile() -> None:
    source = (
        ROOT / "app/web/templates/_client_edit_dialogs.html"
    ).read_text(encoding="utf-8")
    macro = source.split("{% macro edit_xray_protocol_card", 1)[1]
    macro = macro.split("{%- endmacro %}", 1)[0]

    assert "{% if selected and profile.ready %}checked{% endif %}" in macro
    assert "{% if not profile.ready %}disabled{% endif %}" in macro
    assert "Выключен на сервере — при сохранении будет удалён" in macro
