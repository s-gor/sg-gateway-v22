from __future__ import annotations

from typing import Any

from app.security.sg_infosec_presentation import (
    get_ip_intelligence_resolver,
    present_guard_overview,
    present_management_overview,
)


def register_sg_infosec_presentation(app: Any) -> None:
    extensions = getattr(app, "extensions", None)
    if not isinstance(extensions, dict):
        return
    if extensions.get("sg_infosec_presentation") is True:
        return

    resolver = get_ip_intelligence_resolver()
    management_extension = extensions.get("sg_infosec_management")
    if isinstance(management_extension, dict):
        management = management_extension.get("client")
        original = getattr(management, "overview", None)
        if callable(original):
            def management_overview():
                return present_management_overview(
                    original(),
                    resolver=resolver,
                )

            management.overview = management_overview

    guard_extension = extensions.get("sg_infosec_guard")
    if isinstance(guard_extension, dict):
        engine = guard_extension.get("engine")
        original_guard = getattr(engine, "overview", None)
        if callable(original_guard):
            def guard_overview():
                return present_guard_overview(
                    original_guard(),
                    resolver=resolver,
                )

            engine.overview = guard_overview

    extensions["sg_infosec_presentation"] = True
