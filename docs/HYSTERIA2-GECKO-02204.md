# SG-Gateway 022.04 — Hysteria2 Gecko

## Contract

This branch keeps the proven 022.03 isolated AWG3 userspace architecture and changes the managed Hysteria2 obfuscation from plain Salamander to Gecko.

### Server runtime

Xray still names the FinalMask primitive `salamander`. Gecko is activated by adding the packet-size range to the same layer:

```json
{
  "udp": [
    {
      "type": "salamander",
      "settings": {
        "password": "<managed password>",
        "packetSize": "512-1200"
      }
    }
  ]
}
```

The SG-Gateway database keeps the existing internal value `hysteria2_obfs_mode=salamander` so upgrades do not require a schema/state migration. The UI and exported Hysteria2 URI expose the actual client-facing mode as Gecko.

### Client export

Managed Hysteria2 links use:

- `obfs=gecko`
- the existing managed obfuscation password
- the normal Hysteria2 TLS/SNI parameters

### Compatibility

Plain Salamander is no longer the managed Hysteria2 mode in 022.04. Existing stored mode/password state is reused, but after applying Gecko clients must refresh their Hysteria2 link/profile so the client uses Gecko.

### Xray version

The pinned/proven Xray `26.6.27` already contains Gecko support, so 022.04 does not replace the Xray core merely to enable Gecko.

### AWG3

The 022.03 userspace architecture is preserved. AWG3 H1-H4 generation is now source-level and independent from the AWG2 obfuscation namespace.

## Verification contract

A valid 022.04 build must prove:

1. `merge_finalmask(..., "salamander", password)` renders Xray `type=salamander` with `packetSize=512-1200`.
2. Hysteria2 client exports use `obfs=gecko`.
3. The admin UI displays Gecko while keeping the internal form value compatible.
4. Xray minimum version is `26.6.27`.
5. AWG2 runtime stays unchanged by the AWG3 userspace installation.
