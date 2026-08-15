# Installation

Use a fresh Ubuntu server. From a checked-out SG-Gateway repository:

```bash
chmod +x install.sh
sudo ./install.sh
```

The current production installer is the root-level `install.sh`. It installs a
native systemd runtime and does not use Docker.

Important defaults in 021:

- panel HTTPS port: `63443`;
- Xray Reality TCP port: `443`;
- AmneziaWG: fixed UDP `585`;
- XHTTP Reality: `8444`;
- XHTTP TLS: `8445`;
- Hysteria 2: `8446`.

The installer writes its protected log to:

```text
/var/log/sg-gateway-installer-021.log
```

Do not publish that log without reviewing it, even though the installer applies
credential redaction.
