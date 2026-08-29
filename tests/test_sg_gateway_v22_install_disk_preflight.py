from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "deploy" / "install-from-github.sh"


def test_clean_installer_checks_free_space_before_download_and_extraction():
    text = INSTALLER.read_text(encoding="utf-8")

    assert 'MIN_FREE_MIB="${SG_GATEWAY_INSTALL_MIN_FREE_MIB:-1024}"' in text
    assert "require_free_space()" in text
    assert 'df -Pk "$path"' in text
    assert 'require_free_space /tmp "temporary storage"' in text
    assert 'require_free_space /opt "installation storage"' in text
    assert "not enough free disk space for clean install" in text

    first_preflight = text.index('require_free_space /tmp "temporary storage"')
    package_bootstrap = text.index("missing_packages=()")
    download = text.index("Downloading GitHub branch")
    extraction = text.index('tar -xzf "$ARCHIVE"')

    assert first_preflight < package_bootstrap
    assert first_preflight < download
    assert first_preflight < extraction
