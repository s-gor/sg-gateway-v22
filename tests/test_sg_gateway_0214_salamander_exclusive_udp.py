from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from app.xray.salamander import MANAGED_VARIANT_MARKER, merge_finalmask  # noqa: E402
from sg_hostd import client_runtime  # noqa: E402


def test_known_good_gecko_live_shape_is_single_udp_layer():
    base = {
        "udp": [{"type": "padding", "settings": {"size": 7}}],
        MANAGED_VARIANT_MARKER: True,
    }
    live = merge_finalmask(base, "gecko", "S" * 32)
    assert live == {
        "udp": [
            {
                "type": "salamander",
                "settings": {"password": "S" * 32, "packetSize": "512-1200"},
            }
        ]
    }


def test_legacy_02204_gecko_is_discovered_once_then_saved_with_managed_marker(
    tmp_path, monkeypatch
):
    secret = "P" * 32
    live_path = tmp_path / "config.json"
    live_path.write_text(
        json.dumps(
            {
                "inbounds": [
                    {
                        "tag": "sg-hysteria2",
                        "streamSettings": {
                            "finalmask": {
                                "udp": [
                                    {"type": "padding", "settings": {"size": 5}},
                                    {
                                        "type": "salamander",
                                        "settings": {
                                            "password": secret,
                                            "packetSize": "512-1200",
                                        },
                                    },
                                ]
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(client_runtime, "XRAY_CONFIG", live_path)

    # Old 022.04 stored Gecko under the legacy DB mode "salamander". Its
    # discovery path can therefore strip that managed layer during migration.
    stored_base = client_runtime._live_hysteria_finalmask_base(
        {
            "hysteria2_obfs_mode": "salamander",
            "hysteria2_obfs_password": secret,
        }
    )
    assert stored_base == {"udp": [{"type": "padding", "settings": {"size": 5}}]}

    stored_base[MANAGED_VARIANT_MARKER] = True
    enabled = merge_finalmask(stored_base, "gecko", secret)
    assert enabled["udp"] == [
        {
            "type": "salamander",
            "settings": {"password": secret, "packetSize": "512-1200"},
        }
    ]
    assert MANAGED_VARIANT_MARKER not in enabled

    disabled = merge_finalmask(stored_base, "none", "")
    assert disabled == {"udp": [{"type": "padding", "settings": {"size": 5}}]}
