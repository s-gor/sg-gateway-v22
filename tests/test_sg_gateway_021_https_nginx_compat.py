from pathlib import Path


def test_https_supports_ubuntu_nginx_118_without_proxy_cookie_flags():
    source = Path("deploy/configure-panel-access.sh").read_text(encoding="utf-8")
    assert "nginx_cookie_security_directive" in source
    assert 'dpkg --compare-versions "$version" ge \'1.19.3\'' in source
    assert "proxy_cookie_flags ~ secure httponly samesite=lax;" in source
    assert 'proxy_cookie_path / "/; Secure; HttpOnly; SameSite=Lax";' in source
    assert "$cookie_security_directive" in source


def test_https_cookie_compat_keeps_tls_rollback_and_cert_reuse():
    source = Path("deploy/configure-panel-access.sh").read_text(encoding="utf-8")
    assert 'if [[ -s "$cert_file" && -s "$key_file" ]]' in source
    assert 'log "Использую существующий сертификат"' in source
    assert 'restore_backup "$SG_HTTPS_BACKUP_DIR"' in source
