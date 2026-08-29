from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_public_clean_install_refuses_existing_server() -> None:
    body = source("deploy/install-from-github.sh")
    assert "SG_GATEWAY_02112_INSTALL_UPDATE_SPLIT" in body
    assert "Clean Install is blocked on an existing server." in body
    assert "deploy/update-from-github.sh" in body


def test_clean_install_rejects_unsupported_ubuntu_before_mutation() -> None:
    wrapper = source("deploy/install-from-github.sh")
    installer = source("deploy/install-core.sh")
    for body in (wrapper, installer):
        assert "require_supported_ubuntu()" in body
        assert '${VERSION_ID:-}' in body
        assert '"24.04"' in body
        assert "Ubuntu 24.04" in body
    assert wrapper.index("require_supported_ubuntu\n") < wrapper.index("missing_packages=()")
    assert installer.index("require_supported_ubuntu\n") < installer.index("prepare_log\n")


def test_existing_install_update_command_keeps_selected_branch() -> None:
    body = source("deploy/install-from-github.sh")
    assert '"$REPOSITORY" "$BRANCH" "$BRANCH"' in body
    assert "sudo env SG_GATEWAY_GITHUB_BRANCH=%s bash" in body


def test_dedicated_update_never_runs_full_installer_or_package_install() -> None:
    body = source("deploy/update-from-github-core.sh")
    assert "Dedicated panel-only Update" in body
    assert 'bash "$SOURCE_DIR/install.sh"' not in body
    assert "SG_GATEWAY_SOURCE_DIR" not in body
    assert "apt-get" not in body
    assert "python3-certbot-nginx" not in body
    assert "apt-get install" not in body
    assert "install_mihomo" not in body
    assert "install_sing_box" not in body
    assert "install_amneziawg" not in body
    assert "warp.install" not in body


def test_dedicated_update_preserves_https_and_runtime() -> None:
    body = source("deploy/update-from-github-core.sh")
    assert "etc/letsencrypt" in body
    assert "letsencrypt-before.sha256" in body
    assert "nginx-before.sha256" in body
    assert "clients-before.sha256" in body
    assert "verify_runtime_states_unchanged" in body
    assert 'systemctl stop "$PANEL_SERVICE" "$HOSTD_SERVICE"' in body
    assert "systemctl restart xray.service" not in body
    assert "systemctl restart mihomo.service" not in body
    assert "systemctl restart sg-gateway-awg.service" not in body
    assert "systemctl restart sg-gateway-singbox.service" not in body


def test_update_has_six_user_visible_stages_and_rollback() -> None:
    body = source("deploy/update-from-github-core.sh")
    for number in range(1, 7):
        assert f"run_stage {number} " in body
    assert "rollback_update" in body
    assert "state.tar" in body
    assert "ROLLBACK OK" in body
