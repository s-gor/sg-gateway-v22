# SG-Gateway 0.1.0-021.12 — FINAL AWG2

Статус: **FINAL AWG2 / feature-frozen**

Дата фиксации: 2026-08-09.

## Что означает FINAL

Версия `0.1.0-021.12` является окончательной линией SG-Gateway на AmneziaWG 2.

В `021.12` больше не добавляются новые функции, новые протоколы или AWG3.
Допустимы только критические исправления ошибок или безопасности без изменения
утверждённой архитектуры.

Следующая линия разработки: **`0.1.0-022.01`**, начиная с поддержки AWG3.

## Подтверждённый рабочий сценарий

На реальном сервере подтверждены:

- Clean Install;
- Full Restore из полного `.sgbackup`;
- рабочий HTTPS-домен;
- публичные подключения по домену;
- Safe Update 6/6;
- сохранение Clients/credentials;
- сохранение полного `/etc/letsencrypt`;
- сохранение Nginx;
- сохранение VPN runtime;
- Light Update без тяжёлых деревьев репозитория.

Наблюдавшийся Light Update:

```text
Git objects fetched: 676K
Checked-out source: 2.9M
```

## AmneziaWG

`021.12` фиксируется на поколении **AWG2**.

Clean Install baseline:

- AmneziaWG tools `1.0.20260618-2`;
- AmneziaWG kernel module `1.0.20260329-2`;
- DKMS `1.0.0`;
- UDP `585`.

AWG3 в этой версии не включается.

## Clean Install core baseline

- Xray `v26.6.27`;
- Mihomo `v1.19.29`;
- sing-box `1.13.14`;
- wgcf-cli `v0.3.6`;
- AmneziaWG 2 — версии выше.

Core Update остаётся отдельной Maintenance-операцией и не смешивается с
обновлением SG-Gateway.

## Обновление SG-Gateway

Update обновляет только приложение SG-Gateway.

Light source whitelist:

- `app/`;
- `hostd/`;
- `deploy/`;
- необходимые маленькие root-файлы.

Не загружаются:

- `assets/`;
- `data/`;
- `docs/`;
- `tests/`;
- `vendor/`;
- `.github/`.

Update не переустанавливает Nginx, Certbot, Xray, AmneziaWG, Mihomo, sing-box
или WARP helper.

**Local assets policy:** Light Update не скачивает `assets/` из GitHub и не удаляет уже установленный `/opt/sg-gateway/assets`. Целостность проверяется fingerprint. Для сервера, уже затронутого старым FIX9-R2, предусмотрено восстановление `assets` из предыдущего Safety Backup.

## Traffic

Traffic/statistics в `021.12` не добавляются.

## Команды

Clean Install:

```bash
curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway/main/deploy/install-from-github.sh | sudo bash
```

Update:

```bash
curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway/main/deploy/update-from-github.sh | sudo bash
```

Full Uninstall:

```bash
curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway/main/deploy/full-uninstall-ubuntu.sh | sudo bash
```

---

**021.12 закрыта как FINAL AWG2. AWG3 начинается только с 022.01.**
