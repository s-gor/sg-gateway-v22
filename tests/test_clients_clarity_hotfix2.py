from pathlib import Path

from jinja2 import Environment


ROOT = Path(__file__).resolve().parents[1]


def test_clients_page_is_a_single_simple_list() -> None:
    template = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")

    for marker in (
        "cv15-clarity-page",
        "cv15-list-panel",
        "Устройства",
        "Ссылки, QR и управление находятся внутри карточки клиента.",
        "Всего клиентов",
    ):
        assert marker in template

    for removed in (
        "cv2-detail cv35-detail",
        "cv2-profile-pills",
        "cv2-dots-button",
        "data-select-only",
        'id="cv2-access"',
        "ВЫБРАННЫЙ КЛИЕНТ",
        "ID {{ client.id }}",
    ):
        assert removed not in template


def test_clients_table_has_one_open_action_and_no_protocol_column() -> None:
    template = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    table = template.split('<table class="cv2-table cv10-table cv15-table">', 1)[1].split("</table>", 1)[0]

    assert "<th>Клиент</th>" in table
    assert "<th>Сервер</th>" in table
    assert "<th>Статус</th>" in table
    assert "<th>Устройства</th>" in table
    assert "<th>Срок</th>" in table
    assert "<th>Доступы</th>" not in table
    assert table.count(">Открыть</a>") == 1
    assert "Xray</span>" not in table
    assert "Mieru</span>" not in table
    assert "SG Client</span>" not in table


def test_clients_clarity_css_is_loaded_last_and_scoped() -> None:
    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
    css = (ROOT / "app/web/static/sg-clients-clarity-hotfix2.css").read_text(encoding="utf-8")

    assert "sg-clients-clarity-hotfix2.css" in base
    assert base.rfind("sg-clients-clarity-hotfix2.css") > base.rfind("sg-clients-simple-hotfix1.css")
    for marker in (
        "Clients Clarity Hotfix 2",
        "body.clients-clarity-hotfix2 .cv15-list-panel",
        'html[data-theme="light"] body.clients-clarity-hotfix2',
        "--sg-panel: #fffefb",
        "background: linear-gradient(180deg, #3b866d 0%, #2b7059 100%)",
        'html[data-theme="dark"] body.clients-clarity-hotfix2',
    ):
        assert marker in css


def test_clients_template_parses() -> None:
    source = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    Environment().parse(source)
