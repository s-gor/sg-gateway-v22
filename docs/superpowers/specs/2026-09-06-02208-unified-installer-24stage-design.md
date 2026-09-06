# SG-Gateway 0.1.0-022.08 Unified 24-Stage Installer Design

## Goal

Rebuild the 22.08 installation/release path from the clean Stage 8 UI baseline. There must be one production installer and one source of truth. NaiveProxy is a first-class runtime installed by that master, not injected by a wrapper.

## Branch and isolation

Work only on `feature/02208-unified-installer-24stage`, created from Stage 8 commit `8165f93cdbaf7e54d74167d722f1b8e156d8c1bf`.

Do not modify `dev-02207` or `release/02208-rc`. Do not alter UI geometry, templates, CSS or JS as part of this installer rebuild.

## Architecture

`install.sh` is the only production master. `deploy/install-from-github.sh` performs only Ubuntu/bootstrap preflight, downloads an exact source tree, and invokes `install.sh`. It must not patch, inject or append runtime installation logic.

The master owns installation, transaction boundaries, rollback and final validation for every shipped runtime: AWG2, AWG3, AWG3.1, Xray, Mihomo, sing-box, WARP and NaiveProxy.

NaiveProxy uses the existing production implementation in `deploy/install-naiveproxy.sh` as an internal installer component, but invocation is explicit inside `install.sh` before the success boundary. Failure must abort the master and participate in the same install rollback.

## 24 visible stages

The native installer exposes exactly 24 top-level stages, numbered `1/24` through `24/24`:

1. Validate Ubuntu/root/preconditions
2. Prepare installation log and transaction state
3. Detect existing installation and migration mode
4. Capture rollback snapshot
5. Install required Ubuntu packages
6. Verify vendored core manifests
7. Install AWG2 runtime
8. Install AWG3 runtime
9. Install AWG3.1 runtime
10. Install Xray runtime
11. Install Mihomo runtime
12. Install sing-box runtime
13. Install WARP runtime
14. Install NaiveProxy runtime
15. Install application source and Python environment
16. Generate/persist base configuration and secrets
17. Initialize database and seed sg-admin
18. Install systemd units and service ownership
19. Configure firewall/sysctl/network prerequisites
20. Generate/apply Xray and client runtime catalogue
21. Configure Nginx/panel access and HTTPS placeholder
22. Start HostD, panel and required runtimes
23. Validate every mandatory runtime and UI/backend contract
24. Commit transaction, clean rollback snapshot and print final access summary

Substeps may exist internally, but top-level progress must remain exactly 24 stages.

## Runtime contract

A successful clean install is not allowed unless all mandatory shipped runtime assets are present and structurally valid. For NaiveProxy specifically, the installer must verify its prefix/config/state paths, systemd unit registration, command/API integration expected by the panel, and disabled/ready state when HTTPS/settings are not yet configured. It must not falsely require an active listener before user configuration.

## Wrappers

`deploy/install-from-github.sh` must only: validate supported branch/exact SHA, wait for cloud-init, check disk/bootstrap tools, download source, and execute `install.sh` with the exact source environment. No Python source rewriting, no marker replacement, no post-install NaiveProxy call.

Legacy `deploy/install-from-github-02207.sh` is historical compatibility only and cannot define 22.08 behavior.

## Rollback

All 24 stages are within one master transaction. Any failure before stage 24 restores the pre-install server state for SG-managed paths and service state. NaiveProxy-created user/group, prefix, config, state and unit must be reverted by the same failure path. There are no server-side FIX scripts, sed patches or separate repair commands for release acceptance.

## Testing and acceptance

TDD first: add tests that fail on the Stage 8 baseline because the master lacks 24 stages and lacks first-class NaiveProxy invocation.

Required gates before release acceptance:

- installer contract test proves exactly 24 ordered top-level stages;
- wrapper contract proves no source rewriting/injection;
- NaiveProxy clean-install contract proves it is invoked inside the master before `INSTALL_SUCCESS=1`;
- rollback tests cover NaiveProxy-managed paths/service identity;
- full pytest has zero failures;
- source integrity passes;
- FULL package build and `--verify-only` pass;
- real Ubuntu 24.04 Clean Install succeeds and verifies all runtimes including NaiveProxy;
- Full Uninstall leaves deterministic clean SG state;
- Reinstall succeeds and again verifies all runtimes including NaiveProxy;
- existing Stage 8 UI geometry remains unchanged by diff and browser checks.
