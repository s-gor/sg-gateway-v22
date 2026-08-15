import pytest

from app.clients.qr import ClientQrError, build_qr_svg


def test_normal_qr_still_builds_svg():
    svg = build_qr_svg("vless://example")
    assert "<svg" in svg


def test_oversized_qr_is_reported_as_client_conflict():
    with pytest.raises(ClientQrError, match="Ссылка слишком велика"):
        build_qr_svg("x" * 3000)
