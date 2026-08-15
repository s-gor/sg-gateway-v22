# SG-Gateway 0.1.0-021.12 — Full Backup / Full Restore / Recovery

> **FINAL AWG2 / feature-frozen.** `0.1.0-021.12` — окончательная линия AmneziaWG 2. Новые функции и AWG3 в 021.12 не добавляются; следующая линия — `0.1.0-022.01`.

SG-Gateway 0.1.0-021.12 — целевая рабочая версия без Traffic/statistics и без новых экспериментальных функций.

Главное изменение этой линии — SG-Gateway теперь можно не только установить и настроить, но и **перенести на новый чистый Ubuntu-сервер либо восстановить после серьёзной аварии как целую систему**.

## Две разные команды: Clean Install и Update

После реального теста обновления установка и обновление окончательно разделены.

### CLEAN INSTALL — только новый сервер

```bash
curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway/main/deploy/install-from-github.sh | sudo bash
```

Clean Install предназначен только для новой Ubuntu. Он устанавливает системные пакеты, Nginx, Certbot, Xray, AmneziaWG, Mihomo, sing-box, WARP helper, systemd-службы и первоначальный runtime.

Если SG-Gateway уже установлен, Clean Install **останавливается и ничего не меняет**. Для существующего сервера нужно использовать отдельную команду Update.

### UPDATE — только существующий SG-Gateway

```bash
curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway/main/deploy/update-from-github.sh | sudo bash
```

Update больше не является повторным полным installer.

**Light Update:** Git получает только runtime whitelist `app/`, `hostd/`, `deploy/` и маленькие root-файлы. `assets/`, `data/`, `docs/`, `tests/`, `vendor/` и `.github/` из GitHub не скачиваются.

При этом уже установленный `/opt/sg-gateway/assets` сохраняется локально и проверяется fingerprint до/после Update. Если старый FIX9-R2 уже удалил `assets`, Update пытается восстановить их из предыдущего Safety Backup. Сетевой повторной загрузки тяжёлого asset-дерева нет.

Он выполняет шесть отдельных этапов:

```text
[1/6] Проверка установленного SG-Gateway и HTTPS
[2/6] Safety Backup: SG state + полный /etc/letsencrypt
[3/6] Обновление только исходников SG-Gateway
[4/6] Python/UI проверка без изменения runtime
[5/6] Перезапуск только panel + hostd
[6/6] Проверка HTTPS, Clients, Nginx и runtime
```

Обычный Update **не устанавливает заново** Nginx, Certbot, Xray, AmneziaWG, Mihomo, sing-box или WARP helper и не пересобирает рабочие VPN runtime-конфигурации.

До переключения кода создаётся safety backup. Отдельно фиксируются состояние Clients/credentials, полный `/etc/letsencrypt`, SG-конфигурация Nginx и состояние runtime-служб.

После обновления проверяется, что:

- Clients и credentials не изменились;
- `/etc/letsencrypt` не изменился;
- конфигурация Nginx не изменилась;
- ранее работающие VPN runtime-службы остались в том же состоянии;
- панель и HostD снова работают;
- рабочий HTTPS-домен отвечает по прежнему адресу.

Если любая из этих проверок не проходит, Update автоматически возвращает pre-update safety backup.

Обновление VPN cores остаётся отдельной операцией в Maintenance и не смешивается с обновлением самой панели.

---

## Full Backup — не только SQLite

Полный backup SG-Gateway — это переносимый файл `.sgbackup`.

В него входят не только записи клиентов, но и необходимые данные всей установленной системы SG-Gateway:

- база SG-Gateway;
- клиенты, устройства, UUID и credentials;
- ключи и protocol state;
- Xray;
- AmneziaWG;
- Mihomo;
- sing-box;
- Routing;
- WARP state;
- GeoFiles;
- SG-конфигурация Nginx;
- полный `/etc/letsencrypt` с сертификатами и renewal state.

Перед созданием полного архива SQLite снимается согласованным snapshot и проверяется на целостность.

В backup намеренно не переносятся временные job-файлы, история самих backup-файлов и другой transient runtime-мусор.

## Перенос на новый сервер

Проверенный сценарий выглядит так:

1. На старом сервере создать **Full Backup** и скачать `.sgbackup`.
2. Создать новый VPS/EC2 с чистой Ubuntu.
3. Выполнить **Clean Install** SG-Gateway.
4. Открыть **Maintenance → Full Restore**.
5. Загрузить `.sgbackup`.
6. Дождаться завершения фоновой операции Restore.

Full Restore сначала проверяет безопасность архива и SQLite внутри него.

До замены данных новый сервер автоматически создаёт собственный safety backup.

После этого восстанавливаются клиенты, credentials, ключи, сертификаты, GeoFiles, WARP и сохранённые настройки.

