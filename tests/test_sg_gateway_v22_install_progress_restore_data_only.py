from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "deploy" / "install-from-github-02207.sh"
INSTALLER = ROOT / "install.sh"
RESTORE = ROOT / "hostd" / "sg_hostd" / "clients_keys_portable_restore_patch.py"


EXPECTED_STAGES = {
    1: "Ожидание cloud-init",
    2: "Загрузка и проверка exact source",
    3: "Подготовка Ubuntu",
    4: "Резервная копия и подготовка исходника",
    5: "Nginx, Certbot и системные пакеты",
    6: "AmneziaWG 2.0",
    7: "AmneziaWG 3.0 userspace",
    8: "Xray",
    9: "Mihomo",
    10: "sing-box",
    11: "WARP helper",
    12: "Python-окружение и проверка исходника",
    13: "UI и база данных",
    14: "Локальная проверка страниц",
    15: "Создание systemd-служб",
    16: "Firewall и сетевые порты",
    17: "Запуск sg-hostd",
    18: "Проверка команд sg-hostd",
    19: "Подготовка AWG 3.1",
    20: "Применение Xray и клиентов",
    21: "Запуск панели",
    22: "Проверка Nginx и служб",
    23: "Контроль Clients",
    24: "Установка и проверка NaiveProxy",
}


def _sources() -> str:
    return WRAPPER.read_text(encoding="utf-8") + "\n" + INSTALLER.read_text(encoding="utf-8")


def test_clean_install_exposes_one_numbered_progress_contract_of_24_stages():
    source = _sources()
    assert "Этап 10/10" not in source
    for number, label in EXPECTED_STAGES.items():
        marker = f"Этап {number}/24 · {label}"
        assert source.count(marker) == 1, marker


def test_cloud_init_and_exact_source_are_visible_spinner_stages():
    wrapper = WRAPPER.read_text(encoding="utf-8")
    assert 'run_progress_stage 1 "Ожидание cloud-init"' in wrapper
    assert 'run_progress_stage 2 "Загрузка и проверка exact source"' in wrapper
    assert "frames=('|' '/' '-'" in wrapper
    assert "cloud-init status --wait" in wrapper


def test_installer_banner_identifies_02207_development_line():
    installer = INSTALLER.read_text(encoding="utf-8")
    assert "Запускаю полный мастер SG-Gateway 0.1.0-022.07-dev" in installer
    assert "Мастер установки SG-Gateway 0.1.0-022.07-dev запущен" in installer


def test_clients_keys_restore_is_data_only_and_never_applies_protocol_runtime():
    source = RESTORE.read_text(encoding="utf-8")
    forbidden = (
        "apply_all_clients",
        "_apply_portable_clients_runtime_required",
        "destination_protocol_policy",
        "_validate_runtime_after_restore()",
        "_restart_runtime(",
    )
    for token in forbidden:
        assert token not in source, token
    assert "Протоколы не запускаю" in source
    assert '"client_runtime_applied": False' in source
    assert '"portable_runtime_regenerated": False' in source
    assert '"runtime_activation_deferred": True' in source


def test_clients_keys_restore_keeps_https_and_panel_health_validation():
    source = RESTORE.read_text(encoding="utf-8")
    assert "_refresh_restored_https_from_local_files" in source
    assert "_restored_certificate_ready()" in source
    assert "_local_panel_health(full)" in source
    assert "_wait_for_panel_after_scheduled_restart" in source
