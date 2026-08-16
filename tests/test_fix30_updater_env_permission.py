from pathlib import Path

SCRIPT = Path("deploy/update-from-github.sh").read_text(encoding="utf-8")

def test_wsgi_validation_does_not_read_root_env_as_service_user():
    section = SCRIPT.split("validate_deployed_panel() {", 1)[1].split("preflight() {", 1)[0]
    assert "validation_env=\"$validation_root/sg-gateway.env\"" in section
    assert "install -m 0600 -o sg-gateway -g sg-gateway" in section
    assert "\"$CONFIG_DIR/sg-gateway.env\" \"$validation_env\"" in section
    assert "\"$PREFIX\" \"$validation_env\" \"$target\" \"$validation_root\"" in section
    assert "\"$PREFIX\" \"$CONFIG_DIR/sg-gateway.env\" \"$target\" \"$validation_root\"" not in section
