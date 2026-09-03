from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    body = target.read_text(encoding="utf-8")
    if new in body:
        return
    if old not in body:
        raise SystemExit(f"02208 patch anchor missing: {path}: {old[:80]!r}")
    target.write_text(body.replace(old, new, 1), encoding="utf-8")


replace(
    "app/xray/profiles.py",
    'XRAY_MINIMUM_VERSION = "26.6.27"',
    'XRAY_MINIMUM_VERSION = "26.7.28"',
)
replace(
    "app/xray/profiles.py",
    '''# Client-only XHTTP XMUX preset confirmed for Russian networks.\n# maxConcurrency stays 0 because Xray forbids a positive maxConcurrency together\n# with a positive maxConnections.\nXHTTP_XMUX_RF = {\n    "maxConcurrency": 0,\n    "maxConnections": 6,\n    "cMaxReuseTimes": 0,\n    "hMaxRequestTimes": "600-900",\n    "hMaxReusableSecs": "1800-3000",\n    "hKeepAlivePeriod": 0,\n}''',
    '''# Client-only XHTTP XMUX fast-rotation preset for Russian networks.\n# maxConnections stays 0 because Xray forbids a positive maxConnections together\n# with a positive maxConcurrency.\nXHTTP_XMUX_RF = {\n    "maxConcurrency": 5,\n    "maxConnections": 0,\n    "cMaxReuseTimes": 0,\n    "hMaxRequestTimes": "300-600",\n    "hMaxReusableSecs": "900-1800",\n    "hKeepAlivePeriod": 0,\n}''',
)
replace("vendor/cores/VERSIONS.env", "XRAY_VERSION=v26.6.27", "XRAY_VERSION=v26.7.28")
replace("install.sh", 'XRAY_REQUIRED_VERSION="v26.6.27"', 'XRAY_REQUIRED_VERSION="v26.7.28"')
replace("install.sh", 'XRAY_MINIMUM_VERSION="v26.6.27"', 'XRAY_MINIMUM_VERSION="v26.7.28"')

replace(
    "tests/test_sg_gateway_02204_xmux_sgpanel_contract.py",
    '''    assert extra["xmux"] == {\n        "maxConnections": "2-4",\n        "cMaxReuseTimes": "300-600",\n        "hMaxRequestTimes": "1000-2000",\n        "hMaxReusableSecs": "1200-2400",\n        "hKeepAlivePeriod": 600,\n    }''',
    '''    assert extra["xmux"] == {\n        "maxConcurrency": 0,\n        "maxConnections": 3,\n        "cMaxReuseTimes": 0,\n        "hMaxRequestTimes": "600-900",\n        "hMaxReusableSecs": "1800-3000",\n        "hKeepAlivePeriod": 0,\n    }''',
)
replace(
    "tests/test_sg_gateway_02204_xmux_sgpanel_contract.py",
    '''    assert extra["xmux"] == {\n        "maxConcurrency": 0,\n        "maxConnections": "6",\n        "cMaxReuseTimes": 0,\n        "hMaxRequestTimes": "600-900",\n        "hMaxReusableSecs": "1800-3000",\n        "hKeepAlivePeriod": 0,\n    }''',
    '''    assert extra["xmux"] == {\n        "maxConcurrency": 5,\n        "maxConnections": 0,\n        "cMaxReuseTimes": 0,\n        "hMaxRequestTimes": "300-600",\n        "hMaxReusableSecs": "900-1800",\n        "hKeepAlivePeriod": 0,\n    }''',
)
replace(
    "tests/test_sg_gateway_02204_xmux_sgpanel_contract.py",
    '''    assert config["xhttp_extra_client_json"] == {"headers": {"X-Test": "kept"}}''',
    '''    assert config["xhttp_extra_client_json"] == {\n        "headers": {"X-Test": "kept"},\n        "xmux": xmux.XMUX_STANDARD_PRESET,\n    }\n    assert config["xhttp_xmux_preset_revision"] == "xray-26.7.28"''',
)
replace(
    "tests/test_sg_gateway_02204_xmux_sgpanel_contract.py",
    '    assert "Для РФ — уменьшенный" in partial',
    '    assert "Для РФ — быстрая ротация" in partial',
)
replace(
    "tests/test_sg_gateway_02204_xmux_sgpanel_contract.py",
    '    assert "maxConnections 2-4" in partial',
    '    assert "maxConnections 3" in partial',
)
replace(
    "tests/test_sg_gateway_02204_xmux_sgpanel_contract.py",
    '''    assert '<code>maxConnections</code><strong>2-4</strong>' in partial''',
    '''    assert '<code>maxConnections</code><strong>3</strong>' in partial''',
)
replace(
    "tests/test_sg_gateway_021_xmux_rf.py",
    '''    assert XHTTP_XMUX_RF == {\n        "maxConcurrency": 0,\n        "maxConnections": 6,\n        "cMaxReuseTimes": 0,\n        "hMaxRequestTimes": "600-900",\n        "hMaxReusableSecs": "1800-3000",\n        "hKeepAlivePeriod": 0,\n    }''',
    '''    assert XHTTP_XMUX_RF == {\n        "maxConcurrency": 5,\n        "maxConnections": 0,\n        "cMaxReuseTimes": 0,\n        "hMaxRequestTimes": "300-600",\n        "hMaxReusableSecs": "900-1800",\n        "hKeepAlivePeriod": 0,\n    }''',
)
