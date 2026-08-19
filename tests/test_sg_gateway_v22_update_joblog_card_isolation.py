from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.clients import access
from app.clients.repository import Client, ClientDeployment, Device


ROOT = Path(__file__).resolve().parents[1]


def _client() -> Client:
    return Client(
        id=7,
        name="Isolation test",
        enabled=True,
        expires_at=None,
        awg_status="applied",
        xray_status="missing",
        anytls_status="applied",
    )


def _device() -> Device:
    return Device(
        id=11,
        client_id=7,
        name="Phone",
        enabled=True,
        expires_at=None,
        is_primary=True,
        created_at="2026-08-19T00:00:00Z",
    )


def _deployment(engine: str) -> ClientDeployment:
    return ClientDeployment(
        engine=engine,
        status="applied",
        engine_object_id=None,
        config_json="{}",
        device_id=11,
    )


def test_one_broken_exporter_does_not_break_other_client_cards(monkeypatch) -> None:
    client = _client()
    device = _device()
    monkeypatch.setattr(
        access,
        "_deployment_map",
        lambda *_args, **_kwargs: {
            "amneziawg": _deployment("amneziawg"),
            "anytls": _deployment("anytls"),
        },
    )

    def broken_awg(*_args, **_kwargs):
        raise ValueError("synthetic exporter failure")

    monkeypatch.setattr(access, "build_awg_config", broken_awg)
    monkeypatch.setattr(
        access,
        "protocol_ready",
        lambda _client, kind, _device: kind == "anytls",
    )
    monkeypatch.setattr(
        access,
        "build_anytls_link",
        lambda *_args, **_kwargs: SimpleNamespace(body="anytls://still-works"),
    )

    cards = {card.kind: card for card in access.build_access_cards(client, device)}

    assert cards["amneziawg"].status == "error"
    assert cards["amneziawg"].payload == ""
    assert cards["amneziawg"].show_qr is False
    assert "Остальные профили" in cards["amneziawg"].error_message
    assert cards["anytls"].status == "applied"
    assert cards["anytls"].payload == "anytls://still-works"


def test_panel_update_safety_backup_keeps_live_operation_job_outside_rollback_archive() -> None:
    body = (ROOT / "deploy" / "update-from-github.sh").read_text(encoding="utf-8")
    assert 'OPERATION_JOB_DIR="$DATA_DIR/security/jobs"' in body
    assert '--exclude="${OPERATION_JOB_DIR#/}"' in body
    assert "preserve_operation_jobs_for_rollback()" in body
    assert "restore_operation_jobs_after_rollback()" in body

    rollback = body[body.index("rollback_update() {"):body.index("\non_error() {", body.index("rollback_update() {"))]
    assert rollback.index("preserve_operation_jobs_for_rollback") < rollback.index('rm -rf -- "$path"')
    assert rollback.index('tar -C / -xpf "$BACKUP_DIR/state.tar"') < rollback.index("restore_operation_jobs_after_rollback")


def test_client_detail_marks_only_failed_card_as_generation_error() -> None:
    template = (ROOT / "app" / "web" / "templates" / "client_detail.html").read_text(encoding="utf-8")
    assert "card.status == 'error'" in template
    assert "Ошибка генерации" in template
    assert "card.error_message" in template
