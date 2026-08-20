from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app" / "web" / "static" / "sg-maintenance-recovery-v1.js"
OPERATION_TEMPLATE = ROOT / "app" / "web" / "templates" / "operation_job.html"
HOSTD_JOBS = ROOT / "hostd" / "sg_hostd" / "operation_jobs.py"


def test_full_restore_restart_reconnects_same_terminal_over_https():
    script = SCRIPT.read_text(encoding="utf-8")
    template = OPERATION_TEMPLATE.read_text(encoding="utf-8")
    jobs = HOSTD_JOBS.read_text(encoding="utf-8")

    assert 'data-restart-expected="{{ \'1\' if job.restart_expected else \'0\' }}"' in template
    assert '"full_backup_restore"' in jobs
    assert '{"restart_expected": True}' in jobs

    assert 'opjob-page[data-restart-expected="1"]' in script
    assert 'window.location.protocol !== "http:"' not in script
    assert r"\[Restore 6\/\d+\]" in script
    assert "Адрес панели после переключения" in script
    assert "restoreAddress" in script
    assert "secureJobUrl.origin !== currentUrl.origin" in script
    assert 'currentUrl.protocol !== "https:"' in script
    assert "if (!crossOrigin && !protocolUpgrade)" in script
    assert 'secureStatusUrl.protocol = "https:"' in script
    assert 'mode: "no-cors"' in script
    assert "window.location.replace(secureJobUrl.toString())" in script
    assert "Переподключаю этот же терминал автоматически" in script
