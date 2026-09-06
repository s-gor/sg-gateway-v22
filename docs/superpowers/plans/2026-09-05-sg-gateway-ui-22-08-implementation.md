# SG-Gateway 22.08 UI Architecture Implementation Plan

> For Codex: REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the accumulated SG-Gateway frontend geometry/CSS override stack with the approved semantic `sg-ui-*` architecture while preserving all backend, protocol, form, route, permission, and JavaScript behavior.

**Architecture:** Introduce three canonical shared layers (`foundation`, `layout`, `components`), one automatic frontend asset revision mechanism, and one browser-computed geometry gate. Migrate pages sequentially. A migrated page must stop depending on its historical namespace for global geometry, and obsolete CSS is physically deleted after usage and browser verification.

**Tech Stack:** Python 3.11+/3.12 CI, Flask/Jinja, CSS, existing vanilla JavaScript, pytest, Python Playwright + Chromium for browser geometry checks, GitHub Actions, existing FULL package verifier.

---

## 0. Non-negotiable execution rules

- Work only on `feature/02208-ui-foundation` until the complete feature is reviewed and accepted.
- The branch started from `c0da8491c638f94c7f22552050b74bd2354658bf`; do not merge/cherry-pick Draft PR #140 or #141.
- `dev-02207` remains untouched during implementation.
- Do not create `dev-02208` during this plan.
- Every behavior change must be test-first. For pure CSS/markup migration, the RED test is either the semantic architecture test, preserved HTML contract test, or browser geometry test that the current implementation fails.
- Never weaken an existing behavioral test merely because its selector/class changes. Replace presentation-string assertions only when an equivalent or stronger semantic/browser assertion is added first.
- Never leave a migrated page depending on both new canonical page geometry and an old page-generation geometry override.
- Do not preserve a legacy stylesheet as fallback after its last real reference disappears.
- Do not change AWG/Xray/XMUX/Mihomo/NaiveProxy/WARP/Routing/GeoFiles/Backup/TLS/subscription/runtime semantics.
- Preserve form `action`, `method`, field `name`, server-facing values, significant `id`, JS `data-*` hooks, route names, submit semantics, Jinja enabled/disabled conditions, polling endpoints, and confirmation attributes.
- At each stage, dark and light themes must use the same geometry.
- Browser geometry is authoritative. String inspection of CSS may enforce ownership rules, but must not be used as proof that two rendered rails align.

## 1. Repository baseline and source-integrity preflight

### Task 1.1 — Normalize documentation checksums before implementation

**Files:**
- Modify: `SOURCE-SHA256SUMS`
- Existing docs already on branch:
  - `docs/superpowers/specs/2026-09-05-sg-gateway-ui-22-08-design.md`
  - `docs/superpowers/plans/2026-09-05-sg-gateway-ui-22-08-implementation.md`

The current CI verifies every tracked file in `HEAD` against `SOURCE-SHA256SUMS` before installing dependencies. The two approved planning documents therefore need to enter the checksum inventory before using CI as a clean baseline.

**Step 1: Confirm the exact starting ancestry**

```bash
git switch feature/02208-ui-foundation
git status --short
git rev-parse HEAD
git merge-base --is-ancestor c0da8491c638f94c7f22552050b74bd2354658bf HEAD
```

Expected: clean worktree; HEAD is the implementation-plan commit or its direct descendant; ancestry command exits 0.

**Step 2: Regenerate the checksum inventory from the staged index**

Use the index, not arbitrary filesystem reads, so the resulting hashes match the CI `git show HEAD:<path>` contract after commit:

```bash
git add -A
python3 -B - <<'PY'
import hashlib
import subprocess
from pathlib import Path

tracked = subprocess.check_output(
    ["git", "ls-files"], text=True, encoding="utf-8"
).splitlines()
tracked = sorted(path for path in tracked if path != "SOURCE-SHA256SUMS")
rows = []
for path in tracked:
    data = subprocess.check_output(["git", "show", f":{path}"])
    rows.append(f"{hashlib.sha256(data).hexdigest()}  {path}")
Path("SOURCE-SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")
PY
git add SOURCE-SHA256SUMS
```

**Step 3: Commit checksum normalization**

```bash
git commit -m "chore: refresh source integrity for 22.08 docs"
```

**Step 4: Run the exact source-integrity logic used by CI**

Copy/run the `Verify FINAL source integrity` Python block from `.github/workflows/ci.yml` unchanged.

Expected: `Git-blob source integrity ok: ... tracked files verified`.

### Task 1.2 — Establish a factual baseline

**Files:** none.

Run:

