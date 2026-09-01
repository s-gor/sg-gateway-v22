from __future__ import annotations

from types import SimpleNamespace

from app.security.sg_infosec_guard import (
    AlertStore,
    GuardEngine,
    GuardSettings,
    register_sg_infosec_guard,
)


class FakeApp:
    def __init__(self) -> None:
        self.extensions = {}
        self.before_request_funcs = {None: [lambda: "auth"]}

    def before_request(self, function):
        self.before_request_funcs.setdefault(None, []).append(function)
        return function


def test_guard_registration_is_first_and_idempotent(tmp_path) -> None:
    app = FakeApp()
    engine = GuardEngine(
        settings=GuardSettings(mode="monitor"),
        alerts=AlertStore(tmp_path / "alerts.jsonl"),
    )

    register_sg_infosec_guard(app, engine=engine)
    before_count = len(app.before_request_funcs[None])
    register_sg_infosec_guard(app, engine=engine)

    assert app.before_request_funcs[None][0].__name__ == (
        "_sg_infosec_guard_before_request"
    )
    assert app.before_request_funcs[None][1]() == "auth"
    assert len(app.before_request_funcs[None]) == before_count
    assert app.extensions["sg_infosec_guard"]["engine"] is engine


def test_guard_attaches_existing_event_client(tmp_path) -> None:
    event_client = SimpleNamespace(emit_security_event=lambda **_: True)
    app = FakeApp()
    app.extensions["sg_infosec"] = {"client": event_client}
    engine = GuardEngine(
        settings=GuardSettings(mode="monitor"),
        alerts=AlertStore(tmp_path / "alerts.jsonl"),
    )

    register_sg_infosec_guard(app, engine=engine)

    assert engine.event_client is event_client
