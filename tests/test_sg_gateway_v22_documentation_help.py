from pathlib import Path

from app.help.content import list_topics


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs/SG-GATEWAY-02206-GUIDE.md"
CHANGES = ROOT / "docs/CHANGES-02204-TO-02206.md"
README = ROOT / "README.md"
PUBLICATION = ROOT / "PUBLICATION-02206.md"
HELP_TEMPLATE = ROOT / "app/web/templates/help.html"


def test_full_guide_and_version_changes_are_published() -> None:
    assert GUIDE.is_file()
    assert CHANGES.is_file()

    guide = GUIDE.read_text(encoding="utf-8")
    changes = CHANGES.read_text(encoding="utf-8")

    for heading in (
        "Установка, обновление и удаление",
        "Первый запуск",
        "AmneziaWG 2.0, 3.0 и 3.1",
        "Клиенты, устройства и подписки",
        "Маршрутизация и WARP",
        "Резервные копии и восстановление",
        "Диагностика и типовые неисправности",
    ):
        assert heading in guide

    assert "Что нового в 022.06" in changes
    assert "Что уже было в 022.04" in changes
    assert "AWG 3.1" in changes
    assert "Router JSON Subscription" in changes


def test_guide_reserves_eight_numbered_screenshot_slots() -> None:
    guide = GUIDE.read_text(encoding="utf-8")

    for number in range(1, 9):
        assert f"<!-- SCREENSHOT-{number:02d} -->" in guide
        assert f"Скриншот {number}" in guide


def test_readme_and_release_page_link_to_new_documentation() -> None:
    readme = README.read_text(encoding="utf-8")
    publication = PUBLICATION.read_text(encoding="utf-8")

    for source in (readme, publication):
        assert "docs/SG-GATEWAY-02206-GUIDE.md" in source
        assert "docs/CHANGES-02204-TO-02206.md" in source


def test_embedded_help_covers_complete_operator_workflow() -> None:
    topics = {topic.slug: topic for topic in list_topics()}
    required = {
        "quickstart",
        "system",
        "clients",
        "subscriptions",
        "connections",
        "awg",
        "xray",
        "mihomo",
        "routing",
        "security",
        "backups",
        "updates",
        "troubleshooting",
    }

    assert required <= topics.keys()
    for slug in required:
        assert len(topics[slug].body) >= 4
        assert topics[slug].summary.strip()


def test_help_page_describes_the_expanded_practical_guide() -> None:
    source = HELP_TEMPLATE.read_text(encoding="utf-8")

    assert "Практическая справка SG-Gateway" in source
    assert "установка, клиенты, протоколы, подписки, резервные копии" in source
    assert "System, Clients, Connections, Routing, Maintenance, Security" not in source
