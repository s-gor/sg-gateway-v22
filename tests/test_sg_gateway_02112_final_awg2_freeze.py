from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_02112_final_awg2_freeze() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert version == "0.1.0-022.04"
    release = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    assert release["rebuild_policy"]["baseline"] == "0.1.0-021.12"

    req = json.loads((ROOT / "SG-GATEWAY-021-REQUIREMENTS.json").read_text(encoding="utf-8"))
    assert req["version"] == "0.1.0-021.12"
    assert req["status"] == "FINAL-AWG2"
    assert req["feature_frozen"] is True
    assert req["next_development_line"] == "0.1.0-022.01"
    assert req["invariants"]["amneziawg_generation"] == "AWG2"
    assert req["invariants"]["traffic_features"] is False
    assert req["invariants"]["safe_update_touches_cores"] is False

    freeze = json.loads((ROOT / "SG-GATEWAY-02112-FINAL-AWG2.json").read_text(encoding="utf-8"))
    assert freeze["baseline"] == "FINAL-AWG2"
    assert freeze["awg_generation"] == "AWG2"
    assert freeze["next_development_line"] == "0.1.0-022.01"
    assert freeze["policy"]["awg3_in_02112"] is False
    assert freeze["policy"]["new_features_in_02112"] is False

    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'AMNEZIAWG_TOOLS_VERSION="1.0.20260618-2"' in installer
    assert 'AMNEZIAWG_KMOD_VERSION="1.0.20260329-2"' in installer

    updater = (ROOT / "deploy" / "update-from-github.sh").read_text(encoding="utf-8")
    assert "SG_GATEWAY_02112_LIGHT_UPDATE_FIX9_R2" in updater
    assert "sparse-checkout set app hostd deploy" in updater

    frozen_doc = (ROOT / "SG-GATEWAY-02112-FINAL-AWG2.md").read_text(encoding="utf-8")
    assert "FINAL AWG2" in frozen_doc
    assert "022.01" in frozen_doc
    assert "021.13" not in frozen_doc

    sums = (ROOT / "SOURCE-SHA256SUMS").read_text(encoding="utf-8")
    assert len(sums.strip().splitlines()) > 10
