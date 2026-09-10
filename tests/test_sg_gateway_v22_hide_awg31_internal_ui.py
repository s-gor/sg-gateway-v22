from pathlib import Path


def test_internal_awg31_hostname_is_not_rendered_in_global_shell() -> None:
    base = Path('app/web/templates/base.html').read_text(encoding='utf-8')
    assert 'server_identity.address' not in base


def test_literal_awg31_internal_is_not_user_visible_in_web_ui() -> None:
    roots = [Path('app/web/templates'), Path('app/web/static')]
    offenders: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob('*'):
            if not path.is_file():
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
            if 'awg31.internal' in text:
                offenders.append(str(path))
    assert offenders == [], f'awg31.internal remains user-visible in: {offenders}'
