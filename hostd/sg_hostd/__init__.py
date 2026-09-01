"""Limited host helper for SG-Gateway."""


# SG_GATEWAY_02206_CLIENTS_KEYS_FINAL_CONTRACT_V1
def _install_clients_keys_contract() -> None:
    from sg_hostd import data_backup_runtime as data_backup_runtime
    from sg_hostd import clients_keys_tls_backup_patch as tls_backup_patch
    from sg_hostd.clients_keys_backup_patch import install
    from sg_hostd.clients_keys_tls_backup_patch import install as install_tls
    from sg_hostd.clients_keys_tls_contract_fix import install as install_tls_fix

    install(data_backup_runtime)
    install_tls(data_backup_runtime)
    install_tls_fix(data_backup_runtime, tls_backup_patch)


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

from importlib import import_module as _import_module
from sg_hostd.awg31_integration import install as _install_awg31_apply

_install_awg31_apply(_import_module("sg_hostd.client_runtime"))
del _install_awg31_apply

from sg_hostd.xray_stale_profile_patch import install as _install_xray_stale_profile
_install_xray_stale_profile(_import_module("sg_hostd.client_runtime"))
del _install_xray_stale_profile

from sg_hostd.awg31_commands import install as _install_awg31_commands
_install_awg31_commands(_import_module("sg_hostd.commands"))
del _install_awg31_commands

# SG_GATEWAY_02207_NAIVEPROXY_COMMANDS
from sg_hostd.naiveproxy_commands import install as _install_naiveproxy_commands
_install_naiveproxy_commands(_import_module("sg_hostd.commands"))
del _install_naiveproxy_commands

# SG_GATEWAY_02207_NAIVEPROXY_LISTENER_GUARD
from sg_hostd.naiveproxy_listener_patch import install as _install_naiveproxy_listener
_install_naiveproxy_listener(_import_module("sg_hostd.naiveproxy_runtime"))
del _install_naiveproxy_listener

# SG_GATEWAY_02207_NAIVEPROXY_FIREWALL
from sg_hostd.naiveproxy_firewall_patch import install as _install_naiveproxy_firewall
_install_naiveproxy_firewall(_import_module("sg_hostd.naiveproxy_runtime"))
del _install_naiveproxy_firewall

# SG_GATEWAY_02207_NAIVEPROXY_DIAGNOSTICS
from sg_hostd.naiveproxy_diagnostics_patch import install as _install_naiveproxy_diagnostics
_install_naiveproxy_diagnostics(_import_module("sg_hostd.naiveproxy_runtime"))
del _install_naiveproxy_diagnostics

# SG_GATEWAY_02207_NAIVEPROXY_CLIENT_RUNTIME
from sg_hostd.naiveproxy_client_runtime_patch import install as _install_naiveproxy_client_runtime
_install_naiveproxy_client_runtime(
    _import_module("sg_hostd.client_runtime"),
    _import_module("sg_hostd.commands"),
    _import_module("sg_hostd.naiveproxy_runtime"),
)
del _install_naiveproxy_client_runtime
del _import_module

# SG_GATEWAY_02207_NAIVEPROXY_BACKUP_TLS
from importlib import import_module as _naive_import_module
from sg_hostd.naiveproxy_backup_patch import install as _install_naiveproxy_backup
_install_naiveproxy_backup(
    _naive_import_module("sg_hostd.full_backup_runtime"),
    _naive_import_module("sg_hostd.data_backup_runtime"),
    _naive_import_module("sg_hostd.operation_jobs"),
)
del _install_naiveproxy_backup
del _naive_import_module
