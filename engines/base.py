from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EngineStatus:
    name: str
    running: bool
    message: str


@dataclass(frozen=True)
class ClientAccess:
    label: str
    kind: str
    value: str


class EngineAdapter(Protocol):
    name: str

    def status(self) -> EngineStatus:
        ...

    def validate(self) -> None:
        ...

    def apply(self) -> None:
        ...

    def rollback(self) -> None:
        ...

    def create_client(self, client_id: str, display_name: str) -> list[ClientAccess]:
        ...

    def update_client(self, client_id: str, display_name: str, enabled: bool) -> None:
        ...

    def delete_client(self, client_id: str) -> None:
        ...

    def export_access(self, client_id: str) -> list[ClientAccess]:
        ...
