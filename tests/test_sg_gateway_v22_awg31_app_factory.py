from __future__ import annotations

import importlib
import inspect
from pathlib import Path

from flask import Flask

from app import db


def _route_count(app: Flask, endpoint: str) -> int:
    return sum(1 for rule in app.url_map.iter_rules() if rule.endpoint == endpoint)


def test_awg31_registration_is_explicit_idempotent_and_factory_local(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(db, "get_database_path", lambda: tmp_path / "factory.sqlite")
    from app.clients.awg31_stage2 import register_awg31
    from app.main import create_app

    first = create_app()
    second = create_app()
    register_awg31(first)
    register_awg31(first)

    for application in (first, second):
        assert _route_count(application, "awg31.api_settings") == 1
        assert _route_count(application, "awg31.update_settings_form") == 1
        assert application.extensions["awg31_stage2"] is True
        processors = application.template_context_processors[None]
        assert sum(item.__name__ == "_settings_context" for item in processors) == 1


def test_reload_does_not_mutate_existing_or_unrelated_flask_apps(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(db, "get_database_path", lambda: tmp_path / "reload.sqlite")
    from app.main import create_app
    import app.clients.awg31_stage2 as stage2

    existing = create_app()
    unrelated = Flask("unrelated-awg31-regression")
    flask_init = Flask.__init__
    existing_rules = tuple(str(rule) for rule in existing.url_map.iter_rules())
    existing_processors = tuple(existing.template_context_processors[None])

    importlib.reload(stage2)
    importlib.reload(importlib.import_module("app.clients"))

    assert Flask.__init__ is flask_init
    assert tuple(str(rule) for rule in existing.url_map.iter_rules()) == existing_rules
    assert tuple(existing.template_context_processors[None]) == existing_processors
    assert "awg31" not in unrelated.blueprints
    assert not any("awg31" in str(rule) for rule in unrelated.url_map.iter_rules())
    assert all(
        processor.__name__ != "_settings_context"
        for processor in unrelated.template_context_processors[None]
    )


def test_exports_and_access_cards_are_normal_dependencies_without_patching() -> None:
    from app.clients import access, exports
    from app.clients import awg31_stage2

    assert exports.protocol_engine("amneziawg31") == "amneziawg31"
    assert exports.protocol_engine("amneziawg31-uri") == "amneziawg31"
    assert exports.build_awg31_config is awg31_stage2.build_awg31_config
    assert exports.build_awg31_uri is awg31_stage2.build_awg31_uri

    exports_source = inspect.getsource(exports)
    access_source = inspect.getsource(access)
    stage2_source = inspect.getsource(awg31_stage2)
    assert "def build_awg31_config" in exports_source
    assert 'deployments.get("amneziawg31")' in access_source
    assert "Flask.__init__" not in stage2_source
    assert "exports.build_protocol_export =" not in stage2_source
    assert "access.build_access_cards =" not in stage2_source