```bash
python -m pip install -r requirements-dev.txt
python -B -c "from pathlib import Path; files=list(Path('app').rglob('*.py'))+list(Path('engines').rglob('*.py'))+list(Path('tests').rglob('*.py')); [compile(p.read_text(encoding='utf-8'), str(p), 'exec') for p in files]; print(f'syntax ok: {len(files)} files')"
python -m pytest tests
VERSION="$(tr -d '[:space:]' < VERSION)"
OUT="/tmp/SG-Gateway-${VERSION}-FULL.run"
bash build-run.sh "$OUT"
bash "$OUT" --verify-only
```

Record exact pass/fail counts. Do not repair unrelated baseline failures inside 22.08 without first separating them from this project.

---

## 2. Stage 0 — Functional contract test infrastructure

### Task 2.1 — Add a rendered-HTML contract extractor

**Files:**
- Create: `tests/ui/__init__.py`
- Create: `tests/ui/html_contract.py`
- Create: `tests/test_sg_gateway_v22_ui_function_contract_02208.py`

Do not add BeautifulSoup solely for this. Use `html.parser.HTMLParser` so the contract helper stays dependency-free.

**RED:** create tests that define the contract shape for at least Connections, Clients, Client Detail, Routing, Security, System, Maintenance, Outbounds, Help, Recovery, Login, and Operation Job.

The helper should normalize only backend-relevant attributes, for example:

```python
@dataclass(frozen=True)
class FormContract:
    action: str
    method: str
    field_names: tuple[str, ...]
    ids: tuple[str, ...]
    data_hooks: tuple[tuple[str, str], ...]

class ContractParser(HTMLParser):
    ...
```

Tests should compare stable contract fixtures/snapshots checked into Python data, not raw HTML byte-for-byte. Do not include CSS classes unless JavaScript actually consumes them.

**Run RED:** 

```bash
python -m pytest tests/test_sg_gateway_v22_ui_function_contract_02208.py -q
```

Expected: fail because helper/fixtures are not yet complete.

**GREEN:** implement the extractor and current accepted contracts without touching templates.

**Run GREEN:** same command; expected all pass.

**Commit:**

```bash
git add tests/ui tests/test_sg_gateway_v22_ui_function_contract_02208.py
git commit -m "test: capture 22.08 frontend behavior contracts"
```

Then refresh `SOURCE-SHA256SUMS` with the staged-index command before the next gate commit.

### Task 2.2 — Add architecture ownership tests

**Files:**
- Create: `tests/test_sg_gateway_v22_ui_architecture_02208.py`

Tests must encode the destination architecture before CSS exists.

Required RED assertions:

1. canonical files exist:
   - `sg-ui-foundation-v22-08.css`
   - `sg-ui-layout-v22-08.css`
   - `sg-ui-components-v22-08.css`
2. foundation/layout/components do not contain legacy page namespaces (`cv2`, `cv10`, `cv15`, `cv35`, `cnv1`, `sv1`, `r096`, `secv2`, `ts2`, `mtv2`, `mtv31`, `mtv32`, `ob49`, `hlpv1`, `dv16`, `cd10`).
3. canonical layout defines `.sg-ui-page`, `.sg-ui-page-head`, `.sg-ui-section`, `.sg-ui-rail`, `.sg-ui-rail-deep`, `.sg-ui-grid`, `.sg-ui-actions`.
4. `.sg-ui-page` does not establish a second horizontal page inset.
5. migrated templates may not include `<link rel="stylesheet">` inside `{% block content %}`.
6. no new page-specific stylesheet may set shell grid columns or canonical content horizontal padding.
7. migrated page assets use the common asset helper.

**Run RED:**

```bash
python -m pytest tests/test_sg_gateway_v22_ui_architecture_02208.py -q
```

Expected: failures for missing canonical files/helper.

Commit only after Tasks 3–5 make these initial requirements green.

---

## 3. Stage 0 — Automatic frontend asset revision

### Task 3.1 — Implement one deterministic revision source

**Files:**
- Create: `app/web/assets.py`
- Modify: `app/main.py`
- Create: `tests/test_sg_gateway_v22_ui_asset_revision_02208.py`

Keep this separate from `app/version.py`; product version and browser asset identity are different contracts.

Suggested implementation:

```python
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

STATIC_ROOT = Path(__file__).resolve().parent / "static"

@lru_cache(maxsize=1)
def frontend_asset_revision(static_root: Path = STATIC_ROOT) -> str:
    digest = sha256()
    for path in sorted(
        p for p in static_root.rglob("*")
        if p.is_file() and p.suffix.lower() in {".css", ".js"}
    ):
        rel = path.relative_to(static_root).as_posix().encode("utf-8")
        digest.update(rel)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]
```

Expose one Jinja helper from `create_app()` / existing template globals:

```python
def static_asset(filename: str) -> str:
    return url_for(
        "static",
        filename=filename,
        v=frontend_asset_revision(),
    )
```

