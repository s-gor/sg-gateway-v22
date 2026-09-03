import shlex
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
WRAPPER = ROOT / "deploy" / "update-from-github-02207.sh"
CORE = ROOT / "deploy" / "update-from-github-core.sh"
NAIVE_INSTALLER = ROOT / "deploy" / "install-naiveproxy.sh"


def test_02207_wrapper_exports_private_curl_policy_before_any_update_fetch():
    source = WRAPPER.read_text(encoding="utf-8")
    capture_start = source.index("capture_naive_prestate()")
    first_fetch = source.index("curl -4fL", capture_start)
    quiet_dir = source.index('install -d -m 0700 "$TX_DIR/curl-home"', capture_start)
    quiet_config = source.index('cat > "$TX_DIR/curl-home/.curlrc"', capture_start)
    quiet_export = source.index('export CURL_HOME="$TX_DIR/curl-home"', capture_start)

    assert capture_start < quiet_dir < quiet_config < quiet_export < first_fetch
    assert "silent\nshow-error\nEOF" in source


def test_nested_panel_core_keeps_inherited_curl_config_enabled():
    source = CORE.read_text(encoding="utf-8")

    assert "curl -fL --retry 6 --retry-all-errors" in source
    assert "curl -q" not in source
    assert "curl --disable" not in source


def test_naive_runtime_download_and_successful_caddy_validation_are_quiet():
    source = NAIVE_INSTALLER.read_text(encoding="utf-8")

    assert "curl -fsSL --retry 3 --connect-timeout 15" in source
    assert "curl -fL --retry 3 --connect-timeout 15" not in source
    assert 'caddy_validate_log="$TX_DIR/caddy-validate.log"' in source
    assert 'if ! "$candidate" validate --config "$CONFIG_DIR/Caddyfile" --adapter caddyfile >"$caddy_validate_log" 2>&1; then' in source
    assert 'cat "$caddy_validate_log" >&2' in source
    assert 'die "Caddy configuration validation failed"' in source


def test_successful_stage3a_machine_json_is_hidden_from_update_console(tmp_path):
    prefix = tmp_path / "opt" / "sg-gateway"
    fake_python = prefix / ".venv" / "bin" / "python"
    fake_python.parent.mkdir(parents=True)
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' '{\"created_credentials\":0,\"peer_configs\":1}'\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    migration_source = tmp_path / "source"
    (migration_source / "vendor" / "cores").mkdir(parents=True)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    database = data_dir / "sg-gateway.sqlite"

    shell = f"""
set -Eeuo pipefail
export SG_GATEWAY_UPDATE_CORE_LIBRARY_ONLY=1
source {shlex.quote(str(CORE))}
PREFIX={shlex.quote(str(prefix))}
MIGRATION_SOURCE_DIR={shlex.quote(str(migration_source))}
SYSTEM_ROOT={shlex.quote(str(tmp_path))}
DATA_DIR={shlex.quote(str(data_dir))}
DATABASE={shlex.quote(str(database))}
validate_runtime_sources() {{ :; }}
run_stage3a_migration
"""
    completed = subprocess.run(
        ["bash", "-c", shell],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "created_credentials" not in completed.stdout
    assert "peer_configs" not in completed.stdout
