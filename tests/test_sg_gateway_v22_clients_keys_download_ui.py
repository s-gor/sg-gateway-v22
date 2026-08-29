from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = ROOT / "app" / "web" / "templates" / "base.html"
DOWNLOAD_JS = ROOT / "app" / "web" / "static" / "sg-clients-keys-download-v1.js"


def test_clients_keys_download_fix_is_loaded_on_maintenance() -> None:
    base = BASE_TEMPLATE.read_text(encoding="utf-8")
    assert "sg-clients-keys-download-v1.js" in base
    assert "active_page|default('') == 'maintenance'" in base


def test_clients_keys_download_requires_real_attachment_and_uses_blob() -> None:
    source = DOWNLOAD_JS.read_text(encoding="utf-8")
    assert '.sg-data-backup-card .sg-full-download' in source
    assert "await fetch(anchor.href" in source
    assert 'credentials: "same-origin"' in source
    assert 'response.headers.get("Content-Disposition")' in source
    assert "/attachment/i.test(disposition)" in source
    assert "URL.createObjectURL(blob)" in source
    assert "download.click()" in source


def test_global_version_badges_show_short_2206_label() -> None:
    base = BASE_TEMPLATE.read_text(encoding="utf-8")
    assert '<div class="sg-server-version">{{ app_version[-5:] }}</div>' in base
    assert '<div class="sg-version-label">{{ app_version[-5:] }}</div>' in base
