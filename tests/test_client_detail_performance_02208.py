import json
from types import SimpleNamespace

from app.clients.repository import Client, ClientDeployment, Device


def test_access_cards_reuse_supplied_xray_overview(monkeypatch):
    from app.clients import access

    client = Client(1, "client", True, None, "missing", "applied")
    device = Device(2, 1, "main", True, None, True, "now")
    deployment = ClientDeployment(
        engine="xray",
        status="applied",
        engine_object_id=None,
        config_json=json.dumps({"profiles": ["reality_tcp", "xhttp_reality"]}),
        device_id=2,
    )
    state = {
        "profiles": [
            SimpleNamespace(id="reality_tcp", enabled=True, ready=True, mode="", title="Reality", port=443),
            SimpleNamespace(id="xhttp_reality", enabled=True, ready=True, mode="stream-one", title="XHTTP", port=8444),
        ]
    }
    calls = {"ready": 0, "build": 0}

    monkeypatch.setattr(access, "_deployment_map", lambda *_: {"xray": deployment})
    monkeypatch.setattr(access, "xray_profiles_overview", lambda: (_ for _ in ()).throw(AssertionError("overview recalculated")))

    def ready(*args, **kwargs):
        calls["ready"] += 1
        assert kwargs.get("xray_state") is state
        return True

    def build(*args, **kwargs):
        calls["build"] += 1
        assert kwargs.get("xray_state") is state
        return SimpleNamespace(body="vless://test")

    monkeypatch.setattr(access, "protocol_ready", ready)
    monkeypatch.setattr(access, "build_xray_profile_link", build)

    cards = access.build_access_cards(client, device, xray_state=state)

    assert [card.kind for card in cards] == ["xray-reality-tcp", "xray-xhttp-reality"]
    assert calls == {"ready": 2, "build": 2}


def test_exports_can_reuse_supplied_xray_overview(monkeypatch):
    from app.clients import exports

    state = {"profiles": [SimpleNamespace(id="reality_tcp", enabled=True, ready=True)]}
    monkeypatch.setattr(exports, "xray_profiles_overview", lambda: (_ for _ in ()).throw(AssertionError("overview recalculated")))
    returned_state, profile = exports._xray_profile("reality_tcp", state)
    assert returned_state is state
    assert profile is state["profiles"][0]
