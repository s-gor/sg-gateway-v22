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
    assert "Ошибка генерации" in cards["amneziawg"].error_message
    assert "Остальные профили" in cards["amneziawg"].error_message
    assert cards["anytls"].status == "applied"
    assert cards["anytls"].payload == "anytls://still-works"


def test_operation_job_logs_live_outside_transactional_data_tree() -> None:
    hostd = (ROOT / "hostd" / "sg_hostd" / "operation_jobs.py").read_text(encoding="utf-8")
    reader = (ROOT / "app" / "security" / "operation_jobs.py").read_text(encoding="utf-8")
    runner = (ROOT / "hostd" / "sg_hostd" / "operation_job_runner.py").read_text(encoding="utf-8")

    assert 'DEFAULT_JOB_DIR = "/var/log/sg-gateway/operation-jobs"' in hostd
    assert 'export SG_GATEWAY_OPERATION_JOB_DIR={shlex.quote(str(JOB_DIR))}' in hostd
    assert 'load_config().log_dir / "operation-jobs"' in reader
    assert 'return load_config().data_dir / "security" / "jobs"' in reader
    assert '"/var/log/sg-gateway/operation-jobs"' in runner
    assert 'export SG_GATEWAY_OPERATION_JOB_DIR=/var/lib/sg-gateway/security/jobs' not in hostd


def test_job_reader_keeps_legacy_fallback_for_old_terminals() -> None:
    reader = (ROOT / "app" / "security" / "operation_jobs.py").read_text(encoding="utf-8")
    assert "def _legacy_jobs_dir()" in reader
    assert "def _job_roots()" in reader
    assert "for candidate in _job_roots():" in reader
