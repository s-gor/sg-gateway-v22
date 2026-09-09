from __future__ import annotations


RETIRED_ENGINES = frozenset({"amneziawg", "amneziawg3"})


def install(client_runtime, awg3_runtime, runtime_contracts) -> None:
    """Remove AWG2/AWG3 from active runtime reconciliation.

    Legacy credentials are intentionally left untouched in the database so old
    Clients & Keys backups remain readable. They are no longer prerequisites,
    no longer applied, and no longer allowed to fail Client Apply.
    """

    if getattr(client_runtime, "_retired_awg_runtime_installed", False):
        return

    runtime_contracts.DEFAULT_SPECS = {
        engine: spec
        for engine, spec in runtime_contracts.DEFAULT_SPECS.items()
        if engine not in RETIRED_ENGINES
    }

    def retired_result(engine: str, title: str):
        return client_runtime.EngineResult(
            engine=engine,
            ok=True,
            message=f"{title}: retired; legacy credentials ignored",
            clients=0,
        )

    client_runtime._apply_awg = lambda: retired_result("amneziawg", "AWG2")
    awg3_runtime.apply_awg3 = lambda: retired_result("amneziawg3", "AWG3")
    client_runtime._retired_awg_runtime_installed = True
