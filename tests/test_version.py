from app.version import get_release_manifest, get_version


def test_version_file_is_read():
    assert get_version()
    assert get_version() == get_release_manifest()["version"]


def test_release_manifest_has_required_images():
    manifest = get_release_manifest()

    assert manifest["images"]["panel"]
    assert manifest["images"]["xray"]
    assert manifest["rollback"]["requires_backup"] is True