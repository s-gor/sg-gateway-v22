# SG-Gateway 0.1.0-022.04 — Release Candidate

Status: **DEV / release candidate**. Branch: `fix30-ipv6-dual-stack`. The release remains a draft until final clean-install and live acceptance are complete.

## Release focus

022.04 is the first SG-Gateway line assembled around **Dual Stack IPv4 + IPv6**, isolated **AWG3 userspace**, independent WARP address-family health, explicit **Family Routing**, safer in-place updates, the expanded SG subscription pipeline, and the accumulated UI/runtime fixes from the V22 development line.

IPv4 remains the compatibility baseline. Lack of public IPv6 is normal and must never make installation fail. IPv6-only VPS support is not part of 022.04.

## Dual Stack IPv4 + IPv6

- Added separate runtime metadata for public IPv4 and IPv6 while preserving the legacy public-address value for compatibility.
- Added local global-IPv6 detection without depending on an external IP-discovery HTTP service.
- IPv6 literals are formatted safely in URI authorities with brackets.
- Xray public listeners use dual-stack listening when public IPv6 is available while the panel backend remains local.
- System UI reports IPv4, IPv6 and Dual Stack state explicitly.
- IPv6 absence remains non-fatal and preserves the IPv4-only contract.

### AWG2

- Existing IPv4 tunnel allocation is preserved.
- Dual-stack servers add a deterministic RFC4193 IPv6 /64 dedicated to AWG2.
- Client addresses become IPv4 + IPv6 when dual stack is available.
- Server peer routes use the existing IPv4 host route plus an IPv6 /128.
- Client default AllowedIPs include both IPv4 and IPv6 default routes.

### AWG3 userspace

- AWG3 is isolated from the AWG2 kernel/runtime line and uses its own vendored 3.x userspace runtime.
- H1-H4/runtime generation is independent from the AWG2 namespace.
- AWG3 gains its own deterministic RFC4193 IPv6 /64, separate from AWG2.
- The userspace helper parses and applies comma-separated IPv4/IPv6 interface addresses with the correct address family.
- The release manifest lists `sg-gateway-awg3` as a first-class service.
- Full uninstall stops/removes the AWG3 service, interface, userspace socket and associated SG runtime state.

## WARP

- Clean install no longer automatically registers/creates a WARP profile. The helper is installed, and WARP is created manually from Outbounds when needed.
- Existing WARP state is preserved on update.
- One WARP WireGuard core is used; IPv4 and IPv6 are family gates rather than separate WARP accounts.
- WARP keeps its proven IPv4 peer endpoint while carrying both IPv4 and IPv6 payload traffic.
- Profile support is tracked separately from live health.
- IPv4 and IPv6 are tested independently through Cloudflare trace.
- Routing capability is gated by the latest family-specific WARP health result: a failed IPv6 test disables only WARP IPv6, and vice versa.
- No silent WARP-to-direct fallback is allowed.

### Live WARP acceptance already performed

- WARP IPv4: OK (`warp=on`).
- WARP IPv6: OK (`warp=on`).
- The live profile contains both an IPv4 and an IPv6 interface address and both default address families in AllowedIPs.

## Family Routing

Routing exposes five explicit actions:

1. `SG-Gateway · IPv4`
2. `SG-Gateway · IPv6`
3. `WARP · IPv4`
4. `WARP · IPv6`
5. `Заблокировать`

- IPv4 and IPv6 never silently fall back to each other.
- Direct IPv4/IPv6 use explicit Xray family strategies.
- WARP IPv4/IPv6 use family gates in front of the shared WARP core.
- Legacy saved `direct` and `warp` actions migrate to IPv4 behavior so an upgrade cannot unexpectedly expose IPv6.
- The final catch-all rule is family-explicit.
- Fixed the missing `Заблокировать` action in “Остальной трафик”.
- Fixed the backend bug that silently rewrote `default_action=block` to `direct4`; Block is now a real fail-closed catch-all.
- LAN remains intentionally limited to SG-Gateway IPv4/IPv6 or Block rather than WARP.

## Non-destructive updater

- Preserves virtual environment, assets and AWG3 runtime instead of replacing the whole application tree blindly.
- Preserves SG TLS certificate material and current HTTPS state.
- Preserves AWG3 configuration/unit/runtime material and validates state across update.
- Safety backup captures service/runtime state required for rollback.
- Safety Backup now checks required disk space before stopping panel/HostD and refuses safely when free space is insufficient.
- Incomplete Safety Backup directories are removed automatically after failed archive creation; successful update backups keep a bounded history (two by default) instead of accumulating indefinitely.
- Safety Backup archive paths are de-duplicated so protected runtime paths already covered by a parent tree are not archived twice.
- Rollback restores protected runtime material rather than only application source.
- Removed blanket ownership rewriting of the whole prefix.
- Added final verification for clients, HTTPS/TLS state, AWG3 state and previously active services.
- Fixed validation against a protected runtime env by using a private temporary env copy rather than weakening permissions.
- Live update acceptance confirmed TLS/Nginx/AWG3 runtime/VPN cores remained untouched.

## SG subscription and client access pipeline

- Added the **SG subscription** schema/store and HTTP compatibility pipeline.
- Added per-device subscription generation and QR support.
- Added Base64-body and compatibility-text handling.
- Added independent per-device access state and device credentials.
- Added dual AWG generation exposure in client UX.
- Preserved legacy client credentials through migration/rollback paths.
- Simplified client/device presentation while keeping technical exports per device.

## Hysteria2 Gecko / Salamander cleanup

