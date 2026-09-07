from pathlib import Path

FINAL = "6ec4b31c45bdfd648a8ee0415e588a557614651b"
STALE = (
    "f709015548de91c631a5daf174194f245f7cce00",
    "889206dd3ddb7d10ef7480f3b5b23694f0b90b7e",
)

def test_public_clean_install_is_pinned_to_final_verified_source():
    for name in ("PUBLICATION-02208.md", "deploy/GITHUB-COMMANDS.md"):
        body = Path(name).read_text(encoding="utf-8")
        assert FINAL in body, name
        for stale in STALE:
            assert stale not in body, (name, stale)

def test_full_uninstall_reinstall_hint_follows_stable_channel_without_stale_sha():
    body = Path("deploy/full-uninstall-ubuntu.sh").read_text(encoding="utf-8")
    for stale in STALE:
        assert stale not in body, stale
    assert "stable-02208/deploy/install-from-github.sh" in body
    assert "Для повторной установки SG-Gateway" in body