## Старый runtime не копируется вслепую

Это принципиальная часть Full Restore.

Восстановленный runtime старого сервера не считается конечной конфигурацией нового сервера.

SG-Gateway восстанавливает исходные данные и **заново генерирует runtime уже на новом сервере**.

Это позволяет сохранить новый public IP сервера и не протащить в новый runtime старый адрес VPS.

## Домен — единый public endpoint

Если после Restore существует рабочий HTTPS-домен, он используется как public endpoint для всех публичных подключений:

- AmneziaWG;
- VLESS Reality TCP;
- VLESS XHTTP Reality;
- VLESS XHTTP TLS;
- Hysteria2;
- Mieru URI;
- Mieru JSON;
- Mihomo YAML;
- AnyTLS;
- TUIC v5;
- subscription;
- QR-коды, которые строятся из этих payload.

Если рабочего HTTPS-домена нет, используется текущий IP нового сервера как fallback.

## HTTPS и сертификаты тоже восстанавливаются

Full Restore возвращает Let's Encrypt state и сертификаты, проверяет их и заново подключает к конфигурации нового сервера.

Не требуется вручную копировать `fullchain.pem`, private key или заново собирать HTTPS-конфигурацию.

После Restore SG-Gateway проверяет Nginx и рабочий HTTPS endpoint.

## Runtime пересобирается и проверяется

После восстановления состояния SG-Gateway заново применяет необходимые runtime-конфигурации.

Проверяются Xray, AmneziaWG, Mihomo/Mieru, AnyTLS, TUIC и связанные клиентские exports/subscriptions.

Для Nginx выполняется конфигурационная проверка. Xray candidate проверяется самим Xray. AWG также проходит собственную проверку.

Restore сообщает успех только после завершения runtime rebuild и финальных проверок.

## Full Restore работает как фоновая транзакция

Большой Restore не зависит от одного долгого HTTP-запроса браузера.

Он запускается как отдельная HostD operation и показывает ход восстановления:

```text
[Full Restore] Фоновая транзакция запущена
[Restore 1/7] Проверяю структуру и безопасность .sgbackup
[Restore 2/7] Backup и SQLite проверены
[Restore 3/7] Создаю страховочный полный backup текущего сервера
[Restore 4/7] Восстанавливаю клиентов, ключи, runtime, HTTPS и сертификаты
[Restore 5/7] Проверяю SQLite и исходные данные; runtime будет создан заново
[Restore 6/7] Возвращаю локальный HTTPS и пересобираю все протоколы на новом сервере
[Restore 6/7] Адрес панели после переключения: https://<domain>:<port>
[Restore 7/7] Full Restore завершён: runtime пересобран на новом сервере
```

Во время переключения backend может быть перезапущен. Вместо обычного сырого `502 Bad Gateway` SG-Gateway использует специальную restart page и после запуска backend возвращает панель.

Session secret нового сервера сохраняется, поэтому обычный restart панели во время Full Restore сам по себе не должен выбрасывать администратора из текущей сессии.

## Recovery Mode

SG-Gateway имеет отдельную минимальную аварийную страницу `/recovery`.

Она показывает:

- общее состояние SG-Gateway;
- health checks;
- последние резервные копии;
- скачивание backup;
- восстановление выбранной копии;
- быстрый переход в Maintenance и обратно в панель.

Recovery намеренно проще основной панели.

Перед обычным Recovery restore автоматически создаётся страховочная копия. Если восстановленный Xray runtime не применяется, SG-Gateway пытается вернуть предыдущую базу и прежний runtime.

Важно различать два механизма:

- **Recovery** — быстрый аварийный restore внутренних backup;
- **Maintenance → Full Restore** — перенос/восстановление всего SG-Gateway из `.sgbackup`.

## Защита от неудачного Restore

Full Restore рассчитан и на ошибочный сценарий.

Перед серьёзным переключением состояния создаётся safety backup.

Временные `security/jobs` и история backup не переносятся поверх активной операции, поэтому текущий Restore не должен затереть собственный журнал старым состоянием сервера.

Если критическая проверка не проходит, SG-Gateway выполняет rollback вместо ложного сообщения об успехе.

---

## Что проверено реально

Сценарий был проверен на новом сервере:

```text
чистая Ubuntu
→ Clean Install из GitHub main
→ загрузка .sgbackup
→ Full Restore
→ восстановление HTTPS
→ восстановление клиентов и ключей
→ runtime rebuild
→ public endpoints по домену
→ рабочие клиентские подключения
```

Именно поэтому Full Restore в 0.1.0-021.12 рассматривается не как обычный «экспорт базы», а как механизм восстановления SG-Gateway на новом сервере.

Traffic/statistics в эту версию не включались.
