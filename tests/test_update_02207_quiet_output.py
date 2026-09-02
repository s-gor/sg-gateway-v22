from pathlib import Path


ROOT = Path(__file__).parents[1]
WRAPPER = ROOT / "deploy" / "update-from-github-02207.sh"
CORE = ROOT / "deploy" / "update-from-github-core.sh"
NAIVE_INSTALLER = ROOT / "deploy" / "install-naiveproxy.sh"


def test_02207_wrapper_exact_commit_fetches_hide_curl_progress_but_keep_errors():
    source = WRAPPER.read_text(encoding="utf-8")

    assert source.count("curl -4fsSL") >= 3
    assert "curl -4fL \\" not in source


def test_base_archive_download_hides_curl_progress_but_keeps_errors():
    source = CORE.read_text(encoding="utf-8")

    assert "curl -fsSL --retry 6 --retry-all-errors" in source
    assert "curl -fL --retry 6 --retry-all-errors" not in source


def test_naive_runtime_download_and_successful_caddy_validation_are_quiet():
    source = NAIVE_INSTALLER.read_text(encoding="utf-8")

    assert "curl -fsSL --retry 3 --connect-timeout 15" in source
    assert "curl -fL --retry 3 --connect-timeout 15" not in source
    assert 'caddy_validate_log="$TX_DIR/caddy-validate.log"' in source
    assert 'if ! "$candidate" validate --config "$CONFIG_DIR/Caddyfile" --adapter caddyfile >"$caddy_validate_log" 2>&1; then' in source
    assert 'cat "$caddy_validate_log" >&2' in source
    assert 'die "Caddy configuration validation failed"' in source
