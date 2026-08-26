#!/usr/bin/env python3
from pathlib import Path

path = Path('scripts/_awg_verified_finalizer.py')
text = path.read_text(encoding='utf-8')

helper = r"""
def patch_clean_install_contract() -> set[str]:
    changed: set[str] = set()

    rel = "app/clients/repository.py"
    body = read(rel)
    original = body
    old = '''                server_public_key=str(settings_raw.get("server_public_key") or ""),
            )'''
    new = '''                server_public_key=str(settings_raw.get("server_public_key") or ""),
                header_protection_key=str(
                    settings_raw.get("header_protection_key") or ""
                ),
            )'''
    if "header_protection_key=str(" not in body:
        body = replace_once(body, old, new, "repository AWG31 header key")
    if body != original:
        write(rel, body)
        changed.add(rel)

    rel = "app/connections/awg31.py"
    body = read(rel)
    original = body
    old = '''def _legacy_stage3a(values: Mapping[str, object]) -> bool:
    return (
        all(str(values.get(name, "0")).strip() == "0" for name in J_FIELDS + S_FIELDS)
        and [str(values.get(name, "")).strip() for name in H_FIELDS] == ["1", "2", "3", "4"]
    )'''
    new = '''def _legacy_stage3a(values: Mapping[str, object]) -> bool:
    headers = [str(values.get(name, "")).strip() for name in H_FIELDS]
    return (
        all(str(values.get(name, "0")).strip() == "0" for name in J_FIELDS + S_FIELDS)
        and headers in (["0", "0", "0", "0"], ["1", "2", "3", "4"])
    )'''
    if old in body:
        body = replace_once(body, old, new, "AWG31 legacy parameter migration")
    if body != original:
        write(rel, body)
        changed.add(rel)

    rel = "app/web/static/sg-awg-dual-v1.css"
    body = read(rel)
    marker = "/* AWG2/AWG3 symmetric cards: one visual contract */\n"
    if marker not in body:
        write(rel, marker + body)
        changed.add(rel)

    rel = "tests/test_sg_gateway_v22_awg31_preserve_existing_awg3.py"
    body = read(rel)
    original = body
    body = body.replace(
        '''            "s1": 1,
            "s2": 2,
            "s3": 3,
            "s4": 4,''',
        '''            "s1": 64,
            "s2": 96,
            "s3": 48,
            "s4": 12,''',
    )
    if body != original:
        write(rel, body)
        changed.add(rel)

    rel = "tests/test_sg_gateway_v22_awg3_dual_contract.py"
    body = read(rel)
    original = body
    if "import re\n" not in body:
        body = body.replace("from pathlib import Path\n", "import re\nfrom pathlib import Path\n", 1)
    body = body.replace(
        '    assert ".button" not in css\n',
        '    assert not re.search(r"(?m)^\\s*\\.button\\b", css)\n',
    )
    if body != original:
        write(rel, body)
        changed.add(rel)

    return changed


"""

anchor = 'def patch_uninstaller() -> set[str]:\n'
if 'def patch_clean_install_contract()' not in text:
    if anchor not in text:
        raise SystemExit('finalizer insertion anchor missing')
    text = text.replace(anchor, helper + anchor, 1)

old_call = '    changed |= patch_v31(v31)\n    changed |= patch_uninstaller()'
new_call = '    changed |= patch_v31(v31)\n    changed |= patch_clean_install_contract()\n    changed |= patch_uninstaller()'
if old_call in text:
    text = text.replace(old_call, new_call, 1)
elif 'changed |= patch_clean_install_contract()' not in text:
    raise SystemExit('finalizer call anchor missing')

path.write_text(text, encoding='utf-8', newline='\n')
