from pathlib import Path


def fix_generated_contract_test() -> None:
    path = Path('tests/test_sg_gateway_v22_routing_contract_02208.py')
    text = path.read_text(encoding='utf-8')
    old = '''    for name in ('preset', 'local_action', 'russia_scope', 'russia_action', 'blocked_action', 'ads_action', 'default_action'):\n        assert f'name="{name}"' in ROUTING\n'''
    new = '''    for name in ('preset', 'russia_scope'):\n        assert f'name="{name}"' in ROUTING\n    assert 'name="{{ name }}"' in ROUTING\n    for name in ('local_action', 'russia_action', 'blocked_action', 'ads_action', 'default_action'):\n        assert f"action_group('{name}'" in ROUTING\n'''
    if old not in text:
        raise RuntimeError('obsolete literal Routing name assertions not found')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


if __name__ == '__main__':
    fix_generated_contract_test()
