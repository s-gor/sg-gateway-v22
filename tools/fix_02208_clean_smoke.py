from pathlib import Path

installer = Path("install.sh")
text = installer.read_text(encoding="utf-8")

# Production: provide the fail helper used by noninteractive/TTY validation paths.
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

# 22.08 must accept a resume file left by the immediately previous stable
# installer. Move it to the current name before parsing, so successful install
# never leaves two competing resume-state files behind.
resume_anchor = '''load_resume_state() {
  [[ -f "$RESUME_FILE" ]] || return 1
'''
resume_replacement = '''load_resume_state() {
  local legacy_resume_file="/root/sg-gateway-02206-installer-resume.env"
  if [[ ! -f "$RESUME_FILE" && -f "$legacy_resume_file" ]]; then
    mv -f "$legacy_resume_file" "$RESUME_FILE"
    chmod 0600 "$RESUME_FILE"
    echo "[SG-Gateway] Параметры незавершённой установки 022.06 перенесены в формат 022.08."
  fi
  [[ -f "$RESUME_FILE" ]] || return 1
'''
if resume_replacement not in text:
    if text.count(resume_anchor) != 1:
        raise SystemExit(f"load_resume_state anchor count={text.count(resume_anchor)}")
    text = text.replace(resume_anchor, resume_replacement, 1)
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

# Release regression: Clean Install uses the current resume contract. Reinstall
# deliberately retains the 022.06 seed to prove one-step migration into 22.08.
release_test = Path("tests/test_sg_gateway_v22_release_02208.py")
body = release_test.read_text(encoding="utf-8")
start = body.find("\ndef test_02208_installer_and_smoke_workflows_use_current_identity():")
if start >= 0:
    body = body[:start].rstrip() + "\n"
body += '''\n\ndef test_02208_installer_and_smoke_workflows_use_current_identity():
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    clean = (ROOT / ".github" / "workflows" / "clean-install-awg3-smoke.yml").read_text(encoding="utf-8")
    reinstall = (ROOT / ".github" / "workflows" / "reinstall-after-full-uninstall-smoke.yml").read_text(encoding="utf-8")

    assert 'fail() {' in installer
    assert 'VERSION="0.1.0-022.08"' in installer
    assert 'legacy_resume_file="/root/sg-gateway-02206-installer-resume.env"' in installer
    assert 'mv -f "$legacy_resume_file" "$RESUME_FILE"' in installer

    assert '/root/sg-gateway-02208-installer-resume.env' in clean
    assert '/root/sg-gateway-02206-installer-resume.env' not in clean
    assert '/var/log/sg-gateway-installer-02208.log' in clean

    # The reinstall smoke intentionally exercises legacy-state compatibility.
    assert '/root/sg-gateway-02206-installer-resume.env' in reinstall
'''
release_test.write_text(body, encoding="utf-8")
