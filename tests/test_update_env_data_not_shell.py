from __future__ import annotations

import shlex
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "deploy" / "update-from-github.sh"


def _post_update_function() -> str:
    source = UPDATER.read_text(encoding="utf-8")
    start = source.index("post_update_awg3_bootstrap() {")
    end = source.index("\n}\n\nbootstrap_main() {", start) + 3
    return source[start:end]


def test_post_update_bootstrap_treats_persisted_env_as_data(tmp_path: Path) -> None:
    prefix = tmp_path / "opt" / "sg-gateway"
    config_dir = tmp_path / "etc" / "sg-gateway"
    data_dir = tmp_path / "var" / "lib" / "sg-gateway"
    python = prefix / ".venv" / "bin" / "python"
    module = prefix / "app" / "maintenance" / "awg3_idle_bootstrap.py"

    python.parent.mkdir(parents=True)
    module.parent.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)

    python.write_text(
        "#!/usr/bin/env bash\n"
        "set -Eeuo pipefail\n"
        "[[ -z \"${SG_GATEWAY_ADMIN_PASSWORD_HASH+x}\" ]]\n"
        "[[ -z \"${SG_GATEWAY_SECRET_KEY+x}\" ]]\n"
        "printf '%s|%s|%s\\n' \"$SG_GATEWAY_APP_ROOT\" \"$SG_GATEWAY_CONFIG_DIR\" \"$SG_GATEWAY_DATA_DIR\"\n",
        encoding="utf-8",
    )
    python.chmod(0o755)
    module.write_text("# test module marker\n", encoding="utf-8")

    (config_dir / "runtime.env").write_text(
        'SG_GATEWAY_PUBLIC_ADDRESS="203.0.113.10"\n', encoding="utf-8"
    )
    (config_dir / "sg-gateway.env").write_text(
        'SG_GATEWAY_ADMIN_PASSWORD_HASH="$3$literal-dollar-value"\n'
        'SG_GATEWAY_SECRET_KEY="$(false)"\n',
        encoding="utf-8",
    )

    script = "\n".join(
        (
            "set -Eeuo pipefail",
            _post_update_function(),
            "unset SG_GATEWAY_ADMIN_PASSWORD_HASH SG_GATEWAY_SECRET_KEY || true",
            f"export SG_GATEWAY_PREFIX={shlex.quote(str(prefix))}",
            f"export SG_GATEWAY_CONFIG_DIR={shlex.quote(str(config_dir))}",
            f"export SG_GATEWAY_DATA_DIR={shlex.quote(str(data_dir))}",
            "post_update_awg3_bootstrap",
        )
    )
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Checking AWG3.0 first-start state" in result.stdout
    assert f"{prefix}|{config_dir}|{data_dir}" in result.stdout
