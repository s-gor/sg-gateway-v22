from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "deploy" / "update-from-github.sh"

def _block(body: str, name: str, next_name: str) -> str:
    start = body.index(f"{name}() {{")
    end = body.index(f"\n{next_name}() {{", start)
    return body[start:end]

def test_update_source_is_bound_to_exact_commit_in_both_source_modes() -> None:
    body = UPDATER.read_text(encoding="utf-8")
    light = _block(body, "prepare_source_light", "prepare_source")
    archive = _block(body, "prepare_source_archive", "prepare_source_light")
    resolver = _block(body, "resolve_source_commit", "prepare_source_archive")
    assert 'SOURCE_COMMIT="$(git -C "$SOURCE_DIR" rev-parse HEAD' in light
    assert '[[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]]' in light
    assert 'archive_url="https://github.com/${REPOSITORY}/archive/${SOURCE_COMMIT}.tar.gz"' in archive
    assert '"$archive_url" -o "$archive"' in archive
    assert 'refs/heads/$BRANCH' in resolver
    assert 'commits/${BRANCH}.atom' in resolver
    assert 'SOURCE_COMMIT="$resolved"' in resolver

def test_successful_update_atomically_binds_panel_state_to_verified_live_tree() -> None:
    body = UPDATER.read_text(encoding="utf-8")
    bind = _block(body, "bind_panel_update_state", "main")
    assert 'PANEL_UPDATE_STATE="${SG_GATEWAY_PANEL_UPDATE_STATE:-$DATA_DIR/updates/panel-state.json}"' in body
    assert 'SG_GATEWAY_PANEL_UPDATE_STATE="$PANEL_UPDATE_STATE"' in bind
    assert 'from app.maintenance.panel_updates import source_fingerprint' in bind
    assert 'fingerprint = source_fingerprint(root)' in bind
    assert '"commit": commit' in bind
    assert '"version": version' in bind
    assert '"channel": channel' in bind
    assert '"source_fingerprint": fingerprint' in bind
    assert 'temporary.write_text' in bind
    assert 'os.chmod(temporary, 0o640)' in bind
    assert 'shutil.chown(temporary, user="root", group="sg-gateway")' in bind
    assert 'os.replace(temporary, state_path)' in bind
    assert 'runuser -u sg-gateway -- test -r "$PANEL_UPDATE_STATE"' in bind

def test_state_binding_occurs_after_final_verification_while_rollback_is_still_armed() -> None:
    body = UPDATER.read_text(encoding="utf-8")
    main = body[body.index("main() {"):]
    verify = main.index('run_stage 6 "Проверка HTTPS, Clients, Nginx и runtime" verify_final')
    bind = main.index("bind_panel_update_state", verify)
    finished = main.index("UPDATE_FINISHED=1", bind)
    disarm = main.index("trap - ERR INT TERM", finished)
    assert verify < bind < finished < disarm
    error = _block(body, "on_error", "run_stage")
    assert 'if (( UPDATE_FINISHED == 0 )); then' in error
    assert 'if (( BACKUP_READY == 1 )); then' in error
    assert 'rollback_update || true' in error

def test_fix19_channel_and_production_invariants_survive_state_binding() -> None:
    body = UPDATER.read_text(encoding="utf-8")
    assert 'REPOSITORY="s-gor/sg-gateway-v22"' in body
    assert '${SG_GATEWAY_GITHUB_BRANCH:-${SG_GATEWAY_UPDATE_BRANCH:-stable-02208}}' in body
    assert 'PANEL_PRODUCTION_WSGI="app.production:app"' in body
    assert 'printf \'%s\\n\' "$PANEL_PRODUCTION_WSGI"' in body
    assert "migrate_panel_wsgi_service()" in body
    assert '[[ -f "$SOURCE_DIR/app/production.py" ]]' in body
    assert 'REPOSITORY="s-gor/sg-gateway"' not in body
    assert "dev-02205" not in body
    assert "app.main:app" not in body
