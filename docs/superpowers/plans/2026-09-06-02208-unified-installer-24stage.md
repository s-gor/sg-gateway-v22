# SG-Gateway 0.1.0-022.08 Unified 24-Stage Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single transactional 22.08 clean installer with exactly 24 visible stages and first-class NaiveProxy installation, starting from the clean Stage 8 UI baseline.

**Architecture:** `install.sh` is the only production master. GitHub wrappers perform bootstrap/download only and never rewrite installer source or append runtimes. Existing runtime-specific implementation is called from explicit master stages and shares the master rollback/success boundary.

**Tech Stack:** Bash, Python 3.12, pytest, systemd, GitHub Actions, Ubuntu 24.04.

**Spec:** `docs/superpowers/specs/2026-09-06-02208-unified-installer-24stage-design.md`

## Global Constraints

- Work only on `feature/02208-unified-installer-24stage`, based on `8165f93cdbaf7e54d74167d722f1b8e156d8c1bf`.
- Do not modify `dev-02207` or `release/02208-rc`.
- Do not modify `app/web/`, templates, CSS or JS for this installer rebuild.
- Native installer exposes exactly `1/24` through `24/24` top-level stages.
- NaiveProxy installation occurs inside `install.sh` before `INSTALL_SUCCESS=1`.
- No server-side FIX scripts, sed patches, marker injection or runtime source rewriting.

---

### Task 1: RED installer architecture contract

**Files:**
- Create: `tests/test_sg_gateway_v22_unified_installer_02208.py`

**Interfaces:**
- Consumes: `install.sh`, `deploy/install-from-github.sh`, `deploy/install-naiveproxy.sh`.
- Produces: contract for `TOTAL_STAGES=24`, ordered stage labels, master NaiveProxy call and thin wrapper.

- [ ] Write tests that parse `install.sh` and require `TOTAL_STAGES=24`.
- [ ] Require exactly 24 ordered top-level `run_stage`/`run_quiet` stage numbers before the success boundary.
- [ ] Require an explicit master function `stage_install_naiveproxy` invoking `deploy/install-naiveproxy.sh` before `INSTALL_SUCCESS=1`.
- [ ] Require `deploy/install-from-github.sh` to contain no `source.replace`, `patched_installer`, or post-install NaiveProxy invocation.
- [ ] Run the focused tests and confirm RED on the clean Stage 8 baseline.
- [ ] Commit the RED test only.

### Task 2: 22.08 identity and 24-stage master orchestration

**Files:**
- Modify: `install.sh`
- Test: `tests/test_sg_gateway_v22_unified_installer_02208.py`

**Interfaces:**
- Produces: `stage_install_naiveproxy()` and exactly 24 ordered top-level stages.

- [ ] Change installer identity to `0.1.0-022.08`, build `02208-unified-24stage`, log/resume/backup names `02208`.
- [ ] Split the current combined engine stage into explicit master calls for vendor verification, AWG2, AWG3, Xray, Mihomo, sing-box and WARP without changing their underlying runtime implementation.
- [ ] Add AWG3.1 migration/install as its own top-level stage.
- [ ] Add `stage_install_naiveproxy()` that calls `env SG_GATEWAY_SOURCE_ROOT="$SOURCE_DIR" bash "$SOURCE_DIR/deploy/install-naiveproxy.sh"` and verifies installed unit/prefix/config/state contract.
- [ ] Re-map existing source/config/database/systemd/firewall/runtime/final verification functions into exactly 24 ordered visible stages.
- [ ] Keep `INSTALL_SUCCESS=1` only after stage 24 passes.
- [ ] Run focused tests GREEN.

### Task 3: Thin 22.08 GitHub wrapper

**Files:**
- Modify/Create: `deploy/install-from-github.sh`
- Test: `tests/test_sg_gateway_v22_unified_installer_02208.py`

**Interfaces:**
- Consumes: exact source SHA and `stable-02208` channel label.
- Produces: bootstrap → download → direct `bash "$SOURCE_DIR/install.sh"` only.

- [ ] Preserve Ubuntu/cloud-init/disk/bootstrap checks.
- [ ] Pin accepted channel to `stable-02208` and validate optional exact 40-hex SHA.
- [ ] Download source and directly invoke master installer.
- [ ] Ensure no source rewriting, patching, marker replacement or runtime installation exists in wrapper.
- [ ] Run focused tests GREEN.

### Task 4: Full uninstall contract including NaiveProxy

**Files:**
- Modify/Create: `deploy/full-uninstall-ubuntu.sh`
- Modify/Create: `deploy/uninstall-from-github.sh`
- Test: `tests/test_sg_gateway_v22_unified_installer_02208.py`

**Interfaces:**
- Produces deterministic removal of SG application/runtime including NaiveProxy-managed unit, prefix, config, state and service identity.

- [ ] Add assertions/tests for NaiveProxy cleanup and 22.08 identity.
- [ ] Ensure full uninstall removes NaiveProxy SG-owned artifacts while preserving unrelated Ubuntu packages/data.
- [ ] Keep exact confirmation `DELETE SG-GATEWAY`.
- [ ] Run focused tests GREEN.

### Task 5: Real clean-install smoke must verify NaiveProxy

**Files:**
- Modify: `.github/workflows/clean-install-awg3-smoke.yml` or replace with a 22.08 all-runtime clean-install workflow.
- Test: `tests/test_sg_gateway_v22_unified_installer_02208.py`

**Interfaces:**
- Produces acceptance evidence that a successful clean install has NaiveProxy runtime/unit/API integration plus AWG/Xray/Mihomo/sing-box contracts.

- [ ] Rename/expand smoke semantics from AWG3-only to all mandatory 22.08 runtimes.
- [ ] Verify NaiveProxy prefix/config/state/unit exist after install.
- [ ] Verify NaiveProxy is ready/disabled when settings/HTTPS are absent, not falsely required active.
- [ ] Keep AWG3/AWG31/Xray/Mihomo/sing-box checks.

### Task 6: Release identity and source integrity

**Files:**
- Modify: `VERSION`, `BUILD-ID`, `DEVELOPMENT-VERSION`, `release-manifest.json`, release/public command files needed by 22.08.
- Regenerate: `SOURCE-SHA256SUMS`.

- [ ] Set release identity to `0.1.0-022.08`, `MAIN-02208-STABLE`, next development `0.1.0-022.09-dev`, channel `stable-02208`.
- [ ] Regenerate source snapshot after all source changes.
- [ ] Ensure no public exact-source command points at the abandoned RC.

### Task 7: Full verification

- [ ] Run full pytest; require zero failures.
- [ ] Run source integrity and syntax/manifest gates.
- [ ] Build `SG-Gateway-0.1.0-022.08-FULL.run` and run `--verify-only`.
- [ ] Run real Ubuntu 24.04 Clean Install and verify all mandatory runtimes including NaiveProxy.
- [ ] Run Full Uninstall and verify deterministic clean SG state.
- [ ] Run Reinstall and verify all mandatory runtimes including NaiveProxy again.
- [ ] Compare branch against Stage 8 and reject any changes under `app/web/` or other UI geometry assets.
- [ ] Only after fresh all-green evidence may this branch become a new release candidate.
