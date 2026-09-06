from pathlib import Path

ROOT = Path('.')


def replace_exact(path: str, old: str, new: str, *, count: int | None = None) -> None:
    p = ROOT / path
    text = p.read_text(encoding='utf-8')
    found = text.count(old)
    if found == 0:
        raise SystemExit(f'missing anchor in {path}: {old!r}')
    if count is not None and found != count:
        raise SystemExit(f'unexpected anchor count in {path}: {old!r}: {found} != {count}')
    p.write_text(text.replace(old, new), encoding='utf-8')
    print(f'{path}: {found} replacement(s)')


# Production release identity.
replace_exact('install.sh', 'VERSION="0.1.0-022.06"', 'VERSION="0.1.0-022.08"', count=1)
replace_exact('install.sh', 'INSTALLER_BUILD="02206-full-clean-dual-stack"', 'INSTALLER_BUILD="02208-full-clean-dual-stack"', count=1)
replace_exact('install.sh', 'INSTALL_LOG="/var/log/sg-gateway-installer-02206.log"', 'INSTALL_LOG="/var/log/sg-gateway-installer-02208.log"', count=1)
replace_exact('install.sh', 'RESUME_FILE="/root/sg-gateway-02206-installer-resume.env"', 'RESUME_FILE="/root/sg-gateway-02208-installer-resume.env"', count=1)
replace_exact('install.sh', 'before-sg-gateway-02206', 'before-sg-gateway-02208', count=2)
replace_exact('install.sh', 'Запускаю полный мастер SG-Gateway 0.1.0-022.06', 'Запускаю полный мастер SG-Gateway 0.1.0-022.08', count=1)
replace_exact('install.sh', 'Мастер установки SG-Gateway 0.1.0-022.06 запущен', 'Мастер установки SG-Gateway 0.1.0-022.08 запущен', count=1)

replace_exact('deploy/full-uninstall-ubuntu.sh', 'UNINSTALL_LOG="/var/log/sg-gateway-full-uninstall-02206.log"', 'UNINSTALL_LOG="/var/log/sg-gateway-full-uninstall-02208.log"', count=1)
replace_exact('deploy/full-uninstall-ubuntu.sh', 'SG-Gateway 0.1.0-022.06 · ПОЛНОЕ УДАЛЕНИЕ', 'SG-Gateway 0.1.0-022.08 · ПОЛНОЕ УДАЛЕНИЕ', count=1)

uninstaller = ROOT / 'deploy/full-uninstall-ubuntu.sh'
uninstall_text = uninstaller.read_text(encoding='utf-8')
old_cleanup = '    /root/sg-gateway-02206-installer-resume.env \\\n'
if old_cleanup not in uninstall_text:
    raise SystemExit('missing 02206 resume cleanup anchor')
uninstall_text = uninstall_text.replace(
    old_cleanup,
    old_cleanup + '    /root/sg-gateway-02208-installer-resume.env \\\n',
    1,
)
old_log_cleanup = '    /var/log/sg-gateway-installer-02112.log \\\n'
if old_log_cleanup not in uninstall_text:
    raise SystemExit('missing installer log cleanup anchor')
uninstall_text = uninstall_text.replace(
    old_log_cleanup,
    old_log_cleanup + '    /var/log/sg-gateway-installer-02206.log \\\n    /var/log/sg-gateway-installer-02208.log \\\n',
    1,
)
old_verify = '''  if [[ -e /root/sg-gateway-02206-installer-resume.env ]]; then
    echo "Остаток после удаления: /root/sg-gateway-02206-installer-resume.env" >&2
    bad=1
  fi
'''
if old_verify not in uninstall_text:
    raise SystemExit('missing 02206 residue verification anchor')
uninstall_text = uninstall_text.replace(
    old_verify,
    old_verify + '''  if [[ -e /root/sg-gateway-02208-installer-resume.env ]]; then
    echo "Остаток после удаления: /root/sg-gateway-02208-installer-resume.env" >&2
    bad=1
  fi
''',
    1,
)
uninstaller.write_text(uninstall_text, encoding='utf-8')

