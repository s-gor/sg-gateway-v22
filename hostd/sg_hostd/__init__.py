"""Limited host helper for SG-Gateway."""


# SG_GATEWAY_02206_CLIENTS_KEYS_FINAL_CONTRACT_V1
# Install the final Clients & Keys policy once at package import so every
# hostd entry point (service, commands and tests) uses the same archive rules.
def _install_clients_keys_contract() -> None:
    from sg_hostd import data_backup_runtime as data_backup_runtime
    from sg_hostd.clients_keys_backup_patch import install

    install(data_backup_runtime)


_install_clients_keys_contract()
del _install_clients_keys_contract
