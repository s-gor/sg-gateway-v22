import shutil

import pytest
import json
import uuid

from app.engines.provisioning import build_engine_config


def test_xray_provisioning_generates_uuid():
    object_id, config_json = build_engine_config("xray", 7, "Irina")
    payload = json.loads(config_json)

    assert str(uuid.UUID(object_id)) == object_id
    assert payload["uuid"] == object_id


def test_amneziawg_provisioning_generates_keys():
    if shutil.which("awg") is None:
        pytest.skip("awg binary is not installed in the source-test container")
    object_id, config_json = build_engine_config("amneziawg", 7, "Irina")
    payload = json.loads(config_json)

    assert object_id == payload["public_key"]
    assert payload["private_key"]
    assert payload["address"] == "10.66.7.2/32"