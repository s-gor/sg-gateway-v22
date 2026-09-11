from pathlib import Path


def _text_files(root: Path):
    if not root.exists():
        return
    for path in root.rglob('*'):
        if path.is_file():
            yield path


def test_internal_server_address_is_not_rendered_anywhere_in_user_templates() -> None:
    offenders: list[str] = []
    for path in _text_files(Path('app/web/templates')):
        text = path.read_text(encoding='utf-8', errors='ignore')
        if 'server_identity.address' in text:
            offenders.append(str(path))
    assert offenders == [], f'server_identity.address remains user-visible in: {offenders}'


def test_literal_awg31_internal_is_not_user_visible_in_web_ui() -> None:
    offenders: list[str] = []
    for root in (Path('app/web/templates'), Path('app/web/static')):
        for path in _text_files(root):
            text = path.read_text(encoding='utf-8', errors='ignore')
            if 'awg31.internal' in text:
                offenders.append(str(path))
    assert offenders == [], f'awg31.internal remains user-visible in: {offenders}'
