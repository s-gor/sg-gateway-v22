import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_dev_rebuild_identity_is_explicit_and_not_live():
    manifest=json.loads((ROOT/'release-manifest.json').read_text(encoding='utf-8'))
    assert (ROOT/'VERSION').read_text(encoding='utf-8').strip() == '0.1.0-021.12'
    assert manifest['status'] == 'DEV'
    assert manifest['channel'] == 'dev-v22'
    assert manifest['rebuild_target'] == '0.1.0-022.05'
    assert manifest['rebuild_policy']['baseline'] == '0.1.0-021.12'
    assert manifest['rebuild_policy']['awg3'] is True
    assert manifest['rebuild_policy']['publication_requires_real_clean_install'] is True

def test_full_builder_is_version_driven():
    body=(ROOT/'build-run.sh').read_text(encoding='utf-8')
    wrapper=(ROOT/'build-run-vendored.sh').read_text(encoding='utf-8')
    assert 'VERSION="$(tr -d' in body
    assert 'BUILD_ID="$(tr -d' in body
    assert 'DEFAULT_BASENAME="SG-Gateway-${VERSION}-FULL"' in body
    assert '__SG_GATEWAY_BINARY_PAYLOAD_V1__' in body
    assert 'EXPECTED_VERSION="0.1.0-021.12"' not in body
    assert 'SG-Gateway-${VERSION}-FULL.run' in wrapper
    assert '02112' not in wrapper

def test_ci_builds_current_version_named_package():
    body=(ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8')
    assert 'Build and verify current FULL package' in body
    assert 'OUT="/tmp/SG-Gateway-${VERSION}-FULL.run"' in body
    assert 'SG-Gateway-02112-FULL-CLEAN.run' not in body