**RED tests:**
- same content → same revision;
- changing one CSS/JS byte in a temporary static tree changes revision;
- ordering is deterministic;
- non-CSS/JS changes do not alter this frontend revision unless explicitly included by design;
- `static_asset("x.css")` contains exactly one `v=` query parameter;
- no handwritten suffix is required.

Run:

```bash
python -m pytest tests/test_sg_gateway_v22_ui_asset_revision_02208.py -q
```

**GREEN:** implement minimal helper/context integration.

Run the focused test and `python -m pytest tests/test_auth.py -q` to ensure application construction/auth still works.

**Commit:** `feat: add deterministic frontend asset revision`.

---

## 4. Stage 0 — Canonical foundation, layout, components

### Task 4.1 — Add the three canonical CSS layers

**Files:**
- Create: `app/web/static/sg-ui-foundation-v22-08.css`
- Create: `app/web/static/sg-ui-layout-v22-08.css`
- Create: `app/web/static/sg-ui-components-v22-08.css`
- Modify: `app/web/templates/base.html`
- Modify: `tests/test_sg_gateway_v22_ui_architecture_02208.py`

**Implementation boundaries:**

`foundation` owns tokens/base type/theme only. Mine accepted values from current shell/global files; do not invent a new visual direction.

`layout` owns only shell/page/section/rail/grid/action geometry. Initial token set should include semantic spacing/radius/control variables and these structural primitives:

```css
.sg-ui-page { min-width: 0; display: grid; gap: var(--sg-ui-page-gap); }
.sg-ui-page-head { ... }
.sg-ui-section { min-width: 0; }
.sg-ui-section-head { ... }
.sg-ui-section-body { ... }
.sg-ui-rail { ... }
.sg-ui-rail-deep { ... }
.sg-ui-grid { display: grid; gap: var(--sg-ui-grid-gap); }
.sg-ui-actions { display: flex; ... }
```

`components` owns controls/cards/status/tabs/tables/modals.

**Important:** at this stage the old CSS remains loaded because no page has migrated. The new layers are additive but must not attempt to override every old namespace.

`base.html` must load canonical files through `static_asset(...)` before page-specific legacy assets. Introduce/rename a Jinja block such as `{% block page_assets %}{% endblock %}` if needed, but preserve compatibility with current `{% block head %}` until pages migrate.

**RED/GREEN:** run architecture test until canonical ownership rules pass.

Then run:

```bash
python -m pytest tests/test_sg_gateway_v22_ui_architecture_02208.py tests/test_sg_gateway_v22_ui_asset_revision_02208.py tests/test_auth.py -q
```

**Commit:** `feat: establish 22.08 UI foundation`.

---

## 5. Stage 0 — Real-browser geometry harness

### Task 5.1 — Add Playwright as an isolated dev dependency

**Files:**
- Modify: `requirements-dev.txt`
- Modify: `pyproject.toml` dev optional dependencies
- Modify: `.github/workflows/ci.yml`
- Create: `tests/ui/browser_harness.py`
- Create: `tests/test_sg_gateway_v22_ui_browser_smoke_02208.py`

Use Python Playwright directly, without `pytest-playwright`.

Add compatible dependency constraint consistently to both dev dependency declarations, e.g. `playwright>=1.50,<2`.

CI after installing Python dependencies:

```yaml
- name: Install browser for UI geometry tests
  run: python -m playwright install --with-deps chromium
```

Do not replace the existing `python -m pytest tests`; browser tests remain normal pytest tests.

### Task 5.2 — Build an isolated live Flask fixture

`create_app()` already initializes the DB. The browser harness should set temporary environment values before constructing the app:

```python
SG_GATEWAY_DATA_DIR=<tmp>/data
SG_GATEWAY_LOG_DIR=<tmp>/logs
SG_GATEWAY_HOST=127.0.0.1
SG_GATEWAY_PUBLIC_ADDRESS=203.0.113.10
SG_GATEWAY_COUNTRY_CODE=fr
SG_GATEWAY_SECRET_KEY=test-secret
SG_GATEWAY_ADMIN_PASSWORD=admin
```

Serve the app with `werkzeug.serving.make_server("127.0.0.1", 0, app)` in a test-owned thread and always shut it down in `finally`.

Provide helper functions:

```python
def rect(page, selector: str) -> dict[str, float]:
    return page.locator(selector).evaluate(
        "el => { const r = el.getBoundingClientRect(); return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}; }"
    )

def assert_aligned(a, b, tolerance=1.0): ...
```

Login through the real login form for authenticated pages; do not bypass auth internals in browser tests.

### Task 5.3 — Add smoke gates

**RED first:** test Chromium can open Login and one authenticated page at `1440x1000` in dark and light themes.

