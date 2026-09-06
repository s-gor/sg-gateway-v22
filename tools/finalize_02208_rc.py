from pathlib import Path

EXACT = "cde152df4b957c254950e3b4a2276b76561653c9"

commands = f"""# SG-Gateway 0.1.0-022.08 · команды GitHub

Канал: `stable-02208`. Поддерживается Ubuntu 24.04.

## Чистая установка

Только для сервера без установленного SG-Gateway. Команда закреплена на проверенный исходный commit `{EXACT}`:

```bash
curl -4 -fsSL \\
  https://raw.githubusercontent.com/s-gor/sg-gateway-v22/{EXACT}/deploy/install-from-github.sh \\
| sudo env \\
  SG_GATEWAY_GITHUB_BRANCH=stable-02208 \\
  SG_GATEWAY_SOURCE_COMMIT={EXACT} \\
  bash
```

## Обновление

Для уже установленного SG-Gateway:

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/update-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```

## Полное удаление

Удаляются приложение, конфигурация, база, резервные копии, SG-службы и установленные SG runtime. Системные пакеты Ubuntu остаются установленными.

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/uninstall-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```

Для подтверждения необходимо ввести точно:

```text
DELETE SG-GATEWAY
```
"""
Path("deploy/GITHUB-COMMANDS.md").write_text(commands, encoding="utf-8")

public_test = f'''from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL_WRAPPER = ROOT / "deploy" / "install-from-github.sh"
UPDATE_WRAPPER = ROOT / "deploy" / "update-from-github.sh"
UNINSTALL_WRAPPER = ROOT / "deploy" / "uninstall-from-github.sh"
COMMANDS = ROOT / "deploy" / "GITHUB-COMMANDS.md"
INSTALL_SOURCE_COMMIT = "{EXACT}"

INSTALL_URL = (
    "https://raw.githubusercontent.com/s-gor/sg-gateway-v22/"
    f"{{INSTALL_SOURCE_COMMIT}}/deploy/install-from-github.sh"
)
UPDATE_COMMAND = (
    "curl -4 -fsSL "
    "https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/"
    "deploy/update-from-github.sh | sudo env "
    "SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash"
)
UNINSTALL_COMMAND = (
    "curl -4 -fsSL "
    "https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/"
    "deploy/uninstall-from-github.sh | sudo env "
    "SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash"
)


def test_public_github_commands_are_published():
    body = COMMANDS.read_text(encoding="utf-8")
    assert INSTALL_URL in body
    assert "SG_GATEWAY_GITHUB_BRANCH=stable-02208" in body
    assert f"SG_GATEWAY_SOURCE_COMMIT={{INSTALL_SOURCE_COMMIT}}" in body
    assert UPDATE_COMMAND in body
    assert UNINSTALL_COMMAND in body


def test_public_uninstall_wrapper_is_pinned_and_delegates_to_official_uninstaller():
    body = UNINSTALL_WRAPPER.read_text(encoding="utf-8")
    assert 'REPOSITORY="s-gor/sg-gateway-v22"' in body
    assert 'stable-02208' in body
    assert 'SG_GATEWAY_ALLOW_DEVELOPMENT' not in body
    assert 'stable uninstaller is pinned to stable-02208' in body
    assert 'archive/refs/heads/${{BRANCH}}.tar.gz' in body
    assert 'gzip -t "$ARCHIVE"' in body
    assert 'tar -xzf "$ARCHIVE"' in body
    assert 'deploy/full-uninstall-ubuntu.sh' in body
    assert 'bash "$UNINSTALLER"' in body
    assert 'DELETE SG-GATEWAY' not in body


def test_public_install_and_update_default_to_stable_channel():
    install = INSTALL_WRAPPER.read_text(encoding="utf-8")
    update = UPDATE_WRAPPER.read_text(encoding="utf-8")
    assert 'SG_GATEWAY_ALLOW_DEVELOPMENT' not in install
    assert 'stable installer is pinned to stable-02208' in install
    assert '${{SG_GATEWAY_UPDATE_BRANCH:-stable-02208}}' in install
    assert '${{SG_GATEWAY_UPDATE_BRANCH:-stable-02208}}' in update
'''
Path("tests/test_sg_gateway_v22_public_github_commands.py").write_text(public_test, encoding="utf-8")

