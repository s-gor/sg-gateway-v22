# SG-Gateway 22.08 UI Architecture Design

Date: 2026-09-05
Status: design approved in chat; implementation not started
Base branch: `dev-02207`
Base commit: `c0da8491c638f94c7f22552050b74bd2354658bf`
Working branch: `feature/02208-ui-foundation`

## 1. Purpose

SG-Gateway 22.08 replaces the accumulated frontend geometry and CSS override stack with one explicit UI architecture. The change is architectural rather than cosmetic: one shell, one page geometry, one spacing/rail system, one semantic component vocabulary, one asset revision strategy, and page-specific CSS that is allowed to own only component internals.

The implementation must preserve runtime behavior and server semantics. 22.08 is not a protocol, backend, database, routing, permissions, provisioning, maintenance, or API rewrite.

The design is based on the accepted `dev-02207` state at commit `c0da8491c638f94c7f22552050b74bd2354658bf`. Draft PRs #140 and #141 are not part of the base and their code must not be copied automatically.

## 2. Goals

22.08 must achieve all of the following:

1. Replace historical page-generation namespaces as owners of global geometry.
2. Make the outer content rail identical across System, Clients, Client Detail, Connections, Routing, Security, Maintenance, Outbounds, Help, Operation Job, and other panel surfaces.
3. Make nested rails deterministic and semantic rather than the result of cumulative margins.
4. Separate foundation, layout, and components into explicit layers.
5. Remove legacy CSS after each migrated page is accepted; do not retain unused files as fallback.
6. Preserve HTML form semantics, backend routes, request methods, field names, important IDs, data attributes, and JavaScript hooks.
7. Use browser-computed geometry as the authoritative visual regression signal.
8. Use one automatic cache-busting strategy for frontend assets instead of handwritten per-file suffixes.
9. Preserve dark/light theme support.
10. Preserve Recovery as an operationally independent emergency surface while sharing safe tokens/components where practical.

## 3. Non-goals

22.08 does not:

- change VPN or proxy protocol behavior;
- change AWG, Xray, XMUX, Mihomo, NaiveProxy, WARP, routing, GeoFiles, backup, TLS, or subscription semantics;
- redesign information architecture or rename product concepts unless required to remove a legacy CSS namespace;
- introduce a frontend framework;
- replace Jinja server rendering;
- rewrite existing JavaScript behavior without a functional necessity;
- carry forward draft PR #140 or #141 as hidden dependencies;
- create `dev-02208` before the feature work is accepted.

## 4. Confirmed current-state problems

### 4.1 `base.html` owns too much

The accepted base loads shell/theme assets but also historical page/fix layers. It therefore acts as a global compatibility aggregator rather than a stable shell.

Examples include typography generations, preview/final patches, client hotfixes, Routing frame CSS, control fixes, and conditional page bundles. This creates cross-page coupling and makes stylesheet order part of the layout contract.

### 4.2 Multiple generations coexist inside individual pages

Examples in the accepted base:

- Clients uses `cv2`, `cv10`, `cv15`, and `cv35` classes simultaneously.
- Client Detail uses `dv16`, `cd10`, Devices v46, collapse v1, QR, and subscription-specific layers.
- Security mixes `secv2` and `ts2` structure.
- Maintenance mixes `mtv2`, `mtv31`, and `mtv32`.
- Routing is built around the isolated `r096` namespace.
- Outbounds is built around `ob49`.
- Help is built around `hlpv1`.
- System has its main `sv1` layer plus multiple later corrective files.

These names may remain temporarily as implementation hooks during one migration stage, but no migrated page may depend on them for global page geometry.

### 4.3 22.07 shared layout contract is a transitional layer

`sg-layout-contract-v1.css` introduced useful concepts such as page, card, head/body, nested, grid, and actions. However it is intentionally small and still coexists with page-owned geometry.

`sg-global-ui-system-v1.css` also unifies old generations through selectors such as `:is(.sv1-..., .cv2-..., .cnv1-..., ...)`. That direction is transitional. In 22.08 the semantic primitive must be the dependency of the page; the global layer must not enumerate page generations.

### 4.4 CSS delivery is inconsistent

Existing templates use a mixture of:

- no query key;
- `?v={{ app_version }}`;
- handwritten suffixes such as `-mobile-v1` or `-connections-unified-v1`;
- page-local stylesheet tags inside the content block.