Run before browser installation to prove dependency/setup failure, then install Chromium locally:

```bash
python -m playwright install chromium
python -m pytest tests/test_sg_gateway_v22_ui_browser_smoke_02208.py -q
```

Expected GREEN: page loads, no uncaught page errors, canonical stylesheet URLs contain one revision key.

**Commit:** `test: add real browser UI geometry harness`.

---

## 6. Stage 1 — Connections: functional contract before markup

### Task 6.1 — Freeze Connections behavior

**Files:**
- Modify: `tests/test_sg_gateway_v22_ui_function_contract_02208.py`
- Add focused browser test: `tests/test_sg_gateway_v22_connections_geometry_02208.py`

Before touching `connections.html`, ensure the contract includes all current forms/buttons/IDs/data hooks for:
- Xray profile apply/selection;
- XMUX settings;
- AWG2/AWG3/AWG3.1 settings;
- shared AWG DNS;
- Mihomo listeners/actions;
- NaiveProxy settings;
- navigation buttons.

Browser RED assertions at desktop/narrow/mobile and dark/light:
- Connections outer page rail equals canonical content rail;
- major Xray/AWG/Mihomo sections use same left/right page coordinates;
- intended Xray internal action rail and XMUX internal control rail have equal `left`/`right` within 1px;
- no horizontal overflow at 1440x1000, 1024x900, 390x844.

Current 22.07 should fail at least the semantic/new-selector assertion; do not fabricate a failing pixel assertion if current pixels happen to match.

### Task 6.2 — Migrate Connections outer geometry

**Files:**
- Modify: `app/web/templates/connections.html`
- Modify partials as needed:
  - `app/web/templates/_awg31_panel.html`
  - `app/web/templates/_mihomo_panel.html`
  - `app/web/templates/_xray_xmux_settings.html`
- Create: `app/web/static/sg-ui-connections-v22-08.css`
- Modify: `app/web/templates/base.html`

Convert outer structure to canonical primitives. Preserve legacy classes temporarily only where unique JS/component rules still need them.

Representative markup target:

```html
<section class="sg-ui-page" data-sg-ui-page="connections">
  <header class="sg-ui-page-head">...</header>
  <section class="sg-ui-section sg-ui-card" data-sg-section="xray">
    <div class="sg-ui-section-head sg-ui-rail">...</div>
    <div class="sg-ui-section-body sg-ui-rail">...</div>
  </section>
</section>
```

Use stable `data-sg-*` hooks for geometry tests rather than generation classes.

Move Connections-specific asset loading to the page asset block and use `static_asset()`.

### Task 6.3 — Separate unique component styling from structural legacy styling

Mine only component internals from:
- `sg-connections-visual-v1.css`
- `sg-connections-unified-v1.css`
- `sg-connections-dark-classic-v1.css`
- `sg-xray-profiles-v2.css`
- `sg-xmux-settings-v1.css`
- `sg-awg-dual-v1.css`
- `sg-mihomo-v1.css` / `sg-mihomo-v2.css` where Connections-specific
- `sg-compact-protocol-cards-v1.css` for NaiveProxy portions

Put retained Connections-only internals into `sg-ui-connections-v22-08.css`; reusable controls belong in `sg-ui-components-v22-08.css` instead.

Do not copy page-level margin hacks into the new file.

### Task 6.4 — Replace 22.07 CSS-string geometry tests

**Files:**
- Modify or retire after stronger coverage:
  - `tests/test_sg_gateway_v22_connections_final_grid_align.py`
  - `tests/test_sg_gateway_v22_connections_unified_ui.py`
  - other Connections visual-density tests that assert obsolete generation selectors.

Maintain useful semantic assertions (no palette in geometry layer, component coverage, etc.) but remove exact-margin assertions once the browser test proves actual coordinates.

Run:

```bash
python -m pytest \
  tests/test_sg_gateway_v22_ui_function_contract_02208.py \
  tests/test_sg_gateway_v22_ui_architecture_02208.py \
  tests/test_sg_gateway_v22_connections_geometry_02208.py \
  tests/test_sg_gateway_v22_connections_unified_ui.py \
  tests/test_sg_gateway_v22_connections_final_grid_align.py -q
```

### Task 6.5 — Delete obsolete Connections layers

Search before delete:

```bash
git grep -nE 'sg-connections-(visual|unified|dark-classic)-v1\.css|sg-xray-profiles-v2\.css|sg-xmux-settings-v1\.css|sg-awg-dual-v1\.css'
```

For each file: if only dead references/tests remain, delete it. If another page still consumes a component portion, split that portion first and document the surviving dependency.

After deletion rerun focused tests plus browser matrix.

**Commit sequence:**
1. `test: specify 22.08 Connections rails`
2. `refactor: migrate Connections to 22.08 UI rails`
3. `refactor: remove legacy Connections geometry`