old_readme = Path("README.md").read_text(encoding="utf-8")
marker = "## История предыдущих выпусков"
if marker not in old_readme:
    raise SystemExit("README history marker missing")
_, history_tail = old_readme.split(marker, 1)

top = f"""# SG-Gateway

**Лёгкая и быстрая веб-панель для личного и семейного VPN.**

> **Один сервер. Одна панель. Семейный VPN без серверной акробатики.**

![Версия](https://img.shields.io/badge/version-0.1.0--022.08-3b82f6)
![Ubuntu](https://img.shields.io/badge/Ubuntu-native-E95420?logo=ubuntu&logoColor=white)
![Xray](https://img.shields.io/badge/Xray-supported-2563EB)
![AmneziaWG](https://img.shields.io/badge/AmneziaWG-supported-6D5BD0)
![Mihomo](https://img.shields.io/badge/Mihomo-supported-8B5CF6)
![sing-box](https://img.shields.io/badge/sing--box-supported-0EA5E9)
![WARP](https://img.shields.io/badge/WARP-supported-F38020?logo=cloudflare&logoColor=white)
![systemd](https://img.shields.io/badge/deploy-systemd-16A085)
![HTTPS](https://img.shields.io/badge/HTTPS-Let%27s_Encrypt-003A70?logo=letsencrypt&logoColor=white)
![Status](https://img.shields.io/badge/status-022.08--STABLE-16A34A)

> **Актуальная версия — 0.1.0-022.08 STABLE.** Стабильный канал: `stable-02208`.

## Что нового в SG-Gateway 0.1.0-022.08

- Единый UI-контракт 22.08 для основных страниц панели.
- Согласованная геометрия Connections, Clients, Routing, Security, System, Maintenance и Outbounds.
- Login, Recovery, Help и Operation Job переведены на общий визуальный каркас.
- Browser geometry проверяется Chromium на desktop/tablet/mobile и в dark/light.
- Сохранены проверенные AWG 2.0, AWG 3.0, AWG 3.1, Xray, NaiveProxy, Backup/Restore и safe Update контракты.

Полное описание выпуска: **[SG-Gateway 0.1.0-022.08 — описание релиза](PUBLICATION-02208.md)**.

## Быстрые команды

### Clean Install — только новый сервер

```bash
curl -4 -fsSL \\
  https://raw.githubusercontent.com/s-gor/sg-gateway-v22/{EXACT}/deploy/install-from-github.sh \\
| sudo env \\
  SG_GATEWAY_GITHUB_BRANCH=stable-02208 \\
  SG_GATEWAY_SOURCE_COMMIT={EXACT} \\
  bash
```

### Update — существующий SG-Gateway

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/update-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```

### Full Uninstall — полное удаление SG-Gateway

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/uninstall-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```

Подтверждение удаления: `DELETE SG-GATEWAY`.

SG-Gateway устанавливается на один самостоятельный Ubuntu 24.04 сервер и превращает его в готовый VPN-шлюз с веб-интерфейсом.

## История предыдущих выпусков

<details>
<summary><strong>SG-Gateway 0.1.0-022.06</strong></summary>

Предыдущий стабильный выпуск сохранён в ветке `stable-02206`.

Полное описание: **[SG-Gateway 0.1.0-022.06 — описание релиза](PUBLICATION-02206.md)**.

</details>
"""
Path("README.md").write_text(top + history_tail.lstrip("\n"), encoding="utf-8")

publication_path = Path("PUBLICATION-02208.md")
publication = publication_path.read_text(encoding="utf-8").rstrip() + f"""

## Команды

### Clean Install

```bash
curl -4 -fsSL \\
  https://raw.githubusercontent.com/s-gor/sg-gateway-v22/{EXACT}/deploy/install-from-github.sh \\
| sudo env \\
  SG_GATEWAY_GITHUB_BRANCH=stable-02208 \\
  SG_GATEWAY_SOURCE_COMMIT={EXACT} \\
  bash
```

### Update

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/update-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```

### Full Uninstall

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/uninstall-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```
"""
publication_path.write_text(publication, encoding="utf-8")