This makes browser cache behavior part of manual release work. 22.08 requires one generated asset revision mechanism.

## 5. Architectural direction

The selected architecture is a semantic `sg-ui-*` system introduced once and adopted page by page.

The three primary CSS layers are:

```text
app/web/static/sg-ui-foundation-v22-08.css
app/web/static/sg-ui-layout-v22-08.css
app/web/static/sg-ui-components-v22-08.css
```

They have strict ownership boundaries.

### 5.1 Foundation ownership

`sg-ui-foundation-v22-08.css` owns:

- palette variables for dark/light themes;
- typography tokens;
- spacing scale;
- radius scale;
- shadow tokens;
- control dimensions;
- focus-ring tokens;
- semantic state colors;
- base box-sizing and typography inheritance where appropriate.

Foundation must not contain page selectors such as `.cv2-*`, `.cnv1-*`, `.sv1-*`, `.r096-*`, `.mtv*`, `.ob49-*`, `.hlpv1-*`, or any future page generation namespace.

### 5.2 Layout ownership

`sg-ui-layout-v22-08.css` is the only owner of global coordinates and structural rails:

- application shell;
- sidebar/main split;
- topbar geometry;
- content viewport padding;
- page width and page vertical rhythm;
- page header alignment;
- major section rails;
- card header/body rails;
- nested rails;
- grid gaps;
- action row alignment;
- responsive breakpoints for these structures.

Page/component CSS must not override page-level horizontal padding, major-section width, global shell columns, or canonical rail offsets.

### 5.3 Component ownership

`sg-ui-components-v22-08.css` owns reusable presentation and internal component geometry:

- buttons and icon buttons;
- inputs, selects, textareas;
- cards and nested cards;
- badges/capsules/status pills;
- notices;
- tabs;
- tables;
- modal shell;
- action bars;
- common empty/error/locked states.

Component-specific CSS files are allowed only when a component has genuinely unique internal structure. They may not own the page coordinate system.

## 6. Semantic UI API

The initial semantic vocabulary is intentionally small.

### 6.1 Page primitives

```text
.sg-ui-page
.sg-ui-page-head
.sg-ui-page-head-copy
.sg-ui-page-actions
.sg-ui-kicker
.sg-ui-title
.sg-ui-subtitle
```

`sg-ui-page` has no additional horizontal margin or padding beyond the global content viewport. The outer horizontal rail exists exactly once.

### 6.2 Section/card primitives

```text
.sg-ui-section
.sg-ui-section-head
.sg-ui-section-body
.sg-ui-card
.sg-ui-card-head
.sg-ui-card-body
.sg-ui-nested
```

Major sections occupy the full available page rail unless their semantic component explicitly defines a narrower content measure. That narrowing must be component-local, not a page-generation override.

### 6.3 Rail/grid primitives

```text
.sg-ui-rail
.sg-ui-rail-deep
.sg-ui-grid
.sg-ui-grid-2
.sg-ui-grid-3
.sg-ui-grid-4
.sg-ui-actions
.sg-ui-actions-start
.sg-ui-actions-between
```

The rail classes represent semantic inset levels, not arbitrary historical pixel values. A nested control group aligns because it uses the same rail primitive, not because unrelated margins happen to add to the same number.

### 6.4 State/component primitives

```text
.sg-ui-button
.sg-ui-button-primary
.sg-ui-button-danger
.sg-ui-control
.sg-ui-badge
.sg-ui-status
.sg-ui-notice
.sg-ui-tabs
.sg-ui-table
.sg-ui-modal
```

Existing `.button` and other legacy component classes may be bridged temporarily during migration, but the final 22.08 state must have one canonical component owner.

## 7. Rail contract

This is the central geometry rule for 22.08.

### 7.1 Outer rail

The shell defines the main content viewport. The content viewport applies the canonical page inset once. `.sg-ui-page` fills that viewport and does not add a second horizontal inset.

### 7.2 Major sections

A major section fills the page rail. Its border/background may span the full rail.

### 7.3 Section internal rail

A major section uses exactly one canonical internal rail for headings, controls, nested cards, grids, and action groups unless a component explicitly opts into the deep rail.

### 7.4 Deep rail

The deep rail exists for cases where two semantic containment levels are visually intended. It is not implemented as arithmetic knowledge in page CSS. The primitive itself owns the depth.

### 7.5 XMUX/Xray implication

