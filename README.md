# SG-Gateway

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
- Большой performance-pass по Clients, client detail, Connections, Routing, System, Maintenance, Recovery и общей навигации.
- Убраны N+1-запросы, повторные credentials/settings reads и лишние тяжёлые health/runtime probes.
- Обычная навигация больше не запускает полный health scan; полная диагностика остаётся на специальных страницах.
- **AWG 3.1 — текущий активный AmneziaWG runtime.** Legacy AWG 2.0/AWG 3.0 runtime выведен из эксплуатации штатной cleanup-логикой.
- Сохранены Xray, NaiveProxy, Mihomo/sing-box, WARP, Backup/Restore и safe Update/rollback контракты.

Полное описание выпуска: **[SG-Gateway 0.1.0-022.08 — описание релиза](PUBLICATION-02208.md)**.

## Быстрые команды

### Clean Install — только новый сервер

```bash
curl -4 -fsSL \
  https://raw.githubusercontent.com/s-gor/sg-gateway-v22/6d8b07125289566a6e8a7ba206094d8969e92125/deploy/install-from-github.sh \
| sudo env \
  SG_GATEWAY_GITHUB_BRANCH=stable-02208 \
  SG_GATEWAY_SOURCE_COMMIT=6d8b07125289566a6e8a7ba206094d8969e92125 \
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

Полный и актуальный набор публичных команд: **[deploy/GITHUB-COMMANDS.md](deploy/GITHUB-COMMANDS.md)**.

## Документация

- **[Описание выпуска 022.08](PUBLICATION-02208.md)**
- **[Полная справка SG-Gateway 022.06](docs/SG-GATEWAY-02206-GUIDE.md)** — базовая эксплуатационная справка для унаследованных функций.
- **[Техническое устройство SG-Gateway](docs/TECHNICAL.md)**
- **[Начало работы](docs/README.md)**
- **[Установка и обновление](docs/INSTALLATION.md)**
- **[Руководство пользователя](docs/USER-GUIDE.md)**
- **[Connections и клиентские профили](docs/CONNECTIONS.md)**
- **[Routing и GeoFiles](docs/ROUTING.md)**
- **[HTTPS и безопасность](docs/security.md)**
- **[Maintenance и диагностика](docs/MAINTENANCE.md)**
- **[Полное удаление](docs/UNINSTALL.md)**

## Основные возможности

SG-Gateway устанавливается на один самостоятельный Ubuntu 24.04 VPS/EC2 и превращает его в готовый VPN-шлюз с веб-интерфейсом.

Поддерживаются современные Xray-профили, включая **VLESS Reality TCP + XTLS Vision**, **VLESS XHTTP Reality + XTLS Vision + VLESS Encryption** и **VLESS XHTTP TLS + XTLS Vision + VLESS Encryption**, а также AWG 3.1, Mieru, AnyTLS, TUIC v5 и WARP routing.

Панель управляет клиентами и устройствами, персональными subscriptions, QR/exports, Routing/GeoFiles, HTTPS/Let's Encrypt, backup/restore, diagnostics и безопасными обновлениями.

### Clients

Клиент может иметь несколько устройств. Для каждого устройства сохраняются собственные credentials, ссылки, QR-коды и персональная SG Client subscription.

### Routing и GeoFiles

Доступны прямой выход через SG-Gateway, WARP IPv4/IPv6, блокировка, готовые и пользовательские правила. GeoFiles можно проверять и обновлять из панели.

### HTTPS и безопасность

HTTPS включается из `Security`. Панель проверяет DNS, получает сертификат Let's Encrypt, валидирует Nginx и проверяет итоговый endpoint. Привилегированные операции выполняет отдельный HostD.

### Backup / Restore

Поддерживаются обычные и полные резервные копии. Перед критическими переключениями создаётся safety backup; при ошибке применяется rollback.

### Update

Clean Install и Update разделены. Update не переустанавливает системные пакеты и не выполняет повторный полный installer. Он обновляет исходники по безопасной транзакционной схеме и проверяет состояние сервера после переключения.

## Для кого создан SG-Gateway

SG-Gateway подходит, когда нужен собственный VPN на одном сервере для себя, семьи или небольшой группы без Controller/Cluster/Cascade и без серверной акробатики.

Для многоузловой инфраструктуры существует отдельный проект SG-Panel.

> **SG-Panel — для сложной инфраструктуры.**  
> **SG-Gateway — для дома, семьи и спокойной жизни.**

## История выпусков

Предыдущие стабильные линии сохранены отдельными ветками:

- `stable-02206` — SG-Gateway 0.1.0-022.06;
- `stable-02204` — SG-Gateway 0.1.0-022.04.

Исторические описания выпусков остаются в репозитории.

**Один сервер. Одна панель. Нормальный выход в интернет.**
