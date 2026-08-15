# Xray v26.6.27 · VLESS Encryption + Vision + XHTTP

Preview 31 bootstraps a fresh installation with **v26.6.27** and treats it as the minimum supported version. Maintenance can update Xray to a newer stable or explicitly selected pre-release build; panel upgrades preserve any already installed supported newer version and never downgrade it.

## VLESS Encryption

Preview 31 generates one VLESS Encryption pair with `xray vlessenc` when the pair is absent.

- `SG_GATEWAY_VLESS_DECRYPTION` stays in `/etc/sg-gateway/engine-secrets.env` with root-only permissions and is written to server-side XHTTP inbound `settings.decryption`.
- `SG_GATEWAY_VLESS_ENCRYPTION` is copied to Xray connection settings and client deployments, then exported in client VLESS links as `encryption=`.
- Both XHTTP profiles use `flow=xtls-rprx-vision` on the server and in client links.
- The classic RAW/REALITY profile keeps `decryption=none` and XTLS Vision.

## XHTTP modes

The server-side XHTTP inbound uses `mode=auto`, so it can accept supported client implementations. Each XHTTP profile has a client mode selector:

- `auto`
- `stream-one`
- `stream-up`
- `packet-up`

The selected mode is exported in the VLESS URI. Defaults are `stream-one` for direct XHTTP + REALITY and `auto` for XHTTP + TLS/CDN paths.

## Upgrade and rollback

An upgrade preserves UUIDs, ports, selected profiles, Reality keys, AmneziaWG keys and existing client records. Missing mode values are added without overwriting existing settings. If the VLESS pair is absent, Preview 31 creates it and migrates existing Xray deployments.

The backup now also includes the Xray binary, geodata and Xray systemd units. A failed installation can restore the previous Xray runtime together with the panel files and database.


## Preview 34 mode and export policy

The XHTTP server inbound stays in `auto`. The client can select `auto`,
`stream-one`, `stream-up`, or `packet-up`. The selection is exported unchanged
to the VLESS link, QR code, and SG Client Base64 subscription. Both XHTTP
Reality and XHTTP TLS retain `flow=xtls-rprx-vision` and the full client
`encryption` value.
