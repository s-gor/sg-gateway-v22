from pathlib import Path

# Production: provide the fail helper used by noninteractive/TTY validation paths.
installer = Path("install.sh")
text = installer.read_text(encoding="utf-8")
anchor = '''prepare_log() {
  install -d -m 0755 "$(dirname "$INSTALL_LOG")"
  : > "$INSTALL_LOG"
  chmod 0600 "$INSTALL_LOG"
}

'''
if text.count(anchor) != 1:
    raise SystemExit(f"prepare_log anchor count={text.count(anchor)}")
fail_block = '''fail() {
  printf '[SG-Gateway] %s\\n' "$1" >&2
  return 1
}

'''
if "fail() {" not in text:
    text = text.replace(anchor, anchor + fail_block, 1)
installer.write_text(text, encoding="utf-8")

# Current canonical reinstall command must point at the verified 22.08 exact source.
test = Path("tests/test_sg_gateway_v22_reinstall_after_full_uninstall.py")
body = test.read_text(encoding="utf-8")
body = body.replace(
    'PINNED_INSTALL_SHA = "2e96ea97992509f8ff2fdce8b8d23aa0dc5a1dff"',
    'PINNED_INSTALL_SHA = "889206dd3ddb7d10ef7480f3b5b23694f0b90b7e"',
)
body = body.replace('"SG_GATEWAY_GITHUB_BRANCH=stable-02206 "', '"SG_GATEWAY_GITHUB_BRANCH=stable-02208 "')
body = body.replace('assert "stable-02206/deploy/install-from-github.sh" not in body', 'assert "stable-02208/deploy/install-from-github.sh" not in body')
test.write_text(body, encoding="utf-8")

# Release regression: current workflows and installer emergency path must match 22.08.
release_test = Path("tests/test_sg_gateway_v22_release_02208.py")
body = release_test.read_text(encoding="utf-8")
extra = '''\n\ndef test_02208_installer_and_smoke_workflows_use_current_identity():\n    installer = (ROOT / "install.sh").read_text(encoding="utf-8")\n    clean = (ROOT / ".github" / "workflows" / "clean-install-awg3-smoke.yml").read_text(encoding="utf-8")\n    reinstall = (ROOT / ".github" / "workflows" / "reinstall-after-full-uninstall-smoke.yml").read_text(encoding="utf-8")\n\n    assert 'fail() {' in installer\n    assert 'VERSION="0.1.0-022.08"' in installer\n    assert '/root/sg-gateway-02208-installer-resume.env' in clean\n    assert '/root/sg-gateway-02206-installer-resume.env' not in clean\n    assert '/var/log/sg-gateway-installer-02208.log' in clean\n    assert '/root/sg-gateway-02208-installer-resume.env' in reinstall\n    assert '/root/sg-gateway-02206-installer-resume.env' not in reinstall\n    assert '/var/log/sg-gateway-installer-02208.log' in reinstall\n    assert '/var/log/sg-gateway-full-uninstall-02208.log' in reinstall\n'''
if "test_02208_installer_and_smoke_workflows_use_current_identity" not in body:
    body += extra
release_test.write_text(body, encoding="utf-8")
