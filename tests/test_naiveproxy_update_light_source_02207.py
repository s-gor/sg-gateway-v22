from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "deploy" / "update-from-github-core.sh").read_text(encoding="utf-8")


def _shell_function(name: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}$",
        CORE,
    )
    assert match is not None, f"shell function is missing: {name}"
    return match.group(0)


def test_light_source_fetches_naiveproxy_hostd_unit() -> None:
    function = _shell_function("prepare_source_light")
    assert "/hostd/systemd/sg-hostd.service" in function


def test_source_preflight_requires_naiveproxy_hostd_unit() -> None:
    function = _shell_function("prepare_source")
    assert '[[ -f "$SOURCE_DIR/hostd/systemd/sg-hostd.service" ]]' in function
