from __future__ import annotations

from functools import wraps


RETIRED_ENGINES = frozenset({"amneziawg", "amneziawg3"})


def install(repository) -> None:
    """Retire AWG2/AWG3 without destroying credentials from legacy backups.

    The rows may remain in device_credentials for rollback/audit compatibility,
    but product-facing repository reads and new/edit access selection no longer
    expose or create these engines.
    """

    if getattr(repository, "_retired_awg_installed", False):
        return

    repository.SUPPORTED_ENGINES = tuple(
        engine for engine in repository.SUPPORTED_ENGINES
        if engine not in RETIRED_ENGINES
    )
    repository.RUNTIME_ENGINES = tuple(
        engine for engine in repository.RUNTIME_ENGINES
        if engine not in RETIRED_ENGINES
    )

    original_list_device_credentials = repository.list_device_credentials

    @wraps(original_list_device_credentials)
    def list_device_credentials(device_id: int):
        return [
            item for item in original_list_device_credentials(device_id)
            if item.engine not in RETIRED_ENGINES
        ]

    repository.list_device_credentials = list_device_credentials

    original_aggregate_status = repository._aggregate_status

    @wraps(original_aggregate_status)
    def aggregate_status(rows, engine: str) -> str:
        if engine in RETIRED_ENGINES:
            return "missing"
        return original_aggregate_status(rows, engine)

    repository._aggregate_status = aggregate_status
    repository._retired_awg_installed = True
