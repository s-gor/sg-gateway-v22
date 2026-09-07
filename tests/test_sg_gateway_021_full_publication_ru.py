from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_connections_uses_compact_xmux_and_full_width_mihomo():
    template = (ROOT / "app/web/templates/connections.html").read_text(
        encoding="utf-8"
    )
    xray_css = (ROOT / "app/web/static/sg-xray-profiles-v2.css").read_text(
        encoding="utf-8"
    )
    layout_css = (ROOT / "app/web/static/sg-preview28-final.css").read_text(
        encoding="utf-8"
    )

    assert "<strong>XMUX для РФ</strong>" in template
    assert "Показать параметры" in template
    assert "xps2-xmux-switch" not in template
    assert "compact client-only XMUX preset for Russian networks" in xray_css
    assert "Mihomo as a separate full-width Connections block" in layout_css
    assert "grid-template-columns: minmax(0, 1fr) !important" in layout_css


def test_client_detail_uses_02208_canonical_page_frame():
    frame = (ROOT / "app/web/static/sg-page-frame-routing-v1.css").read_text(encoding="utf-8")
    template = (ROOT / "app/web/templates/client_detail.html").read_text(encoding="utf-8")
    clients_css = (ROOT / "app/web/static/sg-ui-clients-v22-08.css").read_text(encoding="utf-8")

    assert ".dv16-page" not in frame
    assert 'data-sg-ui-page="client-detail"' in template
    assert 'class="dv16-heading sg-ui-page-head"' in template
    assert '[data-sg-ui-page="client-detail"]' in clients_css


def test_russian_publication_has_user_and_technical_roads():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    technical = (ROOT / "docs/TECHNICAL.md").read_text(encoding="utf-8")

    for marker in (
        "Лёгкая и быстрая веб-панель",
        "Семейный VPN без серверной акробатики",
        "Без квантовой механики",
        "VLESS Reality TCP + XTLS Vision",
        "VLESS XHTTP Reality + XTLS Vision + VLESS Encryption",
        "VLESS XHTTP TLS + XTLS Vision + VLESS Encryption",
        "А где подсчёт трафика?",
        "Установка",
        "Обновление",
        "Полное удаление",
        "Техническое устройство SG-Gateway",
    ):
        assert marker in readme

    assert "Пользовательская" in docs
    assert "Техническая" in docs
    assert "TECHNICAL.md" in docs
    assert "security.md" in docs

    for marker in (
        "Матрица Xray-профилей",
        "XTLS Vision",
        "VLESS Encryption",
        "XMUX для российских сетей",
        "flow=xtls-rprx-vision",
        "ML-KEM-768",
        "127.0.0.1:18080",
        "UDP `585`",
        "Осознанные ограничения",
    ):
        assert marker in technical