replace_exact(
    'app/maintenance/panel_updates.py',
    'GITHUB_BRANCH = os.getenv("SG_GATEWAY_UPDATE_BRANCH", "stable-02206").strip() or "stable-02206"',
    'GITHUB_BRANCH = os.getenv("SG_GATEWAY_UPDATE_BRANCH", "stable-02208").strip() or "stable-02208"',
    count=1,
)

# Tests that describe the current release must follow the current release.
replace_exact('tests/test_naiveproxy_development_identity_02207.py', 'assert (ROOT / "VERSION").read_text().strip() == "0.1.0-022.06"', 'assert (ROOT / "VERSION").read_text().strip() == "0.1.0-022.08"', count=1)
replace_exact('tests/test_naiveproxy_development_identity_02207.py', 'assert (ROOT / "DEVELOPMENT-VERSION").read_text().strip() == "0.1.0-022.07-dev"', 'assert (ROOT / "DEVELOPMENT-VERSION").read_text().strip() == "0.1.0-022.09-dev"', count=1)

hardening = ROOT / 'tests/test_sg_gateway_v22_02206_hardening.py'
hardening_text = hardening.read_text(encoding='utf-8')
hardening_text = hardening_text.replace('def test_stable_02206_identity_is_consistent() -> None:', 'def test_current_stable_identity_is_consistent() -> None:', 1)
hardening_text = hardening_text.replace('assert version == "0.1.0-022.06"', 'assert version == "0.1.0-022.08"', 1)
hardening_text = hardening_text.replace('assert build_id == "MAIN-02206-STABLE"', 'assert build_id == "MAIN-02208-STABLE"', 1)
hardening_text = hardening_text.replace('assert manifest["channel"] == "stable-02206"', 'assert manifest["channel"] == "stable-02208"', 1)
hardening_text = hardening_text.replace('assert manifest["maintenance_updates"]["panel"]["channel"] == "stable-02206"', 'assert manifest["maintenance_updates"]["panel"]["channel"] == "stable-02208"', 1)
hardening_text = hardening_text.replace('assert manifest["next_development_line"] == "0.1.0-022.07"', 'assert manifest["next_development_line"] == "0.1.0-022.09"', 1)
hardening.write_text(hardening_text, encoding='utf-8')

replace_exact('tests/test_sg_gateway_v22_clean_install_os_preflight.py', 'BOOTSTRAP_LOG="/var/log/sg-gateway-bootstrap-02206.log"', 'BOOTSTRAP_LOG="/var/log/sg-gateway-bootstrap-02208.log"', count=1)

replace_exact('tests/test_sg_gateway_v22_panel_update_channel.py', '# Stable releases track the immutable stable-02206 channel by default.', '# Stable releases track the immutable stable-02208 channel by default.', count=1)
replace_exact('tests/test_sg_gateway_v22_panel_update_channel.py', 'assert panel_updates.GITHUB_BRANCH == "stable-02206"', 'assert panel_updates.GITHUB_BRANCH == "stable-02208"', count=1)
replace_exact('tests/test_sg_gateway_v22_panel_update_channel.py', '${SG_GATEWAY_GITHUB_BRANCH:-${SG_GATEWAY_UPDATE_BRANCH:-stable-02206}}', '${SG_GATEWAY_GITHUB_BRANCH:-${SG_GATEWAY_UPDATE_BRANCH:-stable-02208}}', count=1)
replace_exact('tests/test_sg_gateway_v22_panel_update_channel.py', 'assert "stable-02206" in bootstrap', 'assert "stable-02208" in bootstrap', count=1)
replace_exact('tests/test_sg_gateway_v22_panel_update_state_binding.py', '${SG_GATEWAY_GITHUB_BRANCH:-${SG_GATEWAY_UPDATE_BRANCH:-stable-02206}}', '${SG_GATEWAY_GITHUB_BRANCH:-${SG_GATEWAY_UPDATE_BRANCH:-stable-02208}}', count=1)

