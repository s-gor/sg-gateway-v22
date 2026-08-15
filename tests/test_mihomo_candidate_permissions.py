from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_installer_precreates_mihomo_candidate_dir_for_panel():
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert '"$DATA_DIR/candidates" "$DATA_DIR/candidates/mihomo"' in text


def test_hostd_builds_mihomo_candidate_as_panel_user():
    text = (ROOT / "hostd/sg_hostd/client_runtime.py").read_text(encoding="utf-8")
    start = text.index('def _apply_mihomo()')
    end = text.index('\ndef _singbox_binary', start)
    block = text[start:end]
    assert '"runuser"' in block
    assert '"sg-gateway"' in block
    assert 'from app.mihomo.service import build_candidate; build_candidate()' in block
    assert 'from app.mihomo.service import build_candidate\n' not in block


def test_mihomo_candidate_io_errors_are_wrapped():
    text = (ROOT / "app/mihomo/service.py").read_text(encoding="utf-8")
    assert 'Не удалось подготовить каталог Mihomo candidate' in text
    assert 'Не удалось записать Mihomo candidate' in text
    assert 'Не удалось записать метаданные Mihomo candidate' in text