- **Hysteria2 Gecko** ships with explicit Off / Salamander / Gecko behavior.
- Gecko uses the proven Xray Salamander FinalMask primitive with managed `packetSize=512-1200`.
- Added safe managed-state marker handling so live managed FinalMask is not rediscovered as unmanaged base state.
- Added migration for the first 022.04 Gecko representation.
- Cleaned exported Hysteria2 URI semantics: no artificial `alpn=h3` is added to the client URI.
- Server-side TLS ALPN remains independent from client URI cleanup.
- Pinned Xray 26.6.27 is retained; no core replacement was required merely to enable Gecko.

## XHTTP / XMUX

- Added managed **XMUX** presets and expert mode for XHTTP client exports.
- Standard preset matches the accepted SG-Panel contract.
- Added reduced preset with conflict validation.
- Reality XHTTP client export is normalized to `stream-one`.
- Client `extra` data is preserved while managed XMUX values are added.
- XMUX is never injected into the server XHTTP inbound.
- TLS XHTTP keeps its independent client mode.
- Old fixed-RF presentation is hidden in favor of the explicit XMUX selector.
- The compact XMUX selector no longer keeps a permanent protocol-contract row on screen; pressing a mode opens a parameter dialog with the exact preset values before save.

## Full Backup / restore

- Expanded portable full-backup runtime and verification.
- Added restore-compatible archive validation before acceptance.
- Added safety backup before restore and runtime/certificate verification before success.
- Increased backup upload handling for large archives.
- Added UI/layout fixes for the full-backup flow.

## Panel update and runtime preservation

- Added the V22 panel update channel/state binding.
- Panel-only update uses staging, code backup and automatic rollback.
- Requirements changes block an unsafe panel-only update path.
- Existing runtime assets/cores/state are preserved rather than silently replaced.
- Working Xray/Mihomo state is preserved through supported update paths.

## Production runtime

- Added the production WSGI entrypoint and production systemd launch contract.
- Added clean-install production-entrypoint tests.
- Health handling distinguishes panel liveness from optional runtime availability.

## UI and usability fixes

- Added independent AWG2/AWG3 selection in client/device UI.
- Made the AWG3 connection card visually match AWG2.
- Reduced the three VLESS parameter cards to one equal compact height; Reality TCP and XHTTP Reality keep only the TCP port, while XHTTP TLS keeps client mode and TCP port aligned on the same row.
- Removed editable XHTTP Path fields from the visible controls because they are fixed protocol metadata.
- Restored the accepted dark blue-glass Connections hierarchy without changing the light theme or page geometry.
- Simplified Hysteria 2 Obfuscation controls and removed the internal divider while leaving Off/Salamander/Gecko runtime behavior unchanged.
- Replaced the XMUX selector's passive rows with visible preset buttons and an exact-values dialog; XMUX remains client-only and never enters the server inbound.
- Added compact device presentation and collapse behavior.
- Removed duplicate/empty client UI blocks and retained one clear creation flow.
- Unified readable typography across current panel pages.
- Preserved dark Graphite and light Luxury Jade themes.
- Removed native browser confirmation dialogs in favor of internal confirmation UI.
- Fixed Xray status-card theming and accumulated Connections/System visual regressions.

### Low-resolution desktop support

- Added a source-native **Low-resolution** layer for desktop screens up to 1366px wide or 820px high.
- Added a separate 761–980px compact layout.
- Controls, spacing, sidebar and dialogs compact without hiding actions.
- Routing stacks rule columns at narrower widths and action segments vertically on mobile widths.
- Regression coverage explicitly rejects `display:none` in the low-resolution layer.

## GeoFiles / Routing safety accumulated in V22

- GeoIP + GeoSite remain paired and candidate-tested before live replacement.
- Managed Routing is tested against the future complete Xray candidate before apply.
- Apply/rollback remains atomic and user rules are preserved.
- GeoFiles family transitions and category compatibility are validated before activation.

## Installer and diagnostics hardening

- Clean-install database seed and application-import/render contracts are tested.
- Optional runtimes do not turn the whole install into a false failure.
- Installer output was consolidated around one progress/error path with safer diagnostic summaries.
- Runtime failures preserve useful exact diagnostics while avoiding accidental secret output.
- Existing SG admin and connection identity state is preserved across supported migration/update paths.

## Final Fix30 validation

The final Fix30 tree is validated against the complete 022.04 contract:

- the pre-versioning milestone remains recorded as **551 passed**, 1 skipped;
- source integrity covers every tracked release file;
- Python syntax covers the complete application and test tree;
- pytest: **569 passed**, 1 skipped in the restricted build container; the single unavailable system-permission probe requires real `runuser` group switching, which the container blocks before the tested command starts;
- family-routing regression suite: 15/15;
- default-traffic Block regression suite: 2/2;
- FULL package and embedded-manifest verification are mandatory publication gates for the release artifact.

## Live acceptance already completed

- panel and HostD active after non-destructive update;
- native public IPv4 egress works;
- native public IPv6 egress works;
- public IPv4/IPv6 metadata is persisted;
- WARP IPv4 health succeeds with `warp=on`;
- WARP IPv6 health succeeds with `warp=on`;
- Routing UI exposes family-specific actions;
- low-resolution Routing layout was manually checked.

AWG2/AWG3 IPv6 generation is covered by source/runtime tests; this document does **not** claim separate real-client AWG2/AWG3 IPv6 traffic acceptance that has not been performed.

## Known boundary of 022.04

- IPv6-only VPS operation is deferred; 022.04 is IPv4-compatible Dual Stack.
- The branch remains DEV/draft until final publication gates are explicitly closed.
