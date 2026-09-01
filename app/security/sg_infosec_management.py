from __future__ import annotations

import hmac
import http.client
import ipaddress
import json
import os
import re
import secrets
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import abort, flash, redirect, request, session, url_for

from app.security.auth import is_authenticated, require_auth

DEFAULT_MANAGEMENT_SOCKET = Path("/run/sg-infosec-bridge/management.sock")
DEFAULT_TIMEOUT_SECONDS = 0.75
MAX_RESPONSE_BYTES = 64 * 1024
MAX_BLOCK_HOURS = 168
_ALLOWED_SCOPES = frozenset({"admin-login", "admin-api", "ssh"})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: Path, timeout: float) -> None:
        super().__init__(host="localhost", timeout=timeout)
        self._socket_path = str(socket_path)

    def connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connection.settimeout(self.timeout)
            connection.connect(self._socket_path)
        except OSError:
            connection.close()
            raise
        self.sock = connection


def _canonical_ip(value: object) -> str:
    try:
        address = ipaddress.ip_address(str(value or "").strip())
    except ValueError as exc:
        raise ValueError("Введите корректный IPv4 или IPv6 адрес.") from exc
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    return address.compressed


def _canonical_prefix(value: object) -> str:
    try:
        network = ipaddress.ip_network(str(value or "").strip(), strict=False)
    except ValueError as exc:
        raise ValueError("Введите корректный IP-адрес или CIDR.") from exc
    return network.compressed


def _clean_text(value: object, *, label: str) -> str:
    text = " ".join(str(value or "").split())
    if not 3 <= len(text) <= 240:
        raise ValueError(f"{label} должна содержать от 3 до 240 символов.")
    return text


def _scope(value: object, *, optional: bool = False) -> str:
    text = str(value or "").strip()
    if optional and not text:
        return ""
    if text not in _ALLOWED_SCOPES:
        raise ValueError("Выбрана недопустимая область защиты.")
    return text