Xray controls and XMUX controls that are intended to share a visual coordinate must use the same semantic rail primitive. No rule may encode the relationship as `first margin + second margin` or reproduce a page-specific cumulative inset calculation.

### 7.6 Mobile

At mobile widths the layout layer changes canonical rail tokens once. Individual pages do not carry separate zero-margin overrides solely to compensate for desktop page-generation CSS.

## 8. Shell and template loading model

### 8.1 `base.html`

The final `base.html` should load:

1. theme initialization script;
2. canonical foundation;
3. canonical shell/layout;
4. canonical components;
5. a page-assets block for page/component-specific assets;
6. canonical responsive support if not already inside layout/components.

It must not globally load Clients, Connections, Routing, System, Maintenance, Security, Outbounds, or Help visual patches.

### 8.2 Page asset blocks

Each page may request only assets that are needed for unique component behavior. Page assets must be explicit and cache-busted through the common helper/revision.

### 8.3 No stylesheet tags inside content

Stylesheet tags inside `{% block content %}` are prohibited in migrated templates. Assets belong in the head/page-assets block.

## 9. Asset revision strategy

22.08 introduces one frontend asset revision value.

Conceptually:

```text
/static/<asset>?v=<asset_revision>
```

Requirements:

1. `asset_revision` is generated automatically from the accepted build/source state or an equivalent deterministic frontend fingerprint.
2. Templates do not contain handwritten per-file semantic suffixes.
3. The same revision is used consistently for the build.
4. Updating a frontend asset must change the delivered URL revision without requiring a developer to remember a manual suffix.
5. Tests must prove that a changed frontend asset cannot be served under an unchanged expected revision contract.

The implementation may use a build-level source revision rather than a separate hash per file. The important contract is deterministic automatic invalidation with no manual page-specific cache key.

## 10. Functional preservation contract

For every migrated template the implementation must snapshot and preserve all backend-facing behavior that matters.

At minimum compare before/after:

- form `action`;
- form `method`;
- input/select/textarea `name`;
- hidden values whose semantics are server-facing;
- important element `id` values referenced by JavaScript;
- `data-*` attributes used by JavaScript;
- submit button semantics;
- links to named routes;
- disabled/checked conditions driven by Jinja;
- modal triggers and confirmation attributes;
- polling/status endpoints embedded in markup.

Class names are not automatically part of the functional contract unless JavaScript explicitly depends on them. Where JavaScript depends on a visual class, migrate the hook to a stable `data-*` or semantic hook before deleting the legacy class, with a dedicated test.

## 11. Standalone surfaces

### 11.1 Recovery

Recovery remains a standalone document and must not depend on the full authenticated panel shell. This preserves emergency operability if the normal shell or panel route is impaired.

Recovery may load foundation tokens and a small shared component subset, plus a dedicated recovery component stylesheet if needed. It must not inherit page-specific panel CSS.

### 11.2 Login

Login also remains shell-independent. It should use foundation/components rather than historical theme/fix stacks. Its functional form contract must remain unchanged.

### 11.3 Operation Job

Operation Job remains within the authenticated shell but must migrate its page geometry to the same page/rail primitives. Its terminal component may keep dedicated internal CSS.

## 12. Migration and deletion matrix

Migration is sequential. A page is not considered migrated until its obsolete structural CSS is removed or proven still required for an explicitly documented component.

### Stage 0 — foundation

Create the canonical UI layers, asset revision mechanism, architecture tests, and browser geometry harness. Do not visually rewrite all pages in this stage.

Candidate legacy sources to mine, not preserve as permanent dependencies:

- `sg-panel-shell-v1.css`
- `sg-global-ui-system-v1.css`
- `sg-layout-contract-v1.css`
- typography generations
- shared control/final patches
- mobile/low-resolution compatibility rules

Stage 0 must not alter protocol/runtime behavior.

### Stage 1 — Connections

Migrate:

- `connections.html`
- Xray profile selection geometry
- XMUX panel geometry
- AWG panels
- Mihomo panel integration
- Connections heading/actions/sections

Primary legacy families to eliminate as global geometry owners:

- `cnv1-*`
- `xps2-*` structural rules
- Connections visual/unified/dark-classic structural overlap
- XMUX page-placement rules
- AWG/Mihomo outer-placement rules

Unique protocol component internals may survive only after being separated from page geometry.

Acceptance requires browser verification of Xray/XMUX cumulative alignment rather than a string-based margin assertion.

