from pathlib import Path


def test_sg_subscription_ui_labels_awg31_not_awg2() -> None:
    text = Path('app/web/templates/_sg_subscription_dual.html').read_text(encoding='utf-8')
    assert 'AmneziaWG 3.1' in text
    assert 'SG-CONFIG для AWG3.1' in text
    assert 'AmneziaWG 2.0' not in text
    assert 'SG-CONFIG для AWG2' not in text
