from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_updater_user_facing_text_is_calm_and_nontechnical() -> None:
    overview = (ROOT / "app/maintenance/panel_updates.py").read_text(encoding="utf-8")
    runtime = (ROOT / "hostd/sg_hostd/panel_update_runtime.py").read_text(encoding="utf-8")
    combined = overview + runtime

    assert "Автоматическое обновление сейчас недоступно." in overview
    assert "Текущая версия SG-Gateway продолжает работать нормально." in overview
    assert "Автоматическое обновление сейчас недоступно." in runtime

    for scary in (
        "локальные файлы отличаются",
        "локальный исходник изменён",
        "неопубликованные изменения",
        "GitHub baseline не привязан",
        "Сначала нужно опубликовать",
        "Опубликуйте или восстановите",
    ):
        assert scary not in combined
