# SG InfoSec complete protection

This integration adds the application-facing layer of SG InfoSec to SG-Gateway. It complements the unprivileged SG InfoSec detector and the separate nftables enforcer.

## Request path

The production application registers the components in this order:

1. SG InfoSec Unix-socket adapter;
2. SG InfoSec web guard, inserted at the first `before_request` position;
3. SG InfoSec decision/allowlist management UI;
4. web-guard settings, reputation and alert management.

The web guard runs before panel authentication. It is fail-open only for internal processing failures; an explicit matching security rule in `enforce` mode returns `403`, while a rate-limit decision returns `429`.

## Web protections

The reviewed built-in rules detect:

- requests for `.env`, `.git`, WordPress, phpMyAdmin, actuator, CGI and PHPUnit paths;
- path traversal and common double-encoded traversal forms;
- high-confidence SQL injection expressions;
- script, event-handler and dangerous embedded-object XSS forms;
- common shell command-injection forms;
- `TRACE`, `TRACK` and `CONNECT` methods;
- bodies exceeding the configured limit;
- excessive login and administrative API request rates.

Only a bounded query string and a bounded body for JSON, form, text and XML media types are inspected. Raw paths, queries and bodies are not written to the alert history. Alerts contain only canonical IP, score, action, fixed rule IDs, scope and reviewed reputation fields.

## Modes and reactions

- `off`: no application-layer inspection;
- `monitor`: inspect, score, record and optionally notify, but do not reject;
- `enforce`: return `403` for high-confidence threats and `429` for rate limits.

High-confidence enforcement also requests a one-hour application decision from the local SG InfoSec management bridge. The bridge remains restricted to the `sg-gateway` Unix peer and the reviewed SG InfoSec control routes.

## Reputation

The panel accepts a local JSON file with up to 20,000 CIDR entries. Each entry supports:

- `cidr`;
- `score` from 1 to 100;
- optional two-letter `country`;
- optional numeric `asn`;
- optional `tags`;
- optional ISO-8601 `expires_at`.

Longest-prefix matching is used. Expired entries are discarded during validation. The file is validated completely and then replaced atomically. There are no automatic external requests or telemetry.

Example:

```json
{
  "entries": [
    {
      "cidr": "203.0.113.0/24",
      "score": 90,
      "country": "ZZ",
      "asn": 64500,
      "tags": ["scanner"]
    }
  ]
}
```

## Notifications

An optional HTTPS webhook receives bounded JSON alerts for events at or above the configured notification score. Delivery is asynchronous, has a two-second timeout and a bounded queue. Notification failure never blocks panel requests.

## Persistent state

The systemd unit fixes writable state under:

```text
/var/lib/sg-gateway/infosec/guard.json
/var/lib/sg-gateway/infosec/reputation.json
/var/lib/sg-gateway/infosec/alerts.jsonl
```

Files are created atomically with restrictive modes. SG-Gateway does not need write access to `/etc` for normal operation.

## Isolation

The guard does not alter AWG interfaces, VPN ports 585–587, routing, subscriptions or foreign nftables tables. SSH decisions remain owned by the SG InfoSec enforcer and affect TCP/22 only. Panel and API decisions remain application-scoped.