### Stage 2 — Clients and Client Detail

Migrate:

- `clients.html`
- `client_detail.html`
- client list/filter/header layout
- device cards
- protocol cards
- QR/subscription component placement
- client/device action groups

Eliminate page-generation ownership from:

- `cv2-*`
- `cv10-*`
- `cv15-*`
- `cv35-*`
- `dv16-*`
- `cd10-*`
- page-level portions of device collapse/device visual CSS
- global Clients hotfix layers

Remove duplicate stylesheet injection from the content block.

### Stage 3 — Routing and GeoFiles

Migrate `routing.html`, routing panels, user rule editor, tabs, and GeoFiles integration to canonical page/section/rail primitives.

`r096-*` may remain only as internal behavior hooks during migration; it must not own final page geometry.

### Stage 4 — Security

Migrate Security page geometry and reconcile the current `secv2`/`ts2` structural split.

Retain unique TLS/password component behavior, not separate page rails.

### Stage 5 — System

Migrate System summary, resource cards, controls, tables, resource visualizations, and responsive geometry.

Consolidate or remove the chain of corrective CSS files, including duplicated generations such as refresh-button fixes where only the accepted final behavior is required.

Resource dial/bar internals may remain as dedicated components.

### Stage 6 — Maintenance

Migrate Backups/Updates tabs, update cards, backup tables/actions, diagnostics and maintenance sections.

Remove `mtv2/mtv31/mtv32` generation layering as geometry ownership.

### Stage 7 — Outbounds

Migrate `ob49` page geometry, system outbound rows, WARP cards, and actions.

Unique outbound internals may remain component-specific.

### Stage 8 — Help, Recovery, Login, Operation Job

Migrate Help to canonical page primitives.

Migrate Recovery and Login to foundation/shared components while keeping them shell-independent.

Migrate Operation Job outer geometry; keep terminal internals isolated.

After this stage, run a full legacy inventory and delete any CSS/JS asset that is no longer referenced or required.

## 13. Legacy deletion policy

No legacy CSS file is retained "just in case".

For each migrated page:

1. migrate markup to semantic primitives;
2. pass functional contract tests;
3. pass focused browser geometry and visual checks;
4. determine which legacy rules remain reachable;
5. move any genuinely required component-internal rules into the new component owner;
6. remove the legacy stylesheet reference;
7. rerun functional/browser checks;
8. delete the unreferenced file;
9. regenerate repository source manifests/checksums required by project policy.

A legacy file may remain temporarily only when a later migration stage still actively references it. That dependency must be explicit in the migration inventory.

## 14. CSS ownership enforcement

Architecture tests must reject these classes of regression:

- a migrated page introducing page-level `padding-inline`, `margin-inline`, or width compensation outside the canonical layout layer;
- global CSS enumerating old page-generation namespaces to simulate shared layout;
- migrated templates loading legacy page visual/hotfix CSS;
- stylesheet tags inside the content block;
- duplicate generations of the same corrective stylesheet;
- handwritten asset cache suffixes on migrated assets;
- component CSS modifying `.sg-shell`, `.sg-content`, `.sg-ui-page`, or other global coordinate owners;
- use of arbitrary cumulative margins to align sibling components that should share a semantic rail.

## 15. Browser geometry tests

String inspection remains useful for architecture rules but is not sufficient for rendered geometry.

The browser harness must measure real DOM boxes with `getBoundingClientRect()`.

### 15.1 Cross-page outer rail

At representative desktop width, verify that the principal page container for each migrated page shares the same left and right coordinates within a 1 CSS pixel tolerance.

### 15.2 Header rail

Verify title/kicker/header actions align to the canonical page rail.

### 15.3 Major section rail

Verify representative major cards begin/end on the canonical page rail.

### 15.4 Inner rail

Verify representative content elements across Xray, XMUX, Clients, Routing, System, and Maintenance share the documented semantic inset when they use the same rail primitive.

### 15.5 Responsive geometry

Run at minimum:

- standard desktop;
- narrow desktop/tablet;
- mobile.

The mobile test checks that canonical tokens change centrally and that migrated pages do not compensate with page-specific offset overrides.

## 16. Visual regression acceptance

For each migration stage produce dark and light screenshots for representative desktop and mobile/narrow layouts.

Screenshot review is an acceptance gate for geometry and visual preservation, not merely an artifact.

