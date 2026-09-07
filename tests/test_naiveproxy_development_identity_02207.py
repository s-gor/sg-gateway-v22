from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_02207_development_line_is_explicit_without_faking_release_identity():
    assert (ROOT / "VERSION").read_text().strip() == "0.1.0-022.08"
    assert (ROOT / "DEVELOPMENT-VERSION").read_text().strip() == "0.1.0-022.09-dev"
    install = (ROOT / "deploy/install-from-github-02207.sh").read_text()
    update = (ROOT / "deploy/update-from-github-02207.sh").read_text()
    assert 'BRANCH="${SG_GATEWAY_GITHUB_BRANCH:-dev-02207}"' in install
    assert 'BRANCH="${SG_GATEWAY_GITHUB_BRANCH:-dev-02207}"' in update
    assert "stable-02206" not in install
    assert "stable-02206" not in update