Refresh `SOURCE-SHA256SUMS` before each gate commit that changes tracked files.

---

## 7. Stage 2 — Clients and Client Detail

### Task 7.1 — Freeze Clients/Client Detail behavior

Extend contract tests for:
- add/edit/delete client;
- enable/disable client;
- client apply;
- device add/edit/delete/enable/disable;
- protocol checkboxes and field names;
- QR/subscription controls;
- device collapse hooks;
- confirmation attributes.

Add `tests/test_sg_gateway_v22_clients_geometry_02208.py` comparing outer rail to Connections and canonical shell.

### Task 7.2 — Migrate markup and asset ownership

**Files:**
- Modify: `app/web/templates/clients.html`
- Modify: `app/web/templates/client_detail.html`
- Modify: `app/web/templates/_client_edit_dialogs.html`
- Modify: `app/web/templates/_sg_subscription_dual.html`
- Modify: `app/web/templates/_mihomo_client_actions.html` if used structurally
- Create: `app/web/static/sg-ui-clients-v22-08.css`
- Optionally create only if separation is real: `app/web/static/sg-ui-client-detail-v22-08.css`

Remove the stylesheet tag currently injected inside Clients content. All CSS belongs in the page asset block.

Replace outer `cv2/cv10/cv15/cv35/dv16/cd10` geometry with `sg-ui-*`. Keep a legacy class only while an existing JS/component selector still uses it.

Where JS depends on a purely visual class, first add a stable `data-*` hook and test it, update JS to use the hook, then remove the visual class.

### Task 7.3 — Consolidate/delete Clients legacy files

Inventory and reduce:
- `sg-clients-visual-v2.css`
- `sg-clients-runtime-v10.css`
- `sg-preview35-clients.css`
- `sg-clients-readable-small-v1.css`
- `sg-clients-simple-hotfix1.css`
- `sg-clients-clarity-hotfix2.css`
- `sg-client-detail-v10.css`
- `sg-devices-v46.css`
- page-level portions of device collapse CSS
- QR/subscription component CSS if reusable parts move to canonical components.

Device-collapse JavaScript behavior remains; only selectors are migrated when necessary.

Run contract + Clients browser tests + all existing clients/device/subscription tests.

**Commit sequence:** RED contract/geometry → migration → JS hook cleanup → legacy deletion.

---

## 8. Stage 3 — Routing and GeoFiles

### Task 8.1 — Freeze Routing/GeoFiles forms and JS hooks

**Files:**
- Extend functional contract tests
- Create: `tests/test_sg_gateway_v22_routing_geometry_02208.py`

Explicitly cover `r096-geofiles-form`, `source_id`, GeoFiles URLs/uploads/local path fields, Roscom options, `data-source-fields`, `data-source-info`, copy hooks, routing rule tabs/editors, preview/apply/rollback forms.

### Task 8.2 — Migrate Routing and included panels

**Files:**
- Modify: `app/web/templates/routing.html`
- Modify: `app/web/templates/_geofiles_panel.html`
- Modify: `app/web/templates/_routing_templates_panel.html`
- Create: `app/web/static/sg-ui-routing-v22-08.css`

`r096-*` may remain temporarily as behavior hooks, but no `r096` rule may own final page/content rails.

Migrate tabs to canonical tab components and forms/cards to section/rail primitives.

### Task 8.3 — Remove Routing frame ownership

Remove/decompose:
- `sg-routing-client096.css`
- `sg-routing-ux-fix2.css`
- `sg-routing-visual-v1.css`
- `sg-page-frame-routing-v1.css`
- shared GeoFiles geometry from `sg-geofiles-core-v1.css` after unique component pieces are moved.

Run all existing routing/geofiles tests plus browser matrix.

**Commit sequence:** `test: specify 22.08 Routing contract` → `refactor: migrate Routing to shared rails` → `refactor: remove legacy Routing geometry`.

---

## 9. Stage 4 — Security

### Task 9.1 — Freeze security behavior

Cover domain/TLS/password forms, certificate issue/renew/rollback, navigation links, confirmation hooks, operation-job redirects.

Create `tests/test_sg_gateway_v22_security_geometry_02208.py`.

### Task 9.2 — Migrate Security

**Files:**
- Modify: `app/web/templates/security.html`
- Create: `app/web/static/sg-ui-security-v22-08.css`

Reconcile the current `secv2` + `ts2` structural split into canonical page/header/card/rail primitives. Preserve TLS/password state rendering exactly.

### Task 9.3 — Delete old structural layers

Split any unique security internals, then remove obsolete `sg-security-v2.css` and `sg-security-password-fix1.css` when no longer referenced.

Run security/auth/TLS/operation job integration tests and browser matrix.

