# SG InfoSec Security UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe SG-InfoSec management interface to SG-Gateway `/security` without granting the web process administrative SG-InfoSec permissions.

**Architecture:** A dedicated unprivileged Python bridge listens only on `/run/sg-infosec-bridge/management.sock`. It verifies the connecting SG-Gateway UID with `SO_PEERCRED`, exposes a fixed route allowlist, validates every request, forces `source_id=sg-gateway`, and forwards only approved operations to SG-InfoSec `/run/sg-infosec/control.sock`. Flask uses a separate client for the bridge and remains fail-open for login protection when management is unavailable.

**Tech Stack:** Python 3 standard library, Flask/Jinja, Unix domain sockets, systemd, Bash, pytest.

**Spec:** `Вставленная ​​уценка.md` handoff supplied on 2026-09-01.

## Global Constraints

- Work from SG-Gateway `dev-02206` commit `4f77361253a87c16a329b2f8cd8e9f0df66a71c2`.
- Do not commit directly to `dev-02206`.
- Do not add TCP/UDP listeners.
- Never touch ports 585, 586, or 587.
- Do not give `sg-gateway` `read_admin` or `write_admin`.
- Do not access SG-InfoSec SQLite or nftables from Flask.
- Do not run arbitrary shell commands from the web process.
- Management failure must not break VPN service or panel login.
- All web mutations are POST-only, authenticated, CSRF-protected, validated, and audited by SG-InfoSec.

---

### Task 1: Management bridge protocol

**Files:**
- Create: `app/security/sg_infosec_bridge.py`
- Test: `tests/test_sg_infosec_management_bridge.py`

- [ ] Write failing tests for peer UID rejection, route allowlist, request-size limits, forced source ID, IP/CIDR validation, duration limit, timeouts, and Unix-socket-only operation.
- [ ] Implement the minimal bridge with fixed route dispatch and structured JSON errors.
- [ ] Run the focused pytest file.
- [ ] Commit the bridge and tests.

### Task 2: Flask management client and endpoints

**Files:**
- Create: `app/security/sg_infosec_management.py`
- Modify: `app/production.py`
- Test: `tests/test_sg_infosec_security_ui.py`

- [ ] Write failing tests for unavailable status, authenticated reads, anonymous rejection, POST-only mutations, CSRF enforcement, and input validation.
- [ ] Implement the Unix-socket client, context injection, and fixed Flask endpoints for manual block, revoke, allowlist add, and allowlist delete.
- [ ] Register the module after existing SG-InfoSec login middleware.
- [ ] Run focused tests and commit.

### Task 3: Existing-style `/security` interface

**Files:**
- Modify: `app/web/templates/security.html`
- Create: `app/web/templates/_sg_infosec_management.html`
- Create: `app/web/static/sg-infosec-management-v1.css`
- Test: `tests/test_sg_infosec_security_ui.py`

- [ ] Add compact summary, active decisions, manual block, allowlist, and recent audit sections.
- [ ] Disable mutation controls when the bridge is unavailable.
- [ ] Keep the existing HTTPS/password content unchanged.
- [ ] Run template/UI contract tests and commit.

### Task 4: Systemd and idempotent installation

**Files:**
- Create: `deploy/systemd/sg-infosec-management-bridge.service`
- Create: `deploy/install-sg-infosec-management-bridge.sh`
- Modify: `deploy/systemd/sg-gateway.service`
- Test: `tests/test_sg_infosec_management_install_contract.py`

- [ ] Create a dedicated `sg-infosec-bridge` system user with no login shell.
- [ ] Install the SG-InfoSec source-role file with `read_admin` and `write_admin` only for the bridge UID.
- [ ] Link the bridge unit from the release tree, use `PartOf=sg-gateway.service`, and avoid persistent enablement so rollback stops the bridge with the panel.
- [ ] Add a non-fatal privileged `ExecStartPre` installer to the root-owned panel unit.
- [ ] Verify no network listeners and no references to ports 585/586/587.
- [ ] Run shell syntax and contract tests and commit.

### Task 5: Verification

- [ ] Run focused pytest tests.
- [ ] Run the complete available pytest suite.
- [ ] Run `python -m compileall` for changed Python modules.
- [ ] Run `bash -n` for changed shell scripts.
- [ ] Validate both systemd units.
- [ ] Confirm branch ancestry and exact parent SHA.
- [ ] Check GitHub CI on the final SHA.
- [ ] Do not merge into `dev-02206` without explicit approval.
