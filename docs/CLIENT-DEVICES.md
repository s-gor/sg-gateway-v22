# SG-Gateway client access model (Preview 46)

Preview 46 keeps the operator workflow simple while separating independent
accesses internally.

## Model

```text
Client
├── Primary access
└── Optional device access
    ├── device credentials
    └── generated connection profiles
```

The existing `clients` table is the human/client entity. Preview 46 adds:

- `devices` — independently enabled accesses such as Phone, Laptop, TV;
- `device_credentials` — credentials for Xray, Hysteria, Mieru and the other
  selected engines.

Connection links are generated, not treated as keys of their own. One VLESS
UUID belonging to a device can produce Reality TCP, XHTTP Reality and XHTTP TLS
profiles. Another device receives another UUID.

Server endpoint values such as Reality public key, Short ID, SNI, XHTTP path and
VLESS Client Encryption remain shared server-profile parameters.

## Upgrade migration

Each legacy client is migrated to exactly one primary device named
`Основной доступ`. Existing UUIDs, passwords, engine object IDs, selected
profiles, statuses and dates are copied without rotation. The legacy deployment
table remains as a reversible migration source.

## Operator UX

Creating a client automatically creates its primary access. Additional accesses
need only a human name. Each access has:

- a personal SG Client subscription;
- copy, download and QR actions;
- independent enable/disable;
- independent deletion for non-primary accesses;
- technical profile links hidden under an expert disclosure.

Deleting or changing an access applies the complete runtime transactionally. If
runtime application fails, all devices and credentials of the client are
restored from the exact snapshot and the previous runtime is applied again.

## SG-Panel transfer

Do not copy this model to SG-Panel until Preview 46 has passed a real upgrade,
new-device creation, independent disable and connection test on SG-Gateway.