def _identifier(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(text):
        raise ValueError(f"Некорректный идентификатор {label}.")
    return text


def _parse_expiry(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Некорректная дата окончания allowlist.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    if parsed <= datetime.now(timezone.utc):
        raise ValueError("Дата окончания allowlist должна быть в будущем.")
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _empty_overview(message: str = "") -> dict[str, Any]:
    return {
        "available": False,
        "status": "Недоступен",
        "active_decisions": [],
        "active_count": 0,
        "history": [],
        "allowlist": [],
        "allowlist_count": 0,
        "audit": [],
        "last_sync": "—",
        "error": message or "Сервис управления SG-InfoSec недоступен.",
    }


class SGInfoSecManagementClient:
    def __init__(
        self,
        socket_path: str | os.PathLike[str] = DEFAULT_MANAGEMENT_SOCKET,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.socket_path = Path(socket_path)
        self.timeout = max(0.05, min(float(timeout), 3.0))

    @classmethod
    def from_environment(cls) -> "SGInfoSecManagementClient":
        raw_timeout = os.environ.get("SG_INFOSEC_MANAGEMENT_TIMEOUT_SECONDS", "").strip()
        try:
            timeout = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT_SECONDS
        except ValueError:
            timeout = DEFAULT_TIMEOUT_SECONDS
        return cls(
            socket_path=os.environ.get(
                "SG_INFOSEC_MANAGEMENT_SOCKET",
                str(DEFAULT_MANAGEMENT_SOCKET),
            ),
            timeout=timeout,
        )

    def _request(
        self,
        method: str,
        target: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]] | None:
        connection = _UnixHTTPConnection(self.socket_path, self.timeout)
        encoded = None
        headers = {
            "Accept": "application/json",
            "X-Request-ID": f"sg-gateway-web.{uuid.uuid4().hex}",
        }
        if payload is not None:
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            connection.request(method, target, body=encoded, headers=headers)
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                return None
            decoded = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(decoded, dict):
                return None
            return response.status, decoded
        except (
            OSError,
            TimeoutError,
            UnicodeError,
            ValueError,
            json.JSONDecodeError,
            http.client.HTTPException,
        ):
            return None
        finally:
            connection.close()

    @staticmethod
    def _items(result: tuple[int, dict[str, Any]] | None) -> list[dict[str, Any]]:
        if result is None or result[0] != 200:
            return []
        items = result[1].get("items")
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    def overview(self) -> dict[str, Any]:
        health = self._request("GET", "/v1/health")
        if health is None or health[0] != 200 or health[1].get("ok") is not True:
            message = ""
            if health is not None:
                message = str(health[1].get("message") or "")
            return _empty_overview(message)

        active = self._items(
            self._request("GET", "/v1/decisions?state=active&limit=100")
        )
        history = self._items(self._request("GET", "/v1/decisions?limit=30"))
        allowlist = self._items(self._request("GET", "/v1/allowlist?limit=100"))
        audit = self._items(self._request("GET", "/v1/audit?limit=30"))
        return {
            "available": True,
            "status": "Работает",
            "active_decisions": active,
            "active_count": len(active),
            "history": history,
            "allowlist": allowlist,
            "allowlist_count": len(allowlist),
            "audit": audit,
            "last_sync": datetime.now().astimezone().strftime("%d.%m.%Y %H:%M:%S"),
            "error": "",
        }

    @staticmethod
    def _action_result(
        result: tuple[int, dict[str, Any]] | None,
        expected: set[int],
        success_message: str,
    ) -> tuple[bool, str]:
        if result is None:
            return False, "Сервис управления SG-InfoSec недоступен."
        status, payload = result
        if status in expected:
            return True, success_message
        message = str(payload.get("message") or payload.get("code") or "Операция отклонена.")
        return False, message

    def create_manual_decision(
        self,
        *,
        ip: str,
        scope: str,
        duration: str,
        reason: str,
    ) -> tuple[bool, str]:
        return self._action_result(
            self._request(
                "POST",
                "/v1/decisions/manual",
                {
                    "ip": ip,
                    "scope": scope,
                    "duration": duration,
                    "reason": reason,
                },
            ),
            {201},
            "IP заблокирован.",
        )

    def revoke_decision(self, decision_id: str) -> tuple[bool, str]:
        decision_id = _identifier(decision_id, "блокировки")
        return self._action_result(
            self._request("POST", f"/v1/decisions/{decision_id}/revoke"),
            {200},
            "Блокировка снята.",
        )

    def create_allowlist(
        self,
        *,
        prefix: str,
        scope: str,
        description: str,
        expires_at: str | None = None,
    ) -> tuple[bool, str]:
        payload: dict[str, Any] = {
            "prefix": prefix,
            "scope": scope,
            "description": description,
        }
        if expires_at:
            payload["expires_at"] = expires_at
        return self._action_result(
            self._request("POST", "/v1/allowlist", payload),
            {201},
            "Allowlist обновлён.",
        )

    def delete_allowlist(self, entry_id: str) -> tuple[bool, str]:
        entry_id = _identifier(entry_id, "allowlist")
        return self._action_result(
            self._request("POST", f"/v1/allowlist/{entry_id}/delete"),
            {200},
            "Запись удалена из allowlist.",
        )


def _csrf_token() -> str:
    token = str(session.get("sg_infosec_csrf") or "")
    if not token:
        token = secrets.token_urlsafe(32)
        session["sg_infosec_csrf"] = token
    return token


def _require_csrf() -> None:
    expected = str(session.get("sg_infosec_csrf") or "")
    supplied = str(request.form.get("csrf_token") or "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        abort(400, description="invalid CSRF token")


def _flash_result(result: tuple[bool, str]) -> None:
    ok, message = result
    flash(message, "success" if ok else "error")


def register_sg_infosec_management(
    app: Any,
    *,
    client: SGInfoSecManagementClient | None = None,
) -> None:
    if "sg_infosec_management" in app.extensions:
        return
    management = client or SGInfoSecManagementClient.from_environment()

    @app.context_processor
    def _sg_infosec_management_context():
        if not is_authenticated():
            return {
                "sg_infosec": _empty_overview(),
                "sg_infosec_csrf_token": "",
            }
        return {
            "sg_infosec": management.overview(),
            "sg_infosec_csrf_token": _csrf_token(),
        }

    @app.post("/security/infosec/block")
    @require_auth
    def security_infosec_block():
        _require_csrf()
        target = url_for("security") + "#sg-infosec"
        try:
            ip = _canonical_ip(request.form.get("ip"))
            scope = _scope(request.form.get("scope"))
            hours = int(str(request.form.get("hours") or ""))
            if not 1 <= hours <= MAX_BLOCK_HOURS:
                raise ValueError("Срок блокировки должен быть от 1 до 168 часов.")
            reason = _clean_text(request.form.get("reason"), label="Причина")
            _flash_result(
                management.create_manual_decision(
                    ip=ip,
                    scope=scope,
                    duration=f"{hours}h",
                    reason=reason,
                )
            )
        except (TypeError, ValueError) as exc:
            flash(str(exc) or "Некорректные параметры блокировки.", "error")
        return redirect(target)

    @app.post("/security/infosec/decisions/<decision_id>/revoke")
    @require_auth
    def security_infosec_revoke(decision_id: str):
        _require_csrf()
        target = url_for("security") + "#sg-infosec"
        try:
            _flash_result(management.revoke_decision(_identifier(decision_id, "блокировки")))
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(target)

    @app.post("/security/infosec/allowlist")
    @require_auth
    def security_infosec_allowlist_add():
        _require_csrf()
        target = url_for("security") + "#sg-infosec"
        try:
            prefix = _canonical_prefix(request.form.get("prefix"))
            scope = _scope(request.form.get("scope"), optional=True)
            description = _clean_text(
                request.form.get("description"),
                label="Описание",
            )
            expires_at = _parse_expiry(request.form.get("expires_at"))
            _flash_result(
                management.create_allowlist(
                    prefix=prefix,
                    scope=scope,
                    description=description,
                    expires_at=expires_at,
                )
            )
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(target)

    @app.post("/security/infosec/allowlist/<entry_id>/delete")
    @require_auth
    def security_infosec_allowlist_delete(entry_id: str):
        _require_csrf()
        target = url_for("security") + "#sg-infosec"
        try:
            _flash_result(management.delete_allowlist(_identifier(entry_id, "allowlist")))
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(target)

    app.extensions["sg_infosec_management"] = {"client": management}
