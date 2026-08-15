# Architecture

SG-Gateway manages one standalone Ubuntu server. It has no Controller, Node,
Cluster or Cascade roles.

## Components

- `app/`: web panel, database access, clients, exports, Routing, GeoFiles,
  maintenance, recovery and security.
- `hostd/`: privileged allow-listed host operations.
- `engines/`: common engine interfaces.
- Xray: VLESS and Hysteria 2 runtime.
- AmneziaWG: WireGuard-compatible tunnel runtime on UDP 585.
- Mihomo: managed Mieru, AnyTLS and TUIC listeners.
- sing-box: managed runtime used only for supported functions.
- Nginx: panel reverse proxy and certificate integration.

## Configuration lifecycle

```text
candidate -> validate -> backup -> apply -> health check -> active
```

A failed application must restore the previous database/configuration state and
leave the last known working runtime available.

## Filesystem

```text
/opt/sg-gateway
/etc/sg-gateway
/var/lib/sg-gateway
/var/log/sg-gateway
```
