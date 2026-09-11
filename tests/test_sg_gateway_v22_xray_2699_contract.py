from pathlib import Path
import re
import zipfile

from app.xray import profiles

EXPECTED = "26.9.9"

def test_xray_minimum_is_2699():
    assert profiles.XRAY_MINIMUM_VERSION == EXPECTED
    assert not profiles._version_supported("26.9.8")
    assert profiles._version_supported("26.9.9")
    assert profiles._version_supported("26.9.10")

def test_vendor_versions_pins_xray_2699():
    text = Path("vendor/cores/VERSIONS.env").read_text(encoding="utf-8")
    assert re.search(r"(?m)^XRAY_VERSION=v26\.9\.9$", text)

def test_bundled_archive_contains_xray_binary():
    archive = Path("vendor/cores/Xray-linux-64.zip")
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        names = {name.rsplit("/", 1)[-1] for name in zf.namelist()}
    assert "xray" in names
