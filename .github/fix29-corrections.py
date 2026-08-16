from pathlib import Path


def get(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def put(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def one(path: str, old: str, new: str) -> None:
    text = get(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one marker, got {count}: {old[:120]!r}")
    put(path, text.replace(old, new, 1))


# Public Client constructor remains backward compatible: AWG3 is optional and appended.
one("app/clients/repository.py", "    awg3_status: str\n", "")
one(
    "app/clients/repository.py",
    "    active_device_count: int = 0\n",
    "    active_device_count: int = 0\n    awg3_status: str = \"missing\"\n",
)

# Device picker actually knows and orders AWG3, not only server-side HTML.
one(
    "app/web/static/sg-device-collapse-v1.js",
    "    'amneziawg',\n    'mihomo',",
    "    'amneziawg',\n    'amneziawg3',\n    'mihomo',",
)
one(
    "app/web/static/sg-device-collapse-v1.js",
    "    setLabelTitle(byValue.get('amneziawg'), 'AmneziaWG 2.0');\n",
    "    setLabelTitle(byValue.get('amneziawg'), 'AmneziaWG 2.0');\n"
    "    setLabelTitle(byValue.get('amneziawg3'), 'AmneziaWG 3.0');\n",
)
one(
    "app/web/static/sg-device-collapse-v1.js",
    "      setAvailableNote(byValue.get('amneziawg'), 'UDP 585 · отдельная конфигурация и QR');\n",
    "      setAvailableNote(byValue.get('amneziawg'), 'UDP 585 · отдельная конфигурация и QR');\n"
    "      setAvailableNote(byValue.get('amneziawg3'), 'UDP 586 · userspace-конфигурация и QR');\n",
)

# Fix28 DEV metadata assertions advance to intentionally enabled Fix29 policy.
for path, old in (
    ("tests/test_sg_gateway_v22_release_preparation.py", "assert manifest['rebuild_policy']['awg3'] is False"),
    ("tests/test_sg_gateway_02112_final_cumulative_cleanup_r5.py", 'assert release["rebuild_policy"]["awg3"] is False'),
):
    text = get(path)
    if old not in text:
        raise SystemExit(f"{path}: AWG3 policy assertion missing")
    put(path, text.replace(old, old.replace("False", "True"), 1))

# Stage6 now seeds a fourth independent connection endpoint.
one(
    "tests/test_preview52_installer_stage6_and_progress.py",
    '        "amneziawg": "203.0.113.10",\n        "mihomo": "203.0.113.10",',
    '        "amneziawg": "203.0.113.10",\n        "amneziawg3": "203.0.113.10",\n        "mihomo": "203.0.113.10",',
)

# Connections domain contract covers both AWG generations.
path = "tests/test_sg_gateway_02112_all_connections_domain_fix3.py"
text = get(path)
text = text.replace(
    '{"amneziawg", "xray", "mihomo"}',
    '{"amneziawg", "amneziawg3", "xray", "mihomo"}',
    1,
)
text = text.replace(
    '    assert "xray_public_host = public_host(xray.host)" in service\n',
    '    assert "awg3_public_host = public_host(awg3.host)" in service\n'
    '    assert "xray_public_host = public_host(xray.host)" in service\n',
    1,
)
text = text.replace(
    '    assert \'name="host" value="{{ awg_public_host }}"\' in page\n',
    '    assert \'name="host" value="{{ awg_public_host }}"\' in page\n'
    '    assert "<strong>{{ awg3_public_host }}</strong>" in page\n'
    '    assert \'name="host" value="{{ awg3_public_host }}"\' in page\n',
    1,
)
text = text.replace(
    '    assert "AmneziaWG: {{ awg_public_host }}:{{ awg_settings.port }}" in page\n',
    '    assert "AWG2: {{ awg_public_host }}:{{ awg_settings.port }}" in page\n'
    '    assert "AWG3: {{ awg3_public_host }}:{{ awg3_settings.port }}" in page\n',
    1,
)
put(path, text)

# Six install steps / eight vendored media files; AWG2 DKMS checks remain intact.
path = "tests/test_sg_gateway_021_vendored_five_engines.py"
text = get(path)
text = text.replace(
    "def test_installer_uses_five_vendored_engines():",
    "def test_installer_uses_six_vendored_engine_steps_with_isolated_awg3():",
    1,
)
for old, new in (
    ("[Engine 1/5] AmneziaWG", "[Engine 1/6] AmneziaWG 2"),
    ("[Engine 2/5] Xray", "[Engine 2/6] AmneziaWG 3 userspace"),
    ("[Engine 3/5] Mihomo", "[Engine 3/6] Xray"),
    ("[Engine 4/5] sing-box", "[Engine 4/6] Mihomo"),
    ("[Engine 5/5] WARP", "[Engine 5/6] sing-box"),
):
    if old not in text:
        raise SystemExit(f"vendored engine marker missing: {old}")
    text = text.replace(old, new, 1)
text = text.replace(
    '    assert "install_xray_from_vendor" in stage\n',
    '    assert "install_amneziawg3_userspace_from_vendor" in stage\n'
    '    assert "[Engine 6/6] WARP" in stage\n'
    '    assert "install_xray_from_vendor" in stage\n',
    1,
)
text = text.replace(
    "def test_all_six_vendor_files_are_required():",
    "def test_all_eight_vendor_files_are_required():",
    1,
)
text = text.replace(
    '        "amneziawg-linux-kernel-module-1.0.20260329-2.tar.gz",\n',
    '        "amneziawg-linux-kernel-module-1.0.20260329-2.tar.gz",\n'
    '        "amneziawg-tools-3.0.20260805.tar.gz",\n'
    '        "amneziawg-go-linux-amd64-v3.0.0",\n',
    1,
)
text += (
    "\n\ndef test_awg3_vendor_set_has_no_3x_kernel_module():\n"
    "    installer = read(\"install.sh\")\n"
    "    assert \"amneziawg-linux-kernel-module-3.0\" not in installer\n"
    "    assert not any((ROOT / \"vendor\" / \"cores\").glob(\"amneziawg-linux-kernel-module-3.0*\"))\n"
)
put(path, text)

# WARP remains optional; AWG3 is allowed only as isolated userspace.
path = "tests/test_sg_gateway_v22_optional_warp_install.py"
text = get(path)
text = text.replace(
    "assert '[Engine 5/5] WARP wgcf-cli' in body",
    "assert '[Engine 6/6] WARP wgcf-cli' in body",
    1,
)
old = '''def test_optional_warp_fix_preserves_awg2_and_xmux_only() -> None:
    installer = (ROOT / 'install.sh').read_text(encoding='utf-8').lower()
    assert 'amneziawg3' not in installer
    assert 'awg3' not in installer
    assert (ROOT / 'app/xray/xmux.py').is_file()
'''
new = '''def test_optional_warp_fix_preserves_awg2_xmux_and_isolates_awg3() -> None:
    installer = (ROOT / 'install.sh').read_text(encoding='utf-8').lower()
    assert 'amneziawg_tools_version="1.0.20260618-2"' in installer
    assert 'amneziawg_kmod_version="1.0.20260329-2"' in installer
    assert 'awg3_tools_version="3.0.20260805"' in installer
    assert 'prefix="$prefix/awg3" install' in installer
    assert 'amneziawg-linux-kernel-module-3.0' not in installer
    assert (ROOT / 'app/xray/xmux.py').is_file()
'''
if old not in text:
    raise SystemExit("optional WARP legacy AWG3 exclusion block missing")
put(path, text.replace(old, new, 1))

# Device UX includes AWG3 in canonical order and keeps existing layers.
path = "tests/test_sg_gateway_v22_clients_devices_ux.py"
text = get(path)
text = text.replace(
    "expected = ['xray_reality_tcp','xray_xhttp_reality','xray_xhttp_tls','xray_hysteria2','amneziawg','mihomo','anytls','tuic']",
    "expected = ['xray_reality_tcp','xray_xhttp_reality','xray_xhttp_tls','xray_hysteria2','amneziawg','amneziawg3','mihomo','anytls','tuic']",
    1,
)
text = text.replace(
    "    assert \"setLabelTitle(byValue.get('amneziawg'), 'AmneziaWG 2.0')\" in body\n"
    "    lowered = body.lower()\n"
    "    assert 'awg3' not in lowered\n"
    "    assert 'amneziawg 3.0' not in lowered\n",
    "    assert \"setLabelTitle(byValue.get('amneziawg'), 'AmneziaWG 2.0')\" in body\n"
    "    assert \"setLabelTitle(byValue.get('amneziawg3'), 'AmneziaWG 3.0')\" in body\n"
    "    assert \"setAvailableNote(byValue.get('amneziawg3'), 'UDP 586 · userspace-конфигурация и QR')\" in body\n",
    1,
)
text = text.replace(
    "    assert not (ROOT / 'hostd/sg_hostd/awg3_runtime.py').exists()",
    "    assert (ROOT / 'hostd/sg_hostd/awg3_runtime.py').exists()",
    1,
)
put(path, text)

# Gecko and low-resolution contracts now verify coexistence instead of absence.
path = "tests/test_sg_gateway_v22_hysteria2_gecko.py"
text = get(path)
text = text.replace(
    "def test_gecko_integration_preserves_xmux_and_excludes_awg3() -> None:",
    "def test_gecko_integration_preserves_xmux_alongside_isolated_awg3() -> None:",
    1,
)
text = text.replace(
    "    assert not (ROOT / 'hostd/sg_hostd/awg3_runtime.py').exists()\n"
    "    assert not (ROOT / 'deploy/sg-gateway-awg3.service').exists()\n",
    "    assert (ROOT / 'hostd/sg_hostd/awg3_runtime.py').is_file()\n"
    "    assert (ROOT / 'deploy/sg-gateway-awg3.service').is_file()\n",
    1,
)
put(path, text)

path = "tests/test_sg_gateway_v22_low_resolution.py"
text = get(path)
text = text.replace(
    "    assert not (ROOT / 'hostd/sg_hostd/awg3_runtime.py').exists()",
    "    assert (ROOT / 'hostd/sg_hostd/awg3_runtime.py').is_file()",
    1,
)
put(path, text)

# XMUX implementation stays AWG-agnostic; generic client exports may expose AWG3.
path = "tests/test_sg_gateway_v22_xmux_integration.py"
text = get(path)
text = text.replace(
    "def test_xmux_block_does_not_reintroduce_awg3() -> None:",
    "def test_xmux_block_stays_awg_agnostic_while_exports_support_awg3() -> None:",
    1,
)
text = text.replace(
    "        ROOT / 'app/web/static/sg-xmux-settings-v1.js',\n"
    "        ROOT / 'app/clients/exports.py',\n",
    "        ROOT / 'app/web/static/sg-xmux-settings-v1.js',\n",
    1,
)
text = text.replace(
    "    assert 'awg3' not in joined\n",
    "    assert 'awg3' not in joined\n"
    "    exports = (ROOT / 'app/clients/exports.py').read_text(encoding='utf-8')\n"
    "    assert 'def build_awg3_config' in exports\n",
    1,
)
put(path, text)

# SG Subscription v1 now has an independent AWG3 config profile.
path = "tests/test_sg_gateway_v22_sg_subscription_base64_body.py"
text = get(path)
text = text.replace(
    'def test_awg3_stays_out_of_canonical_schema() -> None:\n    assert "amneziawg3" not in subscription.canonical_profile_ids()\n',
    'def test_awg3_is_an_independent_canonical_config_profile() -> None:\n    assert "amneziawg3" in subscription.canonical_profile_ids()\n',
    1,
)
put(path, text)

path = "tests/test_sg_gateway_v22_sg_subscription_compat_text.py"
text = get(path)
text = text.replace(
    '    assert "amneziawg3" not in subscription.canonical_profile_ids()\n',
    '    assert "amneziawg3" in subscription.canonical_profile_ids()\n',
    1,
)
text = text.replace(
    '        "amneziawg", "mieru", "anytls", "tuic",\n',
    '        "amneziawg", "amneziawg3", "mieru", "anytls", "tuic",\n',
    1,
)
put(path, text)

path = "tests/test_sg_gateway_v22_sg_subscription_schema.py"
text = get(path)
text = text.replace(
    "def test_canonical_profile_ids_preserve_v1_order_without_awg3() -> None:",
    "def test_canonical_profile_ids_preserve_v1_order_with_independent_awg3() -> None:",
    1,
)
text = text.replace(
    '        "amneziawg",\n        "mieru",',
    '        "amneziawg",\n        "amneziawg3",\n        "mieru",',
    1,
)
text = text.replace(
    '    assert "amneziawg3" not in subscription.canonical_profile_ids()\n',
    '    assert "amneziawg3" in subscription.canonical_profile_ids()\n',
    1,
)
put(path, text)

# Focused contracts lock constructor compatibility and actual device picker support.
path = "tests/test_sg_gateway_v22_awg3_dual_contract.py"
text = get(path)
text += '''

def test_client_dataclass_keeps_pre_awg3_constructor_compatible():
    client = repository.Client(1, "Legacy", True, None, "applied", "applied")
    assert client.xray_status == "applied"
    assert client.awg3_status == "missing"


def test_device_picker_orders_both_awg_generations():
    body = Path("app/web/static/sg-device-collapse-v1.js").read_text(encoding="utf-8")
    assert "'amneziawg3'" in body
    assert "AmneziaWG 3.0" in body
    assert "UDP 586 · userspace-конфигурация и QR" in body
'''
put(path, text)

# No active Fix28 test may still require AWG3 to be absent globally.
stale = []
for path in Path("tests").glob("test_*.py"):
    body = path.read_text(encoding="utf-8").lower()
    if "assert 'amneziawg3' not in installer" in body:
        stale.append(str(path))
    if 'assert "amneziawg3" not in subscription.canonical_profile_ids()' in body:
        stale.append(str(path))
    if "assert not (root / 'hostd/sg_hostd/awg3_runtime.py').exists()" in body:
        stale.append(str(path))
if stale:
    raise SystemExit("stale Fix28 AWG3 exclusion assertions: " + ", ".join(sorted(set(stale))))

print("FIX29_CORRECTIONS_APPLIED")
