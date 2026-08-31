from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "deploy" / "install-from-github.sh"


def _installer_source() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def test_clean_install_waits_for_cloud_init_before_disk_and_apt_work() -> None:
    source = _installer_source()

    assert "cloud-init status --wait" in source
    assert source.index("wait_for_cloud_init") < source.index(
        'require_free_space /tmp "temporary storage"'
    )


def test_clean_install_updates_ubuntu_before_downloading_gateway_source() -> None:
    source = _installer_source()

    assert "full-upgrade -y" in source
    assert "autoremove -y" in source
    assert source.index("prepare_clean_ubuntu") < source.index(
        "Downloading GitHub branch"
    )


def test_reboot_required_stops_before_gateway_install_without_rebooting() -> None:
    source = _installer_source()

    assert "/var/run/reboot-required" in source
    assert "repeat the same SG-Gateway install command" in source
    assert "systemctl reboot" not in source
    assert "shutdown -r" not in source


def test_clean_install_bootstrap_uses_quiet_green_progress_contract() -> None:
    source = _installer_source()

    assert 'BOOTSTRAP_LOG="/var/log/sg-gateway-bootstrap-02206.log"' in source
    assert "run_quiet()" in source
    assert "local frames=('|' '/' '-' \"\\\\\")" in source
    assert "\\033[1;32m" in source
    assert 'run_quiet "Подготовка 1/6 · Проверка Ubuntu" require_supported_ubuntu' in source
    assert 'run_quiet "Подготовка 2/6 · Ожидание cloud-init" wait_for_cloud_init' in source
    assert 'run_quiet "Подготовка 3/6 · Проверка диска" preflight_disk_space' in source
    assert 'run_quiet "Подготовка 4/6 · Обновление Ubuntu" prepare_clean_ubuntu' in source
    assert 'run_quiet "Подготовка 5/6 · Подготовка инструментов" prepare_bootstrap_tools' in source
    assert 'run_quiet "Подготовка 6/6 · Загрузка SG-Gateway" download_gateway_source' in source


def test_clean_install_bootstrap_hides_raw_output_but_keeps_failure_log() -> None:
    source = _installer_source()

    assert 'if [[ -t 1 ]]' in source
    assert '>"$raw_output" 2>&1 &' in source
    assert 'cat "$raw_output" >> "$BOOTSTRAP_LOG"' in source
    assert 'Полный технический журнал: %s\\n' in source
    assert '"$BOOTSTRAP_LOG"' in source
