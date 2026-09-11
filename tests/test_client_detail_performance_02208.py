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


def test_client_detail_batches_credentials_for_all_devices(monkeypatch):
    import app.main as main

    client = Client(1, "client", True, None, "missing", "missing")
    devices = [
        Device(2, 1, "main", True, None, True, "now"),
        Device(3, 1, "phone", True, None, False, "now"),
    ]
    deployments = {
        2: [ClientDeployment("amneziawg31", "applied", None, "{}", 2)],
        3: [ClientDeployment("xray", "applied", None, json.dumps({"profiles": ["reality_tcp"]}), 3)],
    }
    token_map = {2: ["amneziawg31"], 3: ["xray_reality_tcp"]}
    calls = {"batch": 0, "tokens": 0, "cards": 0}

    monkeypatch.setattr(main, "get_client", lambda client_id: client)
    monkeypatch.setattr(main, "list_devices", lambda client_id: devices)
    monkeypatch.setattr(main, "xray_profiles_overview", lambda: {"profiles": []})
    monkeypatch.setattr(main, "security_tls_overview", lambda: {})
    monkeypatch.setattr(
        main,
        "device_access_tokens",
        lambda *_: (_ for _ in ()).throw(AssertionError("per-device credential query must not run")),
    )

    def batch(client_id):
        calls["batch"] += 1
        assert client_id == 1
        return deployments

    def tokens(rows):
        calls["tokens"] += 1
        device_id = rows[0].device_id
        return token_map[device_id]

    def cards(*args, **kwargs):
        calls["cards"] += 1
        return []

    monkeypatch.setattr(main, "device_deployments_map", batch, raising=False)
    monkeypatch.setattr(main, "deployment_access_tokens", tokens, raising=False)
    monkeypatch.setattr(main, "build_access_cards", cards)
    monkeypatch.setattr(main, "render_template", lambda template, **context: (template, context))

    with main.app.test_request_context("/clients/1"):
        template, context = main.app.view_functions["client_detail"](1)

    assert template == "client_detail.html"
    assert [view["protocol_tokens"] for view in context["device_views"]] == [
        ["amneziawg31"],
        ["xray_reality_tcp"],
    ]
    assert calls == {"batch": 1, "tokens": 2, "cards": 2}
