import json
from pathlib import Path
from types import SimpleNamespace

from app.maintenance import awg31_stage3a


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


def _stub_stage3a_success(monkeypatch):
    class FakeInstaller:
        def __init__(self, **_kwargs):
            pass

        def migrate(self, *, database):
            return SimpleNamespace(
                created_credentials=0,
                total_credentials=1,
                server_config=Path("/etc/amnezia/amneziawg/awg31/awg31.conf"),
                peer_configs=1,
            )

    monkeypatch.setattr(awg31_stage3a, "Stage3AInstaller", FakeInstaller)
    monkeypatch.setattr(
        awg31_stage3a,
        "ensure_seeded_admin_awg3",
        lambda **_kwargs: False,
    )


def _run_stage3a_cli(tmp_path):
    return awg31_stage3a.main(
        [
            "migrate",
            "--source-root",
            str(tmp_path),
            "--root",
            str(tmp_path),
            "--database",
            str(tmp_path / "sg-gateway.sqlite"),
        ]
    )


def test_stage3a_machine_json_is_hidden_inside_02207_update_context(
    monkeypatch, capsys, tmp_path
):
    _stub_stage3a_success(monkeypatch)
    monkeypatch.setenv("SG_GATEWAY_UPDATE_CORE_LIBRARY_ONLY", "1")

    assert _run_stage3a_cli(tmp_path) == 0
    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""


def test_stage3a_machine_json_contract_is_preserved_for_direct_cli(
    monkeypatch, capsys, tmp_path
):
    _stub_stage3a_success(monkeypatch)
    monkeypatch.delenv("SG_GATEWAY_UPDATE_CORE_LIBRARY_ONLY", raising=False)

    assert _run_stage3a_cli(tmp_path) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload == {
        "created_credentials": 0,
        "peer_configs": 1,
        "seeded_awg3_created": False,
        "server_config": "/etc/amnezia/amneziawg/awg31/awg31.conf",
        "total_credentials": 1,
    }
    assert captured.err == ""
