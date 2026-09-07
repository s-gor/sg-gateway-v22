from __future__ import annotations

import importlib.util
import inspect
import os
import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
RUNTIME_PATH = ROOT / "hostd" / "sg_hostd" / "naiveproxy_runtime.py"
INSTALL_PATH = ROOT / "install.sh"


def _load_runtime():
    spec = importlib.util.spec_from_file_location("naiveproxy_runtime_under_test", RUNTIME_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _function_body(source: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\(\) \{{\n(?P<body>.*?)^\}}$", source, re.M | re.S)
    assert match is not None, f"missing shell function: {name}"
    return match.group("body")


def test_tls_permission_helper_repairs_existing_directory_and_files(tmp_path, monkeypatch):
    runtime = _load_runtime()
    config = tmp_path / "etc" / "sg-gateway" / "naiveproxy"
    tls = config / "tls"
    cert = tls / "fullchain.pem"
    key = tls / "privkey.pem"
    tls.mkdir(parents=True)
    cert.write_text("certificate", encoding="utf-8")
    key.write_text("private-key", encoding="utf-8")
    os.chmod(config, 0o700)
    os.chmod(tls, 0o700)
    os.chmod(cert, 0o600)
    os.chmod(key, 0o600)

    monkeypatch.setattr(runtime, "CONFIG_DIR", config)
    monkeypatch.setattr(runtime, "TLS_DIR", tls)
    monkeypatch.setattr(runtime, "TLS_CERTIFICATE", cert)
    monkeypatch.setattr(runtime, "TLS_PRIVATE_KEY", key)

    chowns = []
    monkeypatch.setattr(
        runtime.shutil,
        "chown",
        lambda path, user, group: chowns.append((Path(path), user, group)),
    )

    runtime._ensure_tls_permissions()

    assert config.stat().st_mode & 0o777 == 0o750
    assert tls.stat().st_mode & 0o777 == 0o750
    assert cert.stat().st_mode & 0o777 == 0o644
    assert key.stat().st_mode & 0o777 == 0o640
    assert (config, "root", "sg-naiveproxy") in chowns
    assert (tls, "root", "sg-naiveproxy") in chowns
    assert (cert, "root", "sg-naiveproxy") in chowns
    assert (key, "root", "sg-naiveproxy") in chowns


def test_sync_and_rollback_normalize_tls_permissions_before_service_start():
    runtime = _load_runtime()
    sync_source = inspect.getsource(runtime.sync)
    rollback_source = inspect.getsource(runtime._restore_snapshot)
    public_rollback_source = inspect.getsource(runtime.rollback)

    assert sync_source.count("_ensure_tls_permissions()") >= 2
    assert sync_source.rfind("_ensure_tls_permissions()") < sync_source.index(
        '["systemctl", "enable", "--now", SERVICE]'
    )
    assert "_ensure_tls_permissions()" in rollback_source
    assert rollback_source.index("_ensure_tls_permissions()") < rollback_source.index(
        '["systemctl", "restart", SERVICE]'
    )
    assert "_ensure_tls_permissions()" in public_rollback_source
    assert public_rollback_source.index("_ensure_tls_permissions()") < public_rollback_source.index(
        '["systemctl", "restart", SERVICE]'
    )


def test_installer_repairs_tls_directory_and_validates_active_tls_files():
    install = INSTALL_PATH.read_text(encoding="utf-8")
    stage13 = _function_body(install, "stage_configuration_and_database_02208")
    verify = _function_body(install, "verify_naiveproxy_install_contract")

    assert 'install -d -o root -g sg-naiveproxy -m 0750 "$NAIVEPROXY_CONFIG/tls"' in stage13
    assert 'chown root:sg-naiveproxy "$NAIVEPROXY_CONFIG/tls/fullchain.pem"' in stage13
    assert 'chmod 0644 "$NAIVEPROXY_CONFIG/tls/fullchain.pem"' in stage13
    assert 'chown root:sg-naiveproxy "$NAIVEPROXY_CONFIG/tls/privkey.pem"' in stage13
    assert 'chmod 0640 "$NAIVEPROXY_CONFIG/tls/privkey.pem"' in stage13

    assert 'root:sg-naiveproxy:750' in verify
    assert 'root:sg-naiveproxy:644' in verify
    assert 'root:sg-naiveproxy:640' in verify
    assert '"$NAIVEPROXY_CONFIG/tls/fullchain.pem"' in verify
    assert '"$NAIVEPROXY_CONFIG/tls/privkey.pem"' in verify


def test_installer_keeps_exact_24_stage_contract():
    install = INSTALL_PATH.read_text(encoding="utf-8")
    main = _function_body(install, "main")
    stages = [
        int(value)
        for value in re.findall(r"^  run_(?:interactive_)?stage ([0-9]+) ", main, re.M)
    ]
    assert stages == list(range(1, 25))
