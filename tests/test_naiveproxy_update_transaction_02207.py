from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_02207_update_wraps_naiveproxy_in_panel_safety_rollback():
    source = (ROOT / "deploy/update-from-github-02207.sh").read_text()
    assert "resolve_safety_backup" in source
    assert 'source "$core"' in source
    assert "BACKUP_DIR=\"$TX_BACKUP_DIR\"" in source
    assert "BACKUP_READY=1" in source
    assert "rollback_update" in source
    assert "restore_naive_identity_and_unit" in source


def test_02207_update_verifies_complete_backup_before_runtime_mutation():
    source = (ROOT / "deploy/update-from-github-02207.sh").read_text()
    assert 'required = ("state.tar", "existing-paths.txt", "service-state.tsv")' in source
    assert 'tar -tf "$TX_BACKUP_DIR/state.tar"' in source
    assert source.index("resolve_safety_backup") < source.index(
        'bash "$PREFIX/deploy/install-naiveproxy.sh"'
    )


def test_02207_update_restores_preexisting_service_identity_and_unit():
    source = (ROOT / "deploy/update-from-github-02207.sh").read_text()
    assert "NAIVE_UNIT_EXISTED" in source
    assert "NAIVE_USER_EXISTED" in source
    assert "NAIVE_GROUP_EXISTED" in source
    assert "NAIVE_WAS_ACTIVE" in source
    assert "NAIVE_WAS_ENABLED" in source
    assert "userdel sg-naiveproxy" in source
    assert "groupdel sg-naiveproxy" in source


def test_firewall_is_changed_only_after_runtime_transaction_succeeds():
    source = (ROOT / "deploy/update-from-github-02207.sh").read_text()
    assert source.index('bash "$PREFIX/deploy/install-naiveproxy.sh"') < source.index(
        "ufw allow 8447/tcp"
    )
    assert source.index("rollback_panel_update") < source.index("ufw allow 8447/tcp")