The implementation must preserve accepted information hierarchy and component meaning. Minor visual normalization caused by the shared geometry is expected; protocol/runtime meaning must not change.

## 17. Test strategy

### 17.1 Before migration

Add or update functional-contract tests for the page being migrated.

### 17.2 During migration

Use focused tests for:

- template render/contract;
- CSS ownership rules;
- JS selectors/hooks affected by markup changes;
- asset revision behavior;
- browser geometry.

### 17.3 Stage acceptance

A stage is accepted only when:

- focused tests pass;
- rendered browser geometry passes;
- dark/light screenshots are reviewed;
- obsolete stylesheet references are removed;
- obsolete files are deleted where no later page needs them;
- no backend/runtime contract changed unintentionally.

### 17.4 Final acceptance

Before integration:

- full pytest suite;
- compile/static checks already required by the repository;
- browser geometry suite across all migrated pages;
- dark/light screenshot set;
- legacy asset/reference inventory with no unexplained survivors;
- source checksum/manifest verification;
- diff review specifically for route/method/name/id/data-hook preservation.

## 18. Branch and integration workflow

1. `feature/02208-ui-foundation` starts exactly at `c0da8491c638f94c7f22552050b74bd2354658bf`.
2. Stage 0 and Stage 1 are implemented and reviewed before broad migration.
3. Later stage branches may be created from the latest accepted 22.08 feature integration point if isolation is useful.
4. Draft PR #140 and #141 are not merged or cherry-picked into 22.08 as prerequisites.
5. `dev-02207` remains unchanged by feature implementation.
6. `dev-02208` is created only after the complete 22.08 feature set and final verification are accepted.

## 19. Risks and mitigations

### Risk: hidden JavaScript dependency on legacy classes

Mitigation: inventory selectors before each template migration; preserve behavior hooks via stable IDs/data attributes; add focused JS/template tests before deleting classes.

### Risk: visual regressions masked by string tests

Mitigation: real browser coordinate checks plus screenshots are required acceptance evidence.

### Risk: one giant CSS replacement becomes unreviewable

Mitigation: migrate page by page; foundation stays small and semantic; component CSS remains bounded.

### Risk: temporary compatibility becomes permanent

Mitigation: each stage has a deletion gate. A migrated page cannot be accepted while its obsolete structural stylesheet remains loaded without a documented active dependency.

### Risk: cache hides a correct CSS change

Mitigation: deterministic common asset revision and a regression test that ties changed frontend state to the delivered revision contract.

### Risk: Recovery becomes dependent on the normal panel

Mitigation: keep Recovery standalone; share only static tokens/components that do not require authenticated-shell rendering.

## 20. Stage 0 acceptance criteria

Stage 0 is complete when:

1. the three canonical 22.08 CSS layers exist;
2. their ownership boundaries are encoded by tests;
3. base template loading has a clear canonical order;
4. asset revision generation is automatic and tested;
5. browser geometry test infrastructure can render and measure at least one existing page without altering protocol/runtime semantics;
6. no page migration is falsely claimed merely because the new files are present.

## 21. Stage 1 acceptance criteria

Connections is the proof page for the architecture.

Stage 1 is complete when:

1. Connections outer geometry is owned by `sg-ui-*` primitives;
2. Xray/XMUX/AWG/Mihomo major sections use canonical rails;
3. Xray and XMUX alignment is verified using computed browser coordinates;
4. mobile alignment uses central layout tokens rather than Connections-specific compensation;
5. existing Connections forms/routes/names/IDs/data hooks remain functionally equivalent;
6. obsolete Connections structural CSS is removed from template loading and deleted if unreferenced;
7. dark/light desktop/mobile screenshots are accepted;
8. focused tests and the relevant repository regression tests pass.

## 22. Definition of done for 22.08

22.08 is complete only when the frontend no longer depends on a chain of historical page-layout overrides.

The final system has:

- one canonical shell;
- one canonical page rail;
- semantic section/card/nested/action primitives;
- deterministic responsive geometry;
- common reusable components;
- one automatic asset revision strategy;
- no unexplained legacy visual/hotfix stylesheet survivors;
- browser-based geometry regression coverage;
- preserved server/runtime semantics.

The architectural success criterion is not "the pages still look correct after another override". It is that a future layout change can be made in the semantic owner without understanding the historical `cv*`, `cnv*`, `r096`, `sv1`, `mtv*`, `ob49`, or similar generations.