---

## 10. Stage 5 — System

### Task 10.1 — Freeze dashboard semantics

Cover diagnostics link, Maintenance link, resource state/status IDs/hooks, refresh actions, CPU/memory/disk JS targets.

Create `tests/test_sg_gateway_v22_system_geometry_02208.py`.

### Task 10.2 — Migrate System outer geometry

**Files:**
- Modify: `app/web/templates/system.html`
- Create: `app/web/static/sg-ui-system-v22-08.css`

Use canonical page, summary-grid, cards, section rails and actions. Keep charts/dials/bars as component internals.

### Task 10.3 — Consolidate the corrective CSS chain

Audit and migrate accepted final behavior from:
- `sg-system-visual-v1.css`
- `sg-system-top-bars-v2.css`
- `sg-system-light-theme-v3.css`
- `sg-system-simple-dials-v1.css`
- `sg-system-cpu-summary-header-v1.css`
- `sg-system-memory-row-bars-v1.css`
- `sg-system-memory-legend-divider-remove-v1.css`
- `sg-system-top-dividers-remove-v2.css`
- `sg-system-unified-free-color-v2.css`
- `sg-cpu-breakdown-v1.css`
- `sg-cpu-dial-layout-v3.css`
- `sg-disk-breakdown-v1.css`
- `sg-refresh-buttons-unify-v2.css`
- `sg-refresh-buttons-unify-v5.css`

Do not merge JavaScript behavior merely because CSS is consolidated. Existing JS files may remain if they still have real behavior.

Delete obsolete CSS generations after no references remain.

Run System/resource tests + browser matrix.

---

## 11. Stage 6 — Maintenance

### Task 11.1 — Freeze Maintenance behavior

Contract-test Backups/Updates tabs, create/delete/restore backup actions, diagnostics, panel/core/Xray update links/forms, upload/verify/restore paths, operation-job hooks.

Create `tests/test_sg_gateway_v22_maintenance_geometry_02208.py`.

### Task 11.2 — Migrate and consolidate

**Files:**
- Modify: `app/web/templates/maintenance.html`
- Create: `app/web/static/sg-ui-maintenance-v22-08.css`

Move `mtv2/mtv31/mtv32` geometry to canonical primitives. Preserve current tab semantics and all Jinja status conditions.

Audit/remove:
- `sg-maintenance-v2.css`
- `sg-maintenance-updates-v31.css`
- `sg-maintenance-updates-v32.css`
- `sg-maintenance-visual-v1.css`
- `sg-maintenance-typography-fix2.css`
- structural parts of `sg-full-backup-v1.css`

Keep `sg-maintenance-recovery-v1.js` if it still implements behavior; only migrate its selectors if necessary and test them.

Run maintenance/backup/update tests + browser matrix.

---

## 12. Stage 7 — Outbounds

### Task 12.1 — Freeze WARP/outbound behavior

Contract-test WARP create/apply/rollback/status and Help/Routing links.

Create `tests/test_sg_gateway_v22_outbounds_geometry_02208.py`.

### Task 12.2 — Migrate Outbounds

**Files:**
- Modify: `app/web/templates/outbounds.html`
- Create: `app/web/static/sg-ui-outbounds-v22-08.css`

Replace `ob49` outer page/card/action geometry with canonical primitives. Preserve unique WARP/outbound internals.

Delete `sg-outbounds-v49.css` after its remaining component internals have moved and no references remain.

Run WARP/routing/outbounds tests + browser matrix.

---

## 13. Stage 8 — Help, Recovery, Login, Operation Job

### Task 13.1 — Help

**Files:**
- Modify: `app/web/templates/help.html`
- Create: `app/web/static/sg-ui-help-v22-08.css`

Migrate `hlpv1` page geometry, keeping Help content/search behavior. Delete `sg-help-visual-v1.css` after component migration.

### Task 13.2 — Recovery and Login remain shell-independent

**Files:**
- Modify: `app/web/templates/recovery.html`
- Modify: `app/web/templates/login.html`
- Create: `app/web/static/sg-ui-standalone-v22-08.css`

Both pages should load `foundation` + shared components + standalone layout through `static_asset()`, but not authenticated sidebar/topbar shell CSS.

Recovery must remain operationally independent. Do not make its rendering depend on a healthy main dashboard route.

Preserve Login form action/fields and Recovery actions exactly.

### Task 13.3 — Operation Job

**Files:**
- Modify: `app/web/templates/operation_job.html`
- Create or replace with: `app/web/static/sg-ui-operation-job-v22-08.css`

Migrate outer page/header/actions to canonical primitives. Keep terminal/log/stepper internals isolated.

Run operation-job update/status/polling tests.

---

## 14. Final global cleanup — make `base.html` a real shell

### Task 14.1 — RED architecture test for final allowed global assets

Extend `tests/test_sg_gateway_v22_ui_architecture_02208.py` so final `base.html` is allowed to load globally only:
- theme initialization;
- canonical foundation;
- canonical layout/shell;
- canonical components;
- explicitly justified global behavior assets such as confirmation/modal JS if still universal;
- page asset block.

The test must fail while historical global CSS remains.

### Task 14.2 — Remove compatibility aggregation

**Files:**
- Modify: `app/web/templates/base.html`

Remove global page-specific/historical style references, including after verifying no live dependency:
- `sg-panel-shell-v1.css`
- `sg-global-ui-system-v1.css`
- `sg-layout-contract-v1.css`
- `sg-typography-v1.css`
- `sg-typography-v2.css`
- `sg-readable-typography-v3.css`
- `sg-technical-step2-v1.css`
- old preview final layers
- `sg-controls-final-v1.css`
- `sg-page-frame-routing-v1.css`
- global Clients hotfixes
- `sg-mobile-sidebar-v1.css`
- `sg-low-resolution-v1.css`
- any theme/depth legacy layer whose accepted tokens/components have already moved into canonical files.

Do not delete based only on filename. First prove the accepted final behavior has a canonical owner.

### Task 14.3 — Ban manual frontend cache suffixes

Add architecture test scanning Jinja templates for direct CSS/JS static URLs with handwritten `?v=` suffixes. All migrated frontend CSS/JS must route through `static_asset()`.

Icons/images may retain normal `url_for('static', ...)` if they do not need this CSS/JS revision contract; do not blindly rewrite binary image URLs.

### Task 14.4 — Delete dead static assets

Use repository reachability search:

```bash
for f in app/web/static/*.css app/web/static/*.js; do
  b="$(basename "$f")"
  if ! git grep -q -- "$b" -- ':!SOURCE-SHA256SUMS'; then
    printf 'UNREFERENCED %s\n' "$f"
  fi
done
```

Review every result manually because assets may be dynamically named. Delete only proven-dead files.

Add a static-asset reachability test for known direct template/JS references where feasible.

---

## 15. Cross-page browser acceptance matrix

### Task 15.1 — Add one final geometry matrix

**Files:**
- Create: `tests/test_sg_gateway_v22_ui_geometry_matrix_02208.py`

For authenticated shell pages, test these routes/surfaces:
- System
- Clients
- one Client Detail fixture
- Connections
- Routing
- Security
- Maintenance Backups
- Maintenance Updates
- Outbounds
- Help
- Operation Job fixture

Standalone separately:
- Login
- Recovery

Viewports:
- desktop: `1440x1000`
- narrow desktop/tablet: `1024x900`
- mobile: `390x844`

Themes:
- dark
- light

For every shell page assert:

```python
abs(page_rect["left"] - reference["left"]) <= 1.0
abs(page_rect["right"] - reference["right"]) <= 1.0
```

Also assert:
- document width does not exceed viewport width by more than 1px;
- page head/first major section follows canonical vertical rhythm;
- action groups wrap rather than overflow;
- sidebar/topbar geometry comes from canonical shell;
- switching dark/light does not change measured structural coordinates.

Do not assert exact text widths or font rendering pixels.

### Task 15.2 — Screenshot evidence

During browser matrix execution capture PNG screenshots for each page/theme at desktop and mobile into a temporary test artifact directory such as `/tmp/sg-ui-22-08-screenshots`.

Geometry assertions are CI-gating. Screenshots are review evidence and should be uploaded by CI as artifacts if the workflow supports it; do not make fragile full-page pixel equality the primary gate.

If adding artifact upload, use `actions/upload-artifact@v4` with `if: always()` and a clearly named artifact such as `sg-ui-22-08-screenshots`.

---

## 16. Final static architecture gates

### Task 16.1 — Legacy namespace ownership scan

Extend architecture tests so canonical global CSS contains none of the historical page-generation namespaces.

For fully migrated templates, prohibit the legacy root namespaces as outer layout classes. Allow a narrowly documented component hook only if a behavior test proves it is still needed.

### Task 16.2 — CSS ownership scan

Implement a conservative parser/text rule that rejects these declarations in page/component-specific `sg-ui-*-v22-08.css` files outside the canonical layout file when applied to global primitives:
- `.sg-shell` grid columns;
- `.sg-content`/main page horizontal padding;
- `.sg-ui-page` page inset;
- global sidebar/topbar dimensions.

This is an ownership guard, not a full CSS parser.

### Task 16.3 — No stylesheet inside content blocks

Scan migrated templates and fail on `<link rel="stylesheet">` occurring after `{% block content %}` begins.

### Task 16.4 — No duplicate canonical asset load

