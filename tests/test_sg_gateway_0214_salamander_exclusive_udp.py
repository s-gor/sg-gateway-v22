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

from app.xray.salamander import merge_finalmask  # noqa: E402
from sg_hostd import client_runtime  # noqa: E402


def test_known_good_salamander_live_shape_is_single_udp_layer():
    base = {
        "udp": [{"type": "padding", "settings": {"size": 7}}],
    }
    live = merge_finalmask(base, "salamander", "S" * 32)
    assert live == {
        "udp": [{"type": "salamander", "settings": {"password": "S" * 32}}]
    }


def test_discovered_previous_udp_mask_is_saved_but_suppressed_while_salamander_is_on(
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
                                    {"type": "salamander", "settings": {"password": secret}},
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

    stored_base = client_runtime._live_hysteria_finalmask_base(
        {
            "hysteria2_obfs_mode": "salamander",
            "hysteria2_obfs_password": secret,
        }
    )
    assert stored_base == {"udp": [{"type": "padding", "settings": {"size": 5}}]}

    enabled = merge_finalmask(stored_base, "salamander", secret)
    assert enabled["udp"] == [
        {"type": "salamander", "settings": {"password": secret}}
    ]

    disabled = merge_finalmask(stored_base, "none", "")
    assert disabled == stored_base