# The public install pin is a current-release consistency contract, not a permanent 22.06 SHA.
label_test = ROOT / 'tests/test_sg_gateway_v22_clean_install_awg_label_contract.py'
label_test.write_text('''from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_clean_install_commands_pin_one_verified_02208_source_commit() -> None:
    commands = _read("deploy/GITHUB-COMMANDS.md")
    publication = _read("PUBLICATION-02208.md")
    readme = _read("README.md")
    match = re.search(
        r"https://raw\\.githubusercontent\\.com/s-gor/sg-gateway-v22/([0-9a-f]{40})/deploy/install-from-github\\.sh",
        commands,
    )
    assert match is not None
    commit = match.group(1)
    expected_url = f"https://raw.githubusercontent.com/s-gor/sg-gateway-v22/{commit}/deploy/install-from-github.sh"
    expected_source = f"SG_GATEWAY_SOURCE_COMMIT={commit}"
    for text in (commands, publication, readme):
        assert expected_url in text
        assert "SG_GATEWAY_GITHUB_BRANCH=stable-02208" in text
        assert expected_source in text


def test_clean_install_smoke_verifies_seeded_awg_subscription_labels() -> None:
    workflow = _read(".github/workflows/clean-install-awg3-smoke.yml")
    assert "Verify clean-install subscription labels" in workflow
    assert "from app.clients.sg_subscription import build_sg_subscription_text" in workflow
    assert '"amneziawg", "amneziawg3", "amneziawg31"' in workflow
    assert 'assert labels == ["sg-admin"] * 3' in workflow
    assert 'assert "sg-admin · Устройство" not in labels' in workflow
''', encoding='utf-8')

# Restore the user-facing documentation contract lost when the RC README was shortened.
readme = ROOT / 'README.md'
readme_text = readme.read_text(encoding='utf-8')
anchor = '## Быстрые команды\n'
if anchor not in readme_text:
    raise SystemExit('README quick commands anchor missing')
section = '''## Документация и возможности\n\n- **[Полная справка SG-Gateway 022.06](docs/SG-GATEWAY-02206-GUIDE.md)** — базовая эксплуатационная справка, актуальная для сохранённых runtime-контрактов.\n- **[Отличия 022.06 от 022.04](docs/CHANGES-02204-TO-02206.md)** — история функциональной линии до UI-релиза 22.08.\n- **[Техническое устройство SG-Gateway](docs/TECHNICAL.md)**.\n\n**Gateway — это просто выход в интернет. Без квантовой механики.**\n\nПоддерживаемые Xray-профили включают **VLESS Reality TCP + XTLS Vision**, **VLESS XHTTP Reality + XTLS Vision + VLESS Encryption** и **VLESS XHTTP TLS + XTLS Vision + VLESS Encryption**.\n\n### А где подсчёт трафика?\n\nSG-Gateway намеренно не превращён в биллинговую систему: основной акцент — Установка, Обновление, Полное удаление и надёжная эксплуатация VPN-шлюза.\n\n'''
if '## Документация и возможности\n' not in readme_text:
    readme_text = readme_text.replace(anchor, section + anchor, 1)
readme.write_text(readme_text, encoding='utf-8')

pub = ROOT / 'PUBLICATION-02208.md'
pub_text = pub.read_text(encoding='utf-8')
doc_block = '''\n## Документация\n\n- [Полная справка SG-Gateway 022.06](docs/SG-GATEWAY-02206-GUIDE.md) — базовые эксплуатационные и runtime-контракты, унаследованные 22.08.\n- [Отличия 022.06 от 022.04](docs/CHANGES-02204-TO-02206.md) — история функциональной линии.\n- [Техническое устройство SG-Gateway](docs/TECHNICAL.md).\n'''
if 'docs/SG-GATEWAY-02206-GUIDE.md' not in pub_text:
    pub_text = pub_text.replace('\n## Проверка выпуска\n', doc_block + '\n## Проверка выпуска\n', 1)
pub.write_text(pub_text, encoding='utf-8')

print('022.08 final identity hardening applied')
