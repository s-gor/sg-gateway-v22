from pathlib import Path

OLD = "cde152df4b957c254950e3b4a2276b76561653c9"
NEW = "889206dd3ddb7d10ef7480f3b5b23694f0b90b7e"

for name in ("README.md", "PUBLICATION-02208.md", "deploy/GITHUB-COMMANDS.md"):
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    count = text.count(OLD)
    if count < 2:
        raise SystemExit(f"expected exact-source pin in {name}, found {count}")
    path.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print(f"{name}: repinned {count} occurrence(s)")

path = Path("deploy/full-uninstall-ubuntu.sh")
text = path.read_text(encoding="utf-8")
old_command = "curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/2e96ea97992509f8ff2fdce8b8d23aa0dc5a1dff/deploy/install-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02206 SG_GATEWAY_SOURCE_COMMIT=2e96ea97992509f8ff2fdce8b8d23aa0dc5a1dff bash"
new_command = f"curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/{NEW}/deploy/install-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 SG_GATEWAY_SOURCE_COMMIT={NEW} bash"
if text.count(old_command) != 1:
    raise SystemExit(f"expected one legacy reinstall command, found {text.count(old_command)}")
path.write_text(text.replace(old_command, new_command), encoding="utf-8")
print("deploy/full-uninstall-ubuntu.sh: repinned reinstall guidance")
