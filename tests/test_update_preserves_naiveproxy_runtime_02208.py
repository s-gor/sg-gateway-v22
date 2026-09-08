from pathlib import Path


UPDATER = Path("deploy/update-from-github.sh").read_text(encoding="utf-8")
CORE = Path("deploy/update-from-github-core.sh").read_text(encoding="utf-8")


def test_panel_update_marks_naiveproxy_runtime_as_protected() -> None:
    assert 'NAIVE_ROOT="$PREFIX/naiveproxy"' in UPDATER
    assert '"/opt/sg-gateway/naiveproxy"' in UPDATER
    assert 'NAIVE_ROOT="$PREFIX/naiveproxy"' in CORE
    assert '"$NAIVE_ROOT"' in CORE


def test_panel_update_preserves_naiveproxy_tree_during_source_replace() -> None:
    expected = '".venv"|"awg3"|"naiveproxy") continue ;;'
    assert expected in UPDATER
    assert expected in CORE
    assert '-path "$NAIVE_ROOT"' in UPDATER
    assert '-path "$NAIVE_ROOT"' in CORE


def test_panel_update_tracks_naiveproxy_service_state() -> None:
    assert 'NAIVE_SERVICE="sg-gateway-naiveproxy.service"' in UPDATER
    assert 'NAIVE_SERVICE="sg-gateway-naiveproxy.service"' in CORE
    assert '"$NAIVE_SERVICE"' in UPDATER
    assert '"$NAIVE_SERVICE"' in CORE


def test_light_update_includes_complete_hostd_tree() -> None:
    assert 'sparse-checkout set app hostd deploy' in UPDATER
    assert '/hostd/systemd/' in CORE
