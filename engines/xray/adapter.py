from engines.base import ClientAccess, EngineStatus


class XrayAdapter:
    name = "xray"

    def status(self) -> EngineStatus:
        return EngineStatus(name=self.name, running=False, message="Not configured")

    def validate(self) -> None:
        raise NotImplementedError

    def apply(self) -> None:
        raise NotImplementedError

    def rollback(self) -> None:
        raise NotImplementedError

    def create_client(self, client_id: str, display_name: str) -> list[ClientAccess]:
        raise NotImplementedError

    def update_client(self, client_id: str, display_name: str, enabled: bool) -> None:
        raise NotImplementedError

    def delete_client(self, client_id: str) -> None:
        raise NotImplementedError

    def export_access(self, client_id: str) -> list[ClientAccess]:
        raise NotImplementedError
