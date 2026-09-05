# SG-Gateway UI Layout Standard — Design

Date: 2026-09-05
Target line: 0.1.0-022.07
Base: `dev-02207@ba380f5b281105352cd0911db9c80678ae234b28`

## Problem

SG-Gateway already has shared tokens (`--sgui-*`) for page spacing, radii, controls and typography, but page geometry is still owned by page-specific selectors and accumulated override layers. On Connections this produced repeated regressions: Xray, XMUX, AWG, Mihomo/sing-box and NaiveProxy used different structural levels for the same visual concept, so matching numeric padding values did not produce matching visual rails.

The same pattern exists elsewhere: Clients, Routing, Security, System and Maintenance each use their own class families and multiple page-specific CSS layers. The immediate goal is not to redesign every page in one change. The goal is to establish one reusable layout contract on Connections, prove it visually, then adopt it page-by-page.

## Decision

Introduce semantic layout primitives that own geometry, while preserving existing component classes, behavior and theme ownership.

Canonical primitives:

- `.sg-ui-page` — page rhythm only.
- `.sg-ui-page-head` — common page heading geometry.
- `.sg-ui-section` — one full-width major surface.
- `.sg-ui-section-head` — shared section header geometry.
- `.sg-ui-rail` — the one canonical inner horizontal working rail.
- `.sg-ui-nested` — nested surface geometry inside a rail.
- `.sg-ui-actions` — shared action-row alignment and spacing.
- `.sg-ui-section--compact` — allowed only for intentionally short sections such as NaiveProxy; it changes vertical density, not horizontal geometry.

These primitives will reuse the existing global tokens rather than introduce per-component pixel values.

## Canonical geometry

Desktop:

```text
PAGE CONTENT
|--------------------------------------------------------------|

MAJOR SECTION (.sg-ui-section)
|--------------------------------------------------------------|
|  SECTION HEADER (.sg-ui-section-head)                        |
|                                                              |
|    INNER WORKING RAIL (.sg-ui-rail)                          |
|    |----------------------------------------------------|    |
|    | component content / nested surfaces / action rows |    |
|    |----------------------------------------------------|    |
|                                                              |
|--------------------------------------------------------------|
```

Rules:

1. Every major section occupies the same outer width.
2. Every major section has exactly one canonical inner rail.
3. Component-specific CSS may style content inside the rail, but must not redefine the rail's left/right position.
4. A component may contain nested cards, but nested cards inherit the rail width unless their own internal grid explicitly subdivides it.
5. Header, body and action rows align to the same rail unless the header is intentionally full-bleed inside the section.
6. Horizontal geometry is token-driven. No page-specific `calc()` or extra `margin-inline` may compensate for a different component structure.
7. Mobile reduces the canonical rail inset using the existing nested-padding token; it does not create a separate component-specific mobile geometry.

## Connections adoption

Connections is the first and reference implementation.

### Xray

- Keep existing form, profile cards, Reality fields and actions.
- Major Xray surface becomes `.sg-ui-section`.
- Endpoint, profile selection, parameters and bottom action surface all sit on `.sg-ui-rail`.
- The bottom Xray action surface defines no private horizontal geometry.

### XMUX

- Keep the card-in-card composition approved in screenshots.
- The outer XMUX section remains the same full major-section width as Xray/AWG/Mihomo.
- The inner XMUX card sits on the same `.sg-ui-rail` as Xray's internal action/parameter surfaces.
- XMUX-specific CSS owns only its tabs, JSON body and controls, not section/rail width.

### AmneziaWG

- Major AWG surface becomes `.sg-ui-section`.
- AWG three-card grid and shared DNS row sit on `.sg-ui-rail`.
- Internal endpoint cards may keep their internal card padding, but they do not create a second page-level rail.

### Mihomo / sing-box

- Major Mihomo surface becomes `.sg-ui-section`.
- HTTPS warning/ready surface, listener grid, actions and runtime note sit on the same `.sg-ui-rail`.
- The listener grid may subdivide the rail into three columns; the warning does not get a different horizontal inset.

### NaiveProxy

- Major NaiveProxy surface becomes `.sg-ui-section.sg-ui-section--compact`.
- Its content uses the same rail, but the section is allowed a smaller vertical height.
- Compactness must not change horizontal alignment.

## Scope boundaries

This design does not change:

- runtime behavior;
- POST endpoints;
- JavaScript behavior;
- protocol values or ports;
- database schema/data;
- client exports or subscriptions;
- theme palette;
- button/capsule style;
- existing editability rules for Xray Reality or other forms.

## Cross-page rollout

Connections establishes the reference implementation. Other pages are explicitly not rewritten in the same implementation PR.

After visual acceptance of Connections, perform a separate page-by-page audit and adoption sequence:

1. Clients / client detail
2. Routing / GeoFiles
3. Security
4. System
5. Maintenance
6. Outbounds
7. Recovery / Help

Each page adoption must preserve behavior and use the same semantic layout primitives. Existing page-specific CSS may remain for component internals, but duplicate page/section/rail geometry should be removed as each page migrates.

## Current debt observed outside Connections

- Clients combines multiple generation-specific class families and several CSS layers/hotfixes.
- Routing owns a separate `r096-*` geometry system.
- Security mixes `secv2-*` and `ts2-*` geometry.
- System loads multiple successive system-specific layout override files in addition to the global UI layer.
- Maintenance loads multiple maintenance/update layout generations.
- `base.html` currently carries a broad stack of preview/fix layers, so global visual ownership is not always obvious.

This debt is why the rollout must be incremental rather than a single global rewrite.

## CSS ownership

Add one new global geometry layer, tentatively `sg-layout-contract-v1.css`, loaded after `sg-global-ui-system-v1.css` and before final page/theme-specific visual overrides.

Ownership order:

1. `sg-global-ui-system-v1.css` — tokens, shell, typography and shared control dimensions.
2. `sg-layout-contract-v1.css` — semantic page/section/rail/nested/action geometry.
3. page-specific CSS — component internals only.
4. theme-specific CSS — color/depth only; it must not move rails.

Connections-specific `sg-connections-unified-v1.css` should shrink toward component-only rules as semantic geometry moves into the layout contract.

## Tests

TDD requirements:

1. RED tests first for semantic class adoption on all five Connections sections.
2. Contract test: all major Connections sections share `.sg-ui-section`.
3. Contract test: Xray inner surfaces, XMUX inner card, AWG grid/DNS, Mihomo warning/listeners/actions and NaiveProxy content use the same `.sg-ui-rail` ownership.
4. Contract test: component CSS does not redefine section/rail `margin-inline` after migration.
5. Responsive test: mobile rail changes in one global rule, not per component.
6. Existing full suite remains green.
7. Browser acceptance in light and dark themes at desktop and narrow widths, including visual screenshots for Xray → XMUX, AWG, Mihomo and NaiveProxy.

## Acceptance criteria

Connections is accepted only when:

- all five major sections have the same outer width;
- all primary inner surfaces line up on the same left/right vertical rails;
- nested-card composition may vary, but no section appears to have a different page grid;
- no new component-specific horizontal offset hack is required;
- light and dark themes preserve the same geometry;
- mobile has no double inset;
- full automated test suite is green;
- runtime behavior is unchanged.

## Follow-up after Connections acceptance

Create a UI consistency inventory for the remaining pages and migrate them one by one to the same contract. Do not batch unrelated functional changes with layout adoption.
