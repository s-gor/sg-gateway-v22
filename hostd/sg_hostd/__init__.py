"""Limited host helper for SG-Gateway."""


# SG_GATEWAY_02206_CLIENTS_KEYS_FINAL_CONTRACT_V1
# Install the final Clients & Keys policy once at package import so every
# hostd entry point (service, commands and tests) uses the same archive rules.
def _install_clients_keys_contract() -> None:
    from sg_hostd import data_backup_runtime as data_backup_runtime
    from sg_hostd.clients_keys_backup_patch import install

    install(data_backup_runtime)


# SG_GATEWAY_02206_FULL_RESTORE_HARDENING_V1
# dev-02206 adds restore-specific disk preflight and validated Safety Rollback
# without changing the frozen stable implementation.
def _install_full_restore_hardening() -> None:
    from sg_hostd import full_backup_runtime as full_backup_runtime
    from sg_hostd import restore_hardening_patch as restore_hardening_patch
    from sg_hostd.restore_hardening_patch import install as install_restore
    from sg_hostd.restore_service_health_patch import install as install_service_health

    install_restore(full_backup_runtime)
    install_service_health(restore_hardening_patch)


_install_clients_keys_contract()
_install_full_restore_hardening()
del _install_clients_keys_contract
del _install_full_restore_hardening
