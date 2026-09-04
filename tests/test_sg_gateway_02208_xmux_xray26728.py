from __future__ import annotations

from pathlib import Path

import pytest

from app.xray import profiles, xmux

ROOT = Path(__file__).resolve().parents[1]

STANDARD = {
    "maxConcurrency": 0,
    "maxConnections": 3,
    "cMaxReuseTimes": 0,
    "hMaxRequestTimes": "600-900",
    "hMaxReusableSecs": "1800-3000",
    "hKeepAlivePeriod": 0,
}

RF_FAST_ROTATION = {
    "maxConcurrency": 5,
    "maxConnections": 0,
    "cMaxReuseTimes": 0,
    "hMaxRequestTimes": "300-600",
    "hMaxReusableSecs": "900-1800",
    "hKeepAlivePeriod": 0,
}


def test_02208_fixed_presets_match_xray_26728_contract() -> None:
    assert xmux.XMUX_STANDARD_PRESET == STANDARD
    assert xmux.XMUX_REDUCED_PRESET == RF_FAST_ROTATION
    assert profiles.XHTTP_XMUX_RF == RF_FAST_ROTATION
    assert xmux.XMUX_MODE_OPTIONS[1]["title"] == "Для РФ — быстрая ротация"


def test_02208_fixed_presets_replace_only_xmux() -> None:
    source = {
        "headers": {"X-Test": "kept"},
        "padding": "100-200",
        "xmux": {"maxConnections": 99},
    }
    effective = xmux.effective_client_extra(
        {"xhttp_xmux_mode": "auto", "xhttp_extra_client_json": source}
    )
    assert effective["headers"] == {"X-Test": "kept"}
    assert effective["padding"] == "100-200"
    assert effective["xmux"] == STANDARD


def test_02208_manual_form_builds_xmux_and_rejects_conflict() -> None:
    values = xmux.manual_xmux_from_form(
        {
            "xhttp_xmux_maxConcurrency": "5",
            "xhttp_xmux_maxConnections": "0",
            "xhttp_xmux_cMaxReuseTimes": "0",
            "xhttp_xmux_hMaxRequestTimes": "300-600",
            "xhttp_xmux_hMaxReusableSecs": "900-1800",
            "xhttp_xmux_hKeepAlivePeriod": "0",
        }
    )
    assert values == RF_FAST_ROTATION

    with pytest.raises(xmux.XmuxError, match="maxConnections и maxConcurrency"):
        xmux.manual_xmux_from_form(
            {
                "xhttp_xmux_maxConcurrency": "5",
                "xhttp_xmux_maxConnections": "3",
                "xhttp_xmux_cMaxReuseTimes": "0",
                "xhttp_xmux_hMaxRequestTimes": "600-900",
                "xhttp_xmux_hMaxReusableSecs": "1800-3000",
                "xhttp_xmux_hKeepAlivePeriod": "0",
            }
        )


def test_02208_manual_form_rejects_bad_ranges() -> None:
    with pytest.raises(xmux.XmuxError, match="hMaxRequestTimes"):
        xmux.manual_xmux_from_form(
            {
                "xhttp_xmux_maxConcurrency": "0",
                "xhttp_xmux_maxConnections": "3",
                "xhttp_xmux_cMaxReuseTimes": "0",
                "xhttp_xmux_hMaxRequestTimes": "900-600",
                "xhttp_xmux_hMaxReusableSecs": "1800-3000",
                "xhttp_xmux_hKeepAlivePeriod": "0",
            }
        )


def test_02208_ui_has_two_locked_presets_manual_fields_and_raw_json() -> None:
    partial = (ROOT / "app/web/templates/_xray_xmux_settings.html").read_text(encoding="utf-8")
    assert "Стандартный" in partial
    assert "Для РФ — быстрая ротация" in partial
    assert "Ручной" in partial
    assert "Client Extra JSON" in partial
    assert "Для РФ — уменьшенный" not in partial
    assert "Xray-core 26.7.28 · закреплено" in partial
    for key in (
        "maxConcurrency",
        "maxConnections",
        "cMaxReuseTimes",
        "hMaxRequestTimes",
        "hMaxReusableSecs",
        "hKeepAlivePeriod",
    ):
        assert f'name="xhttp_xmux_{key}"' in partial


def test_02208_xray_runtime_is_pinned_to_official_26728_asset() -> None:
    versions = (ROOT / "vendor/cores/VERSIONS.env").read_text(encoding="utf-8")
    sums = (ROOT / "vendor/cores/SHA256SUMS").read_text(encoding="utf-8")
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert profiles.XRAY_MINIMUM_VERSION == "26.7.28"
    assert "XRAY_VERSION=v26.7.28" in versions
    assert 'XRAY_REQUIRED_VERSION="v26.7.28"' in installer
    assert 'XRAY_MINIMUM_VERSION="v26.7.28"' in installer
    assert (
        "8195d909f1109b8f3d99eefe401a3c451d7bf4af71f24d3815420f77e5dd2a40  "
        "Xray-linux-64.zip"
    ) in sums
