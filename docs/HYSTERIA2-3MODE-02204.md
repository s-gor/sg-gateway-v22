# SG-Gateway 022.04 — Hysteria2 Off / Salamander / Gecko

Status: development candidate after live 022.04 Gecko validation.

## Contract

SG-Gateway exposes three explicit Hysteria2 obfuscation modes:

- `none` — obfuscation disabled;
- `salamander` — Xray FinalMask `type: salamander` with password only;
- `gecko` — the same Salamander primitive plus `packetSize: 512-1200`.

Gecko is the recommended mode for new profiles. Salamander remains available for compatibility.

## Client URI

Hysteria2 exports contain the canonical transport parameters only. SG-Gateway does not add `alpn=h3` to the Hysteria2 URI.

Examples of the managed obfuscation portion:

- Salamander: `obfs=salamander&obfs-password=...`
- Gecko: `obfs=gecko&obfs-password=...`

The server-side Xray Hysteria2 TLS configuration still uses ALPN `h3`; this is independent from the client URI cleanup.

## Stored FinalMask safety marker

`hysteria2_finalmask` carries a private SG-Gateway marker `_sg_hysteria2_obfs_managed`. The marker keeps an otherwise-empty stored base FinalMask non-empty, preventing HostD from rediscovering a currently-live managed Salamander/Gecko layer as unmanaged state while switching variants.

The marker is stripped by `merge_finalmask()` and is never emitted to the live Xray JSON.

## Migration from first 022.04 Gecko build

The first 022.04 build stored Gecko under the historical DB value `hysteria2_obfs_mode=salamander` while the live Xray FinalMask contained `packetSize=512-1200`.

The cleanup upgrade detects that exact live shape, migrates the DB mode to `gecko`, adds the managed marker, validates the Xray candidate, applies it transactionally, and verifies the resulting live FinalMask.

AWG2 and AWG3 runtime files are outside the cleanup scope.
