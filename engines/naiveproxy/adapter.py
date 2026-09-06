from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from app.naiveproxy.runtime import (
    DEFAULT_BINARY,
    DEFAULT_CONFIG_DIR,
    DEFAULT_SERVICE,
    DEFAULT_STATE_DIR,
    NaiveProxyError,
    NaiveProxySettings,
    NaiveProxyUser,
    atomic_write,
    build_client_uri,
    generate_user,
    validate_runtime,
    write_runtime,
)
from engines.base import ClientAccess, EngineStatus

Runner = Callable[..., subprocess.CompletedProcess]


class NaiveProxyAdapter:
    name = "naiveproxy"

    def __init__(
        self,
        state_dir: Path = DEFAULT_STATE_DIR,
        config_dir: Path = DEFAULT_CONFIG_DIR,
        binary: Path = DEFAULT_BINARY,
        runner: Runner = subprocess.run,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.config_dir = Path(config_dir)
        self.binary = Path(binary)
        self.runner = runner

    @property
    def state_path(self) -> Path:
        return self.state_dir / "state.json"

    @property
    def config_path(self) -> Path:
        return self.config_dir / "Caddyfile"

    def _load(self) -> dict:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"settings": {}, "users": []}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise NaiveProxyError(f"Повреждено состояние NaiveProxy: {exc}") from exc
        if not isinstance(value, dict):
            raise NaiveProxyError("Повреждено состояние NaiveProxy")
        value.setdefault("settings", {})
        value.setdefault("users", [])
        return value

    @staticmethod
    def _settings(state: dict) -> NaiveProxySettings:
        raw = state.get("settings")
        if not isinstance(raw, dict) or not str(raw.get("domain") or "").strip():
            raise NaiveProxyError("NaiveProxy ещё не настроен: отсутствует TLS-домен")
        return NaiveProxySettings(**raw).normalized()

    @staticmethod
    def _users(state: dict) -> list[NaiveProxyUser]:
        raw = state.get("users")
        if not isinstance(raw, list):
            raise NaiveProxyError("Повреждён список пользователей NaiveProxy")
        return [NaiveProxyUser(**item) for item in raw if isinstance(item, dict)]

    def _save(self, state: dict) -> None:
        settings = self._settings(state)
        users = self._users(state)
        write_runtime(
            settings,
            users,
            config_dir=self.config_dir,
            state_dir=self.state_dir,
        )

    def status(self) -> EngineStatus:
        try:
            result = self.runner(
                ["systemctl", "is-active", "--quiet", DEFAULT_SERVICE],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return EngineStatus(name=self.name, running=False, message=str(exc))
        return EngineStatus(
            name=self.name,
            running=result.returncode == 0,
            message="active" if result.returncode == 0 else "inactive",
        )

    def validate(self) -> None:
        validate_runtime(binary=self.binary, config_path=self.config_path)

    def apply(self) -> None:
        self.validate()
        self.runner(["systemctl", "restart", DEFAULT_SERVICE], check=True, timeout=30)

    def rollback(self) -> None:
        state_backup = self.state_dir / "state.json.previous"
        config_backup = self.config_dir / "Caddyfile.previous"
        if not state_backup.is_file() or not config_backup.is_file():
            raise NaiveProxyError("Нет полного сохранённого состояния NaiveProxy для отката")
        state_content = state_backup.read_text(encoding="utf-8")
        config_content = config_backup.read_text(encoding="utf-8")
        json.loads(state_content)
        atomic_write(self.state_path, state_content, 0o600)
        atomic_write(self.config_path, config_content, 0o640)
        self.apply()

    def create_client(self, client_id: str, display_name: str) -> list[ClientAccess]:
        state = self._load()
        settings = self._settings(state)
        users = self._users(state)
        if any(user.client_id == str(client_id) for user in users):
            raise NaiveProxyError(f"Клиент NaiveProxy {client_id} уже существует")
        user = generate_user(f"sg-{client_id}", client_id=str(client_id))
        users.append(user)
        state["users"] = [user.__dict__ for user in users]
        self._save(state)
        return [
            ClientAccess(
                label=display_name,
                kind="uri",
                value=build_client_uri(settings, user, display_name),
            )
        ]

    def update_client(self, client_id: str, display_name: str, enabled: bool) -> None:
        state = self._load()
        users = self._users(state)
        found = False
        updated: list[NaiveProxyUser] = []
        for user in users:
            if user.client_id == str(client_id):
                found = True
                updated.append(
                    NaiveProxyUser(
                        username=user.username,
                        password=user.password,
                        enabled=bool(enabled),
                        client_id=user.client_id,
                    )
                )
            else:
                updated.append(user)
        if not found:
            raise NaiveProxyError(f"Клиент NaiveProxy {client_id} не найден")
        state["users"] = [user.__dict__ for user in updated]
        self._save(state)

    def delete_client(self, client_id: str) -> None:
        state = self._load()
        users = self._users(state)
        remaining = [user for user in users if user.client_id != str(client_id)]
        if len(remaining) == len(users):
            raise NaiveProxyError(f"Клиент NaiveProxy {client_id} не найден")
        state["users"] = [user.__dict__ for user in remaining]
        self._save(state)

    def export_access(self, client_id: str) -> list[ClientAccess]:
        state = self._load()
        settings = self._settings(state)
        for user in self._users(state):
            if user.client_id == str(client_id):
                value = build_client_uri(settings, user, f"SG-Gateway · {client_id}")
                return (
                    [ClientAccess(label=f"SG-Gateway · {client_id}", kind="uri", value=value)]
                    if value
                    else []
                )
        return []
