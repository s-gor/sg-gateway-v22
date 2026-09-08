from pathlib import Path


UPDATER = Path("deploy/update-from-github.sh").read_text(encoding="utf-8")


def test_panel_update_marks_naiveproxy_runtime_as_protected() -> None:
    assert 'NAIVE_ROOT="$PREFIX/naiveproxy"' in UPDATER
    assert '"/opt/sg-gateway/naiveproxy"' in UPDATER


def test_panel_update_preserves_naiveproxy_tree_during_source_replace() -> None:
    assert '".venv"|"awg3"|"naiveproxy") continue ;;' in UPDATER
    assert '-path "$NAIVE_ROOT"' in UPDATER


def test_panel_update_tracks_naiveproxy_service_state() -> None:
    assert 'NAIVE_SERVICE="sg-gateway-naiveproxy.service"' in UPDATER
    assert '"$NAIVE_SERVICE"' in UPDATER


def test_light_update_includes_complete_hostd_tree() -> None:
    assert 'sparse-checkout set app hostd deploy' in UPDATER
