# Установка и обновление SG-Gateway

> **0.1.0-021.12 = FINAL AWG2.** Версия зафиксирована как окончательная линия с AmneziaWG 2. AWG3 начинается только с `0.1.0-022.01`.

## Требования

- чистая Ubuntu Server 24.04;
- root-доступ через `sudo`;
- публичный IPv4;
- открытые в AWS Security Group порты используемых профилей.

SG-Gateway устанавливается нативно и не требует Docker.

## Установка из GitHub main

```bash
curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway/main/deploy/install-from-github.sh | sudo bash
```

Bootstrap загружает текущий `main`, проверяет обязательные файлы и запускает нативный `install.sh`.

## Схема чистой установки 021.10

Технические параметры назначаются автоматически:

- hostname `sg-gateway-<страна>`;
- панель `63443/TCP`;
- VLESS Reality `443/TCP`;
- AmneziaWG `585/UDP`;
- Reality target `www.bing.com:443`;
- Reality SNI `www.bing.com`.

Установщик задаёт только два связанных запроса:

1. пароль администратора панели;
2. повтор пароля.

Первый VPN-клиент `sg-admin` создаётся автоматически с профилями Reality TCP, XHTTP Reality, AmneziaWG и Mieru. После входа владелец создаёт собственных пользователей в разделе `Clients`.

Предварительная проверка портов установщиком временно отключена.

## Что делает установщик

1. ждёт освобождения apt/dpkg;
2. устанавливает системные зависимости;
3. определяет публичный IPv4 и страну;
4. автоматически назначает технические параметры;
5. запрашивает и хеширует пароль администратора;
6. создаёт `sg-admin`, пользователя и каталоги SG-Gateway;
7. устанавливает веб-панель, HostD и движки;
8. создаёт systemd-службы;
9. строит и проверяет runtime-конфигурации;
10. настраивает Nginx и UFW и показывает адрес панели.

Постоянный журнал очищается от паролей, приватных ключей, PEM-блоков и клиентских ссылок.

## Начальный доступ

Свежая установка открывается по HTTP и IP. HTTPS включается позднее из раздела `Security`.

## Обновление

Для уже установленного SG-Gateway используется отдельная команда:

```bash
curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway/main/deploy/update-from-github.sh | sudo bash
```

Clean Install и Update — разные операции. `install-from-github.sh` предназначен для чистого сервера и при обнаружении уже установленного SG-Gateway останавливается до изменения системы.

Update не запускает полный installer, не выполняет `apt-get` и не переустанавливает Nginx, Certbot, Xray, AmneziaWG, Mihomo, sing-box или WARP helper.

В обычном режиме Update исходники получаются через Git partial clone (`--depth=1 --filter=blob:none`) и **runtime whitelist**. В Light Update попадают `app/`, `hostd/`, `deploy/` и нужные root-файлы; `assets`, `data`, `docs`, `tests`, `vendor` и `.github` не загружаются. Если Git на старом сервере отсутствует или Light source недоступен, updater автоматически переходит на compatibility archive без установки пакетов.

Перед переключением кода создаётся safety backup, включая `/opt/sg-gateway`, `/etc/sg-gateway`, `/var/lib/sg-gateway`, полный `/etc/letsencrypt`, SG-конфигурацию Nginx и состояние служб. После обновления проверяются Clients/credentials, HTTPS, Nginx и ранее работающие runtime-службы. При ошибке выполняется автоматический rollback.

## Полное удаление

```bash
curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway/main/deploy/full-uninstall-ubuntu.sh | sudo bash
```

Подтверждение:

```text
DELETE SG-GATEWAY
```

Удаляются приложение, данные и управляемые SG-Gateway службы и конфигурации. Общие пакеты Ubuntu намеренно сохраняются.
