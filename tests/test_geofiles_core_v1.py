from __future__ import annotations

from pathlib import Path

import pytest

from app.routing.geofiles import GeoFilesError, _safe_url, extract_categories, validate_pair


def _varint(value: int) -> bytes:
    result = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            result.append(byte | 0x80)
        else:
            result.append(byte)
            return bytes(result)


def _field(number: int, payload: bytes) -> bytes:
    return _varint((number << 3) | 2) + _varint(len(payload)) + payload


def _geodat(categories: list[str], padding: int = 1400) -> bytes:
    messages = []
    for category in categories:
        inner = _field(1, category.upper().encode("utf-8"))
        inner += _field(2, b"x" * padding)
        messages.append(_field(1, inner))
    return b"".join(messages)


def test_extracts_real_categories_without_ads_requirement(tmp_path: Path):
    path = tmp_path / "geosite.dat"
    path.write_bytes(_geodat(["tld-ru", "category-ru", "private"]))
    assert extract_categories(path) == ("category-ru", "private", "tld-ru")


def test_valid_pair_does_not_require_category_ads_all(tmp_path: Path):
    geoip = tmp_path / "geoip.dat"
    geosite = tmp_path / "geosite.dat"
    geoip.write_bytes(_geodat(["ru", "private"]))
    geosite.write_bytes(_geodat(["tld-ru", "category-ru"]))
    report = validate_pair(geoip, geosite, "test", "Test pair")
    assert report.valid is True
    assert report.geoip.categories == ("private", "ru")
    assert report.geosite.categories == ("category-ru", "tld-ru")


def test_rejects_file_without_categories(tmp_path: Path):
    geoip = tmp_path / "geoip.dat"
    geosite = tmp_path / "geosite.dat"
    geoip.write_bytes(b"x" * 2048)
    geosite.write_bytes(_geodat(["category-ru"]))
    report = validate_pair(geoip, geosite)
    assert report.valid is False
    assert report.geoip.valid is False


def test_custom_sources_require_https():
    assert _safe_url("https://example.com/geoip.dat").startswith("https://")
    with pytest.raises(GeoFilesError):
        _safe_url("http://example.com/geoip.dat")
    with pytest.raises(GeoFilesError):
        _safe_url("file:///tmp/geoip.dat")


def test_geofiles_ui_contract_exists():
    root = Path(__file__).resolve().parents[1]
    partial = (root / "app/web/templates/_geofiles_panel.html").read_text(encoding="utf-8")
    for marker in (
        "geofiles_check",
        "geofiles_apply",
        "geofiles_rollback",
        "category-ads-all",
        "candidate",
        "geoip.dat",
        "geosite.dat",
    ):
        assert marker in partial
