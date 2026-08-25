"""Limited host helper for SG-Gateway."""


# SG_GATEWAY_02206_CLIENTS_KEYS_FINAL_CONTRACT_V1
# Install the final Clients & Keys policy once at package import so every
# hostd entry point (service, commands and tests) uses the same archive rules.
def _install_clients_keys_contract() -> None:
    from sg_hostd import data_backup_runtime as data_backup_runtime
    from sg_hostd import clients_keys_tls_backup_patch as tls_backup_patch
    from sg_hostd.clients_keys_backup_patch import install
    from sg_hostd.clients_keys_tls_backup_patch import install as install_tls
    from sg_hostd.clients_keys_tls_contract_fix import install as install_tls_fix

    install(data_backup_runtime)
    install_tls(data_backup_runtime)
    install_tls_fix(data_backup_runtime, tls_backup_patch)


# SG_GATEWAY_02206_FULL_RESTORE_HARDENING_V1
# dev-02206 adds restore-specific disk preflight and validated Safety Rollback
# without changing the frozen stable implementation.
def _install_full_restore_hardening() -> None:
    from sg_hostd import full_backup_runtime as full_backup_runtime
    from sg_hostd import restore_hardening_patch as restore_hardening_patch
    from sg_hostd.restore_hardening_patch import install as install_restore
    from sg_hostd.restore_service_health_patch import install as install_service_health
    from sg_hostd.clients_keys_portable_restore_patch import install as install_clients_restore

    install_restore(full_backup_runtime)
    install_service_health(restore_hardening_patch)
    install_clients_restore(restore_hardening_patch, full_backup_runtime)


_install_clients_keys_contract()
_install_full_restore_hardening()
del _install_clients_keys_contract
del _install_full_restore_hardening

# SG_GATEWAY_AWG31_STAGE1_CORE
from importlib import import_module as _import_module
from sg_hostd.awg31_integration import install as _install_awg31_apply

_install_awg31_apply(_import_module("sg_hostd.client_runtime"))
del _import_module
del _install_awg31_apply

# SG_GATEWAY_AWG31_STAGE2_COMMANDS
from importlib import import_module as _stage2_import_module
from sg_hostd.awg31_commands import install as _install_awg31_commands

_install_awg31_commands(_stage2_import_module("sg_hostd.commands"))
del _stage2_import_module
del _install_awg31_commands
