from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_02207_full_uninstall_runs_naive_cleanup_before_base_uninstall():
    source = (ROOT / "deploy/full-uninstall-02207.sh").read_text()
    assert 'NAIVE="$PREFIX/deploy/uninstall-naiveproxy.sh"' in source
    assert 'BASE="$PREFIX/deploy/full-uninstall-ubuntu.sh"' in source
    assert source.index('bash "$NAIVE"') < source.index('bash "$PATCHED"')
    assert '[[ -f "$NAIVE" ]]' in source
    assert '[[ -f "$BASE" ]]' in source


def test_02207_full_uninstall_patches_identity_and_reinstall_channel():
    source = (ROOT / "deploy/full-uninstall-02207.sh").read_text()
    assert "sg-gateway-full-uninstall-02207.log" in source
    assert "0.1.0-022.07-dev" in source
    assert "install-from-github-02207.sh" in source
    assert "SG_GATEWAY_GITHUB_BRANCH={branch}" in source
    assert "cannot patch unique reinstall command" in source
    assert "stable-02206" in source
    assert "source.replace(old_command, new_command)" in source


def test_02207_full_uninstall_verifies_no_naiveproxy_residue():
    source = (ROOT / "deploy/full-uninstall-02207.sh").read_text()
    for value in (
        "/opt/sg-gateway/naiveproxy",
        "/etc/sg-gateway/naiveproxy",
        "/var/lib/sg-gateway/naiveproxy",
        "/etc/systemd/system/sg-gateway-naiveproxy.service",
        "user sg-naiveproxy",
        "group sg-naiveproxy",
    ):
        assert value in source
    assert "full uninstall left NaiveProxy state" in source
    assert "NaiveProxy residue verification: OK" in source


def test_02207_full_uninstall_refuses_other_channels_and_never_edits_base_file():
    source = (ROOT / "deploy/full-uninstall-02207.sh").read_text()
    assert '"dev-02207"' in source
    assert "feature/02207-*" in source
    assert 'cp -- "$BASE" "$PATCHED"' in source
    assert "python3 - \"$PATCHED\"" in source
    assert "python3 - \"$BASE\"" not in source


def test_02208_full_uninstall_stops_removes_and_verifies_naiveproxy():
    source = (ROOT / "deploy/full-uninstall-ubuntu.sh").read_text()

    assert 'NAIVEPROXY_PORT="8447"' in source
    assert "sg-gateway-naiveproxy.service" in source
    assert "/etc/systemd/system/sg-gateway-naiveproxy.service" in source
    assert "pkill -TERM -u sg-naiveproxy" in source
    assert "userdel sg-naiveproxy" in source
    assert "groupdel sg-naiveproxy" in source
    assert "пользователь sg-naiveproxy" in source
    assert "группа sg-naiveproxy" in source
    assert '"${NAIVEPROXY_PORT}/tcp"' in source


def test_02208_full_uninstall_requires_naiveproxy_listener_to_be_gone():
    source = (ROOT / "deploy/full-uninstall-ubuntu.sh").read_text()

    assert 'ss -H -ltn "sport = :${NAIVEPROXY_PORT}"' in source
    assert "NaiveProxy listener" in source
    assert "Остаток после удаления" in source
