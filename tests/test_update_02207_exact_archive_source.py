from pathlib import Path


ROOT = Path(__file__).parents[1]
WRAPPER = ROOT / "deploy" / "update-from-github-02207.sh"


def test_02207_bootstraps_exact_commit_core_before_panel_update():
    wrapper = WRAPPER.read_text(encoding="utf-8")

    assert (
        "https://raw.githubusercontent.com/${REPOSITORY}/${REQUESTED_SOURCE_COMMIT}/"
        "deploy/update-from-github-core.sh"
    ) in wrapper
    assert "Preparing exact-commit panel updater core" in wrapper
    assert "SG_GATEWAY_UPDATE_CORE_LIBRARY_ONLY=1" in wrapper
    assert 'source "$core"' in wrapper
    assert 'bash "$PREFIX/deploy/update-from-github.sh"' not in wrapper


def test_02207_exact_core_bypasses_light_git_and_uses_archive_source():
    wrapper = WRAPPER.read_text(encoding="utf-8")

    assert "22.07 exact source policy: archive by commit; Git LIGHT disabled" in wrapper
    assert "prepare_source_light()" in wrapper
    assert "prepare_source_archive" in wrapper
    assert "GIT_ASKPASS=/bin/false" not in wrapper
    assert 'SG_GATEWAY_GIT_URL="https://github.com/${REPOSITORY}.git"' not in wrapper
