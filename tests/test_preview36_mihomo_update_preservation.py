from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_update_preserves_applied_mihomo_runtime_configuration():
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "if (( UPDATE_MODE == 0 )); then" in installer
    assert "Mihomo runtime: existing configuration preserved" in installer
    assert "chown root:root /etc/mihomo/config.yaml" in installer
    assert "chmod 0600 /etc/mihomo/config.yaml" in installer
    assert "Mihomo runtime: clean install idle configuration ready" in installer
    assert "cat > /etc/mihomo/config.yaml <<'MIOIDLE'" in installer
    assert 'listeners: []' in installer

    preserved = installer.index("Mihomo runtime: existing configuration preserved")
    update_branch = installer.rfind("elif [[ -e /etc/mihomo/config.yaml ]]", 0, preserved)
    assert update_branch != -1


def test_stale_atomic_mihomo_file_is_removed_but_working_file_is_not_removed_on_update():
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "rm -f /etc/mihomo/config.yaml.new" in installer
    assert "if (( UPDATE_MODE == 0 )); then\n    rm -rf /etc/mihomo/tls" in installer
    assert "cat > /etc/mihomo/config.yaml <<'MIOIDLE'" in installer
    assert "if (( UPDATE_MODE == 0 )); then\n    rm -f /etc/mihomo/config.yaml" not in installer
