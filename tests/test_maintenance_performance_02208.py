from types import SimpleNamespace


def _forbidden(name):
    def fail(*args, **kwargs):
        raise AssertionError(f"{name} must not run for Updates tab")
    return fail


def test_updates_context_skips_backup_and_health_work(monkeypatch):
    import app.main as main

    for name in (
        "list_backups",
        "backup_cleanup_preview",
        "list_data_backups",
        "get_verified_data_backup",
        "list_full_backups",
        "get_verified_full_backup",
        "list_operations",
        "collect_health_checks",
    ):
        monkeypatch.setattr(main, name, _forbidden(name))

    monkeypatch.setattr(main, "xray_update_overview", lambda refresh=False: {"refresh": refresh})
    monkeypatch.setattr(main, "panel_update_overview", lambda refresh=False: {"refresh": refresh})
    monkeypatch.setattr(main, "core_update_overview", lambda refresh=False: {"refresh": refresh})
    monkeypatch.setattr(main, "geofiles_overview", lambda: {"active": None})
    monkeypatch.setattr(main, "run_hostd_command", lambda *a, **k: SimpleNamespace(payload={"ok": True, "checks": []}, message=""))
    monkeypatch.setattr(main, "get_release_manifest", lambda: {"version": "test"})

    context = main._maintenance_page_context("updates", refresh_updates=True)

    assert context["xray_updates"]["refresh"] is True
    assert context["backups"] == []
    assert context["backup_cleanup"] is None
    assert context["health_checks"] == []
    assert context["operations"] == []


def test_backups_context_never_builds_unused_diagnostics(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "list_backups", lambda: [])
    monkeypatch.setattr(main, "backup_cleanup_preview", lambda rows: {"total_count": 0})
    monkeypatch.setattr(main, "list_data_backups", lambda: [])
    monkeypatch.setattr(main, "get_verified_data_backup", lambda: None)
    monkeypatch.setattr(main, "list_full_backups", lambda: [])
    monkeypatch.setattr(main, "get_verified_full_backup", lambda: None)
    monkeypatch.setattr(main, "list_operations", lambda: [])
    monkeypatch.setattr(main, "collect_health_checks", lambda: [])
    monkeypatch.setattr(main, "get_release_manifest", lambda: {"version": "test"})

    context = main._maintenance_page_context("backups")
    assert "diagnostics" not in context
    assert context["backup_cleanup"]["total_count"] == 0
