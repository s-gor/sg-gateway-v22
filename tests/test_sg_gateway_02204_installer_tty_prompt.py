from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"


def _installer() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def test_clean_installer_fails_clearly_without_an_interactive_tty() -> None:
    body = _installer()
    assert "require_interactive_tty()" in body
    assert "интерактивный терминал недоступен" in body
    assert "не удалось открыть интерактивный терминал /dev/tty" in body
    assert "переподключитесь по SSH" in body


def test_password_prompt_is_visible_and_cannot_wait_forever() -> None:
    body = _installer()
    assert "Требуется задать пароль администратора панели" in body
    assert "символы пароля не отображаются" in body
    assert "printf '[SG-Gateway] Пароль администратора" in body
    assert 'read -r -s -t "$timeout_seconds" first < /dev/tty' in body
    assert 'read -r -s -t "$timeout_seconds" second < /dev/tty' in body
    assert "пароль не получен из интерактивного терминала" in body
    assert "read -r -s -p" not in body


def test_all_installer_questions_write_prompts_to_the_tty() -> None:
    body = _installer()
    assert "printf '[SG-Gateway] %s [%s]: '" in body
    assert "printf '[SG-Gateway] %s %s: '" in body
    assert "read -r -p" not in body