Render representative pages and assert each canonical CSS URL is present once.

---

## 17. Full verification before review

### Task 17.1 — Focused 22.08 suite

Run:

```bash
python -m pytest \
  tests/test_sg_gateway_v22_ui_function_contract_02208.py \
  tests/test_sg_gateway_v22_ui_asset_revision_02208.py \
  tests/test_sg_gateway_v22_ui_architecture_02208.py \
  tests/test_sg_gateway_v22_ui_browser_smoke_02208.py \
  tests/test_sg_gateway_v22_connections_geometry_02208.py \
  tests/test_sg_gateway_v22_clients_geometry_02208.py \
  tests/test_sg_gateway_v22_routing_geometry_02208.py \
  tests/test_sg_gateway_v22_security_geometry_02208.py \
  tests/test_sg_gateway_v22_system_geometry_02208.py \
  tests/test_sg_gateway_v22_maintenance_geometry_02208.py \
  tests/test_sg_gateway_v22_outbounds_geometry_02208.py \
  tests/test_sg_gateway_v22_ui_geometry_matrix_02208.py -q
```

Expected: all pass.

### Task 17.2 — Full existing test suite

```bash
python -m pytest tests
```

Expected: all existing and new tests pass; record exact count and warnings.

### Task 17.3 — Syntax check

Run the exact CI syntax command.

Expected: `syntax ok: N files`.

### Task 17.4 — Regenerate source integrity from staged index

```bash
git add -A
python3 -B - <<'PY'
import hashlib
import subprocess
from pathlib import Path

tracked = subprocess.check_output(
    ["git", "ls-files"], text=True, encoding="utf-8"
).splitlines()
tracked = sorted(path for path in tracked if path != "SOURCE-SHA256SUMS")
rows = []
for path in tracked:
    data = subprocess.check_output(["git", "show", f":{path}"])
    rows.append(f"{hashlib.sha256(data).hexdigest()}  {path}")
Path("SOURCE-SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")
PY
git add SOURCE-SHA256SUMS
```

Commit the final cleanup/manifest state, then run the exact CI source-integrity verifier against `HEAD`.

### Task 17.5 — FULL package verify

```bash
VERSION="$(tr -d '[:space:]' < VERSION)"
OUT="/tmp/SG-Gateway-${VERSION}-FULL.run"
bash build-run.sh "$OUT"
bash "$OUT" --verify-only
```

Expected: verification succeeds.

### Task 17.6 — CI workflow

Push only the feature branch. Open a Draft PR targeting the appropriate development review target only after local full verification. Do not retarget/merge to `dev-02207` without explicit project-lead acceptance.

Confirm the CI run includes:
- source integrity;
- syntax;
- release manifest;
- full pytest including Chromium geometry tests;
- FULL package build/verify.

Record final workflow URL/run id and exact test counts.

---

## 18. Review/acceptance dossier

Before asking to merge, produce one factual dossier containing:

1. base SHA and final feature SHA;
2. complete commit list;
3. exact changed/deleted files;
4. list of canonical shared CSS files;
5. remaining page/component CSS files with explicit ownership reason;
6. list of deleted legacy CSS/JS assets;
7. proof PR #140/#141 commits are not ancestors unless explicitly approved later;
8. focused 22.08 test result;
9. full pytest result;
10. browser geometry matrix result;
11. dark/light desktop/mobile screenshot artifact;
12. source-integrity result;
13. FULL package verify result;
14. CI result;
15. confirmation that backend/protocol/database/routing behavior was not intentionally changed.

Acceptance is blocked if any migrated page still requires a page-generation stylesheet to determine its outer horizontal coordinates.

---

## 19. Expected final frontend ownership

At completion the common dependency direction must be:

```text
base.html
  -> sg-ui-foundation-v22-08.css
  -> sg-ui-layout-v22-08.css
  -> sg-ui-components-v22-08.css
  -> explicit page/component assets

page template
  -> semantic sg-ui page/section/rail primitives
  -> optional component-specific internal classes

component-specific CSS
  -> internal component presentation only
  X shell/page/outer-rail ownership
```

No global compatibility layer should enumerate `sv1/cv2/cnv1/r096/mtv2/...` to make old pages look aligned.

## 20. Stop conditions

Stop the current implementation task and diagnose before proceeding if:
- a functional contract changes unexpectedly;
- browser geometry differs between dark/light themes;
- deleting legacy CSS changes unrelated page geometry;
- a page requires `!important` against canonical layout to align;
- a new manual cache suffix appears necessary;
- Playwright requires production paths/network access rather than isolated test data;
- FULL package verification fails after a CSS/template-only stage;
- a Draft PR #140/#141 commit appears in ancestry without explicit approval.

Do not paper over these with another late override stylesheet. Find the ownership/root-cause violation first.