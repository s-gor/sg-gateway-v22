from __future__ import annotations

import hmac
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from flask import abort, flash, redirect, request, session, url_for

from app.security.auth import is_authenticated, require_auth
from app.security.sg_infosec_guard import (
    DEFAULT_REPUTATION_PATH,
    DEFAULT_SETTINGS_PATH,
    GuardEngine,
    GuardSettings,
    ReputationIndex,
)

MAX_REPUTATION_UPLOAD_BYTES = 2 * 1024 * 1024


def _settings_path() -> Path:
    return Path(
        os.environ.get(
            "SG_INFOSEC_GUARD_SETTINGS",
            str(DEFAULT_SETTINGS_PATH),
        )
    )


def _reputation_path() -> Path:
    return Path(
        os.environ.get(
            "SG_INFOSEC_REPUTATION_FILE",
            str(DEFAULT_REPUTATION_PATH),
        )
    )


def _require_csrf() -> None:
    expected = str(session.get("sg_infosec_csrf") or "")
    supplied = str(request.form.get("csrf_token") or "")
    if not expected or not supplied or not hmac.compare_digest(
        expected,
        supplied,
    ):
        abort(400, description="invalid CSRF token")


def _guard_engine(app: Any) -> GuardEngine | None:
    extension = getattr(app, "extensions", {}).get("sg_infosec_guard")
    if not isinstance(extension, dict):
        return None
    engine = extension.get("engine")
    return engine if isinstance(engine, GuardEngine) else None


def _integer(
    value: object,
    *,
    label: str,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(str(value or "").strip())
    except ValueError as exc:
        raise ValueError(f"{label}: требуется целое число.") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(
            f"{label}: допустимо значение от {minimum} до {maximum}."
        )
    return parsed


def _save_reputation_payload(
    payload: str,
    *,
    destination: Path,
) -> ReputationIndex:
    encoded = payload.encode("utf-8")
    if not encoded or len(encoded) > MAX_REPUTATION_UPLOAD_BYTES:
        raise ValueError(
            "Файл репутации должен содержать от 1 байта до 2 МБ."
        )
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise ValueError("Файл репутации должен содержать JSON-объект.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=".sg-infosec-reputation.",
            suffix=".json",
            delete=False,
        ) as handle:
            json.dump(decoded, handle, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        index = ReputationIndex.load(temporary_path)
        index.save(destination)
        return index
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def register_sg_infosec_guard_management(app: Any) -> None:
    extensions = getattr(app, "extensions", None)
    if (
        not isinstance(extensions, dict)
        or "sg_infosec_guard_management" in extensions
        or not callable(getattr(app, "context_processor", None))
        or not callable(getattr(app, "post", None))
    ):
        return

    @app.context_processor
    def _sg_infosec_guard_context():
        if request.path != "/security" or not is_authenticated():
            return {}
        engine = _guard_engine(app)
        return {
            "sg_infosec_guard": (
                engine.overview()
                if engine is not None
                else {
                    "mode": "unavailable",
                    "settings": {},
                    "counters": {},
                    "alerts": [],
                    "unread_count": 0,
                    "reputation_count": 0,
                }
            )
        }

    @app.post("/security/infosec/guard/settings")
    @require_auth
    def security_infosec_guard_settings():
        _require_csrf()
        target = url_for("security") + "#sg-infosec-guard"
        engine = _guard_engine(app)
        if engine is None:
            flash("Веб-защита SG InfoSec недоступна.", "error")
            return redirect(target)
        try:
            mode = str(request.form.get("mode") or "").strip().lower()
            settings = GuardSettings(
                mode=mode,
                max_body_bytes=_integer(
                    request.form.get("max_body_bytes"),
                    label="Размер тела запроса",
                    minimum=1024,
                    maximum=1_048_576,
                ),
                login_requests_per_minute=_integer(
                    request.form.get("login_requests_per_minute"),
                    label="Лимит входа",
                    minimum=1,
                    maximum=10_000,
                ),
                api_requests_per_minute=_integer(
                    request.form.get("api_requests_per_minute"),
                    label="Лимит API",
                    minimum=1,
                    maximum=100_000,
                ),
                block_score=_integer(
                    request.form.get("block_score"),
                    label="Порог блокировки",
                    minimum=1,
                    maximum=100,
                ),
                notification_min_score=_integer(
                    request.form.get("notification_min_score"),
                    label="Порог уведомления",
                    minimum=1,
                    maximum=100,
                ),
                notification_webhook=str(
                    request.form.get("notification_webhook") or ""
                ).strip(),
            )
            settings.save(_settings_path())
            engine.update_settings(settings)
            flash("Настройки веб-защиты сохранены.", "success")
        except (OSError, TypeError, ValueError) as exc:
            flash(str(exc) or "Настройки веб-защиты отклонены.", "error")
        return redirect(target)

    @app.post("/security/infosec/guard/alerts/<alert_id>/ack")
    @require_auth
    def security_infosec_guard_alert_ack(alert_id: str):
        _require_csrf()
        target = url_for("security") + "#sg-infosec-guard"
        engine = _guard_engine(app)
        if engine is None:
            flash("Веб-защита SG InfoSec недоступна.", "error")
        elif engine.alerts.acknowledge(alert_id):
            flash("Событие отмечено как просмотренное.", "success")
        else:
            flash("Событие не найдено.", "error")
        return redirect(target)

    @app.post("/security/infosec/guard/alerts/ack-all")
    @require_auth
    def security_infosec_guard_alert_ack_all():
        _require_csrf()
        target = url_for("security") + "#sg-infosec-guard"
        engine = _guard_engine(app)
        if engine is None:
            flash("Веб-защита SG InfoSec недоступна.", "error")
        else:
            changed = engine.alerts.acknowledge_all()
            flash(f"Просмотрено событий: {changed}.", "success")
        return redirect(target)

    @app.post("/security/infosec/guard/reputation")
    @require_auth
    def security_infosec_guard_reputation():
        _require_csrf()
        target = url_for("security") + "#sg-infosec-guard"
        engine = _guard_engine(app)
        if engine is None:
            flash("Веб-защита SG InfoSec недоступна.", "error")
            return redirect(target)
        try:
            payload = str(request.form.get("reputation_json") or "")
            index = _save_reputation_payload(
                payload,
                destination=_reputation_path(),
            )
            engine.update_reputation(index)
            flash(
                f"Загружено записей репутации: {index.count()}.",
                "success",
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            flash(str(exc) or "Файл репутации отклонён.", "error")
        return redirect(target)

    extensions["sg_infosec_guard_management"] = True
