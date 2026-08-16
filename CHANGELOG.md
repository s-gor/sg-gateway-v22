# Changelog

## 0.1.0-022.04 — 2026-08-16

- Added optional Dual Stack IPv4 + IPv6 across public metadata, Xray listeners, exports, AWG2 and AWG3.
- Added isolated AWG3 3.x userspace runtime with independent IPv6 ULA space and lifecycle handling.
- Made WARP opt-in on clean install and added independent IPv4/IPv6 health with shared-core family gates.
- Added fail-closed Family Routing: SG-Gateway IPv4/IPv6, WARP IPv4/IPv6 and Block, with legacy IPv4 migration.
- Fixed default-traffic Block UI/backend mismatch.
- Hardened the updater to preserve TLS/HTTPS, AWG3 and runtime state with safety backup and rollback validation.
- Added SG subscription/device compatibility pipeline and accumulated client/device UX fixes.
- Added Hysteria2 Off/Salamander/Gecko cleanup and canonical URI handling.
- Added XHTTP XMUX presets/expert mode while keeping XMUX out of server inbound configuration.
- Expanded Full Backup verification/restore safety and panel-update state preservation.
- Added production WSGI/systemd contract and accumulated installer/diagnostic hardening.
- Added low-resolution desktop support that compacts without hiding actions.
- Added AWG3-aware full uninstall and 022.04 release-contract regression coverage.

# SG-Gateway 0.1.0-021.12 — Full Backup / Full Restore / Recovery

- R5-R3 PS1 archive EOL: `SOURCE-SHA256SUMS` hashes canonical LF Git blobs; four tracked `scripts/*.ps1` files previously had `eol=crlf`, so `git archive` exported different bytes and FULL CLEAN reported exactly four checksum mismatches. PS1 export is now fixed to LF; runtime code is unchanged.

- FINAL cumulative cleanup R5: active installer/uninstall identity aligned to 021.12; Light Update preserves local `/opt/sg-gateway/assets` and self-heals FIX9-R2 loss from Safety Backup without re-downloading the heavy asset tree; FULL CLEAN builds canonical committed Git HEAD; source SHA-256 is CI/build-run verified; FINAL AWG2 metadata points to `0.1.0-022.01`.

- FINAL AWG2 freeze: `0.1.0-021.12` закрыта как feature-frozen AWG2 baseline; requirements синхронизированы с 021.12, добавлен freeze-manifest. AWG3 перенесён в новую линию `0.1.0-022.01`.

- FIX9-R2: Light Update переведён с broad sparse checkout на runtime whitelist (`app/`, `hostd/`, `deploy/`). Тяжёлые `assets/geofiles`, `data`, `docs`, `tests`, `vendor` и `.github` больше не загружаются в panel-only Update.

- FIX9 Light Update: panel Update получает исходники через Git partial clone + sparse checkout без `vendor/cores`; Clean Install ставит Git, а старые серверы имеют compatibility fallback на полный archive.

- FIX8: dedicated Update no longer aborts after downloading GitHub main with `source: unbound variable`; candidate Python validation now receives `SOURCE_DIR` correctly.

- README и `docs/INSTALLATION.md` окончательно синхронизированы с двумя отдельными командами Clean Install / Update.
- На главную README вынесен блок быстрых команд: Clean Install, Update и Full Uninstall.
- Удалены оставшиеся устаревшие указания «для обновления используется та же команда».

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

---

# 0.1.0-021.12 — Full Restore published cumulative

- Published cumulative Full Backup/Restore and Domain Endpoint implementation from REBUILD-02.
- Full Restore preserves the destination session secret, rebuilds runtime on the destination server, restores local HTTPS certificates, reapplies all client engines, and validates runtime before success.
- During backend restart Nginx serves a static restart page instead of a raw 502, and the operation terminal offers an explicit panel reopen action.
- Xray restore keeps the accepted recursive 0777 access policy.
- Traffic/statistics remain excluded.

### 0.1.0-021.12 Full Restore final cumulative fix
- Full Restore reapplies `/usr/local/etc/xray` as recursive `0777`, requires `xray.service` active, refreshes HTTPS from restored local Let’s Encrypt files, reapplies all client runtimes, and only then reports success.
- Restore reports actual certificate validation, not only the presence of `/etc/letsencrypt`.
- Xray full-access policy is preserved by install/update, routing writes, TLS material sync, HTTPS refresh and client runtime regeneration.

# 0.1.0-021.12 — Full Backup/Restore + domain endpoint

- Добавлен переносимый полный `.sgbackup`: клиенты, ключи, Xray/AWG/Mihomo/sing-box, Routing/WARP, GeoFiles, Nginx и весь `/etc/letsencrypt`.
- Restore сохраняет публичный IP нового сервера и перед изменением создаёт safety backup.
- Restore выполняется фоновой HostD-задачей с живым терминалом и переживает перезапуск панели.
- Исправлены лимит загрузки/timeout Nginx, абсолютные symlink, вложенная история HTTPS-backup и права SQLite после восстановления.
- При рабочем HTTPS-домене клиентские QR/ссылки/конфиги используют домен; без HTTPS автоматически используется IP.
- Traffic/statistics и экспериментальные функции в релиз не включены.

## 0.1.0-021.10 full-clean retest

- HTTPS verification now waits for new Nginx workers instead of failing on a temporary ACME 404.
- The self-extracting installer uses a direct binary payload; the build reproduces and rechecks the transfer ZIP.
- Full uninstall removes the exact SG-Gateway stream include and the 021.10 resume file, then validates Nginx.
- Ubuntu package preparation shows live progress instead of an opaque spinner.

# 0.1.0-021.10 — единая clean-install база 80/443 и принятый интерфейс

- Порт 80 сразу обслуживает штатную страницу-заглушку; старый редирект на панель удалён из генератора установки.
- Публичный TCP 443 принадлежит Nginx stream/SNI router.
- Reality TCP работает через внутренний listener `127.0.0.1:7443` и сохраняет публичный порт 443.
- После выпуска сертификата обычный HTTPS на 443 направляется на заглушку через `127.0.0.1:7444`.
- Панель остаётся на отдельном настраиваемом порту, по умолчанию 63443.
- В исходники напрямую встроены принятые SUB URL, System FIX3, удаление точек Memory и Device Collapse V1+V4.
- Исторические серверные FIX не запускаются при чистой установке.
- Повторное применение на принятой конфигурации Nginx не добавляет второй include stream-файла и не дублирует listener 443.
- При ошибке установщик показывает настоящий контекст `FAILED COMMAND`, а не последний журнал службы после диагностики.

# SG-Gateway 0.1.0-021.10

- Встроена штатная страница-заглушка на TCP 80.
- Reality TCP перенесён на внутренний 127.0.0.1:7443 при сохранении публичного TCP 443.
- После выпуска сертификата Nginx stream/SNI разделяет Reality и обычный браузерный HTTPS на 443.
- Панель сохраняется на отдельном HTTPS-порту 63443.
- Сохранены принятые URL-подписки, System FIX3 и свёрнутые карточки устройств V1/V4.
- Все изменения встроены напрямую в исходники и чистую установку без цепочки старых FIX.

# 0.1.0-021.9 — клиенты, персональные подписки, QR и полный экспорт Mieru

## Клиенты и устройства

- Добавлено редактирование клиента: имя, срок действия и протоколы основного устройства.
- Добавлено отдельное редактирование дополнительных устройств: название, срок действия и протоколы.
- Поддержано изменение VLESS Reality TCP, VLESS XHTTP Reality, VLESS XHTTP TLS, Hysteria2, Mieru, AmneziaWG, AnyTLS и TUIC v5.
- Неизменённые UUID, пароли, токены, Mieru username/password и ссылки сохраняются без перевыпуска.
- Новые реквизиты создаются только для добавленных протоколов; удалённые протоколы корректно убираются.
- Изменения применяются транзакционно; при ошибке проверки или runtime выполняется автоматический откат.
- Для нового клиента или устройства рекомендованы VLESS Reality TCP, Mieru и персональная SUB.

## Персональная подписка устройства

- Для каждого устройства создан стабильный секретный токен и публичный URL `/sub/<token>` без авторизации панели.
- Существующим устройствам токены добавляются миграцией базы без замены рабочих реквизитов.
- Кнопка **«Скопировать ссылку»** копирует URL, а не внутреннее Base64-тело.
- Добавлен отдельный QR персональной SUB-ссылки.
- Исправлены настоящие переводы строк в декодированной подписке.
- Имя профиля формируется как `SG-Gateway · клиент · устройство` без `.txt`.
- В общую SUB входят только выбранные и готовые VLESS Reality TCP, Hysteria2, AnyTLS и TUIC v5.
- Mieru, AmneziaWG и XHTTP не смешиваются с общей Base64-подпиской ради совместимости импорта.

## Mieru и QR-коды

- Сохранена обычная ссылка `mierus://`, её копирование, скачивание и отдельный QR для SG Client.
- Добавлен отдельный UTF-8 Mieru JSON с фактическими адресом, портом и индивидуальными username/password устройства.
- Для Mieru JSON добавлены копирование, скачивание и отдельный **QR JSON**.
- JSON использует `MULTIPLEXING_MIDDLE`, `HANDSHAKE_STANDARD` и транспорт `TCP`.
- Обычный QR и JSON-QR существуют одновременно.
- Дополнительный экспорт Mihomo YAML сохранён.
- Сохранены QR и скачивание отдельных готовых профилей VLESS, Hysteria2, AnyTLS, TUIC v5 и AmneziaWG.

## Интерфейс клиента

- На странице клиента добавлены редактирование, добавление устройства, проверка доступов, включение, отключение и удаление.
- На дополнительных устройствах добавлены редактирование, включение, отключение и удаление.
- Персональная подписка вынесена в отдельный компактный блок над техническими профилями.
- На карточке устройства собраны SUB, QR подписки, копирование, QR и скачивание отдельных профилей.

## Мобильная версия

- Добавлена принятая полноширинная мобильная навигация до 760 px.
- Адаптированы подписи, иконки, логотип, карточка сервера, кнопки темы и выхода.
- Сворачивание полностью скрывает длинное меню без узкой боковой рейки.
- Убран горизонтальный выход страницы за экран.
- Desktop-разметка и desktop-поведение не изменены.

## Routing

- `Direct`, `WARP` и `Block` переименованы в «Через SG-Gateway», «Через WARP» и «Заблокировать».
- Внутренние Xray-теги `direct`, `warp` и `block` сохранены.
- Добавлено объяснение серверной маршрутизации и отличия от клиентского BYPASS.
- Скрыт лишний дублирующий блок российской маршрутизации.

## Внутренний контракт

- Добавлен публичный маршрут `/sub/<token>` и миграция стабильных токенов.
- Добавлены транзакционные методы обновления клиентов и устройств с сохранением credentials.
- Синхронизированы версия, release manifest, README, CHANGELOG и документация установки.
- Добавлен контракт 021.9 для подписок, Mieru URI/JSON, обоих QR, мобильной версии и безопасного редактирования.

# 0.1.0-021.8 — System, установка, клиенты и безопасное обновление

- Переработана страница System: добавлена детализация CPU, памяти, диска, процессов, данных, базы, логов, резервных копий и GeoFiles.
- Исправлен расчёт занятой, доступной, кэшированной и действительно свободной памяти.
- В Security возвращена смена пароля администратора прямо из панели.
- Чистая установка теперь запрашивает только пароль администратора и его подтверждение; технические параметры назначаются автоматически.
- После чистой установки автоматически создаётся первый VPN-клиент `sg-admin` с основными профилями и SG Client subscription.
- Обновлена страница Clients и окно создания клиента; SG Client больше не показывается как отдельный VPN-протокол.
- Для AnyTLS и TUIC v5 добавлено состояние «Будет включён после создания клиента с этим профилем».
- Удалены предварительные port-preflight проверки, которые могли ошибочно блокировать установку.
- Обновление из GitHub теперь сохраняет рабочие домен, сертификат Let’s Encrypt, HTTPS-конфигурацию Nginx и renewal hook.
- После обновления панель проверяется по сохранённому HTTPS-адресу; при ошибке используется транзакционный rollback.
- README обновлён новым описанием версии и актуальными скриншотами.

# 0.1.0-021.7 — Clients onboarding and protocol grid

- The Clients page now explains that `sg-admin` is the automatically created first VPN client, not a Linux/system user and not a panel login.
- The `sg-admin` note is shown only while that client exists; it tells the administrator to create personal clients and that `sg-admin` can be deleted after verification.
- The new-client dialog contains exactly eight selectable VPN protocol cards in a stable 4 × 2 desktop grid: four Xray profiles on the first row, then AmneziaWG, Mieru, AnyTLS and TUIC v5.
- `SG Client` is no longer a selectable protocol card; its subscription is still requested automatically as a hidden service value.
- TLS-dependent cards remain in place when unavailable and show `Требуется HTTPS`.
- Based strictly on the accepted 0.1.0-021.4 line; rejected 021.5/021.5.1/021.6 experiments are not merged.

# 0.1.0-021.4 — Hysteria2 Salamander exclusive UDP FinalMask

- Salamander is now the only live `streamSettings.finalmask.udp` layer while enabled.
- Existing/stored Hysteria2 UDP FinalMask masks are preserved in SG-Gateway state but suppressed from the live Xray config while Salamander is active.
- Disabling Salamander restores the exact stored base UDP FinalMask.
- Non-UDP FinalMask fields such as `tcp` and `quicParams` remain preserved.
- Existing full-candidate Xray validation and transactional rollback remain unchanged.
- Captured working live reference: Hysteria2 on UDP 8446 with exactly one `salamander` UDP FinalMask layer.
- Panel update availability now uses one normal user-facing message; internal updater-baseline/bootstrap terminology is no longer shown in the panel or update job output.

# 0.1.0-021.3 — Client QR display fix

- QR-коды клиента и QR подписки теперь открываются как отдельное окно поверх страницы.
- Исправлено обрезание QR рамкой страницы Clients (`overflow:hidden`).
- Backend и содержимое QR не изменялись: исправлено именно отображение уже успешно сгенерированного QR.

# 0.1.0-021.2 — HTTPS, Salamander diagnostics and split runtime Apply

- HTTPS setup no longer assumes `proxy_cookie_flags` support.
- Nginx 1.19.3+ keeps `proxy_cookie_flags`; Ubuntu Nginx 1.18 uses a compatible `proxy_cookie_path` fallback with Secure, HttpOnly and SameSite=Lax.
- Existing successful Let’s Encrypt certificate is reused on retry; rollback behavior is unchanged.
- Hysteria2 Salamander diagnostics no longer try to read the root-only Xray config from the web process; safe runtime truth is obtained through privileged HostD without exposing the password.
- Connections → Mieru / AnyTLS / TUIC v5 now applies the real split runtime: Mieru to Mihomo, AnyTLS and TUIC v5 to sing-box.
- The full requested form is validated before Apply, so enabling AnyTLS/TUIC without credentials or HTTPS gives a real error instead of staying silently in «Не применено».
- AnyTLS/TUIC sing-box runtime now uses the applied server ports/TUIC ALPN and updates client export endpoint fields only after successful runtime validation/restart.

# Changelog

## 0.1.0-021.2 · Panel updater bootstrap fix

- исправлена первая проверка/обновление из GitHub main после чистой установки, когда `panel-state.json` ещё не создан;
- первое обновление без baseline разрешается только на строго более новую `VERSION`, с полным backup и последующей привязкой к точному commit SHA;
- GitHub main получает fallback через публичный Atom feed / curl, если REST API временно недоступен;
- уже привязанный baseline с локально изменённым кодом по-прежнему блокирует автообновление.

## 0.1.0-021.2

- Connections: runtime status now reflects the real split engines: Mieru from Mihomo, AnyTLS and TUIC v5 from sing-box.
- The panel reads safe listener truth through privileged HostD without weakening root-only runtime configuration permissions.
- Runtime state (Работает/Ошибка/Выключен) is separated from pending form changes, so a working listener is no longer mislabeled «Не применено».

## 0.1.0-021

Первый стабильный публичный выпуск SG-Gateway.

- Нативная установка на Ubuntu без Docker.
- Xray: VLESS Reality TCP, VLESS XHTTP Reality, VLESS XHTTP TLS и Hysteria 2.
- AmneziaWG, Mihomo/Mieru, sing-box (AnyTLS и TUIC v5) и WARP.
- Клиенты, устройства, ссылки, QR-коды и единая SG Client subscription.
- Routing и транзакционное применение парных GeoFiles с family-aware системными правилами, сохранением пользовательских правил и автоматическим rollback.
- HTTPS с Let’s Encrypt и отдельным привилегированным HostD.
- Резервные копии, диагностика и независимые обновления панели и runtime-компонентов.
- Vendored runtime-комплект из шести проверяемых core-архивов для воспроизводимой чистой установки.
- Mihomo/Mieru готов к работе сразу после чистой установки и управляется из общей панели.
- Простое обновление GeoFiles: выбрать источник → проверить → обновить; подробная инструкция содержит реальные скриншоты.

## 0.1.0-021.10 · installer safety fix 1 (packaging only)

- Исправлена ложная ошибка `rc=141` в финальной проверке при `set -o pipefail`: `nginx -T` и `ss` больше не стоят перед `grep -q` в pipeline.
- После установки/восстановления Nginx сохраняется пакетный baseline `/etc/nginx` до SG-настроек; аварийный rollback восстанавливает его и больше не оставляет установленный Nginx без `nginx.conf`.
- Повторный clean install автоматически восстанавливает отсутствующий `/etc/nginx/nginx.conf` через `nginx-common`/`nginx` с `--force-confmiss`.
- Full uninstall не падает, если старый ошибочный rollback уже удалил `/etc/nginx/nginx.conf`; Nginx-проверка в таком состоянии безопасно пропускается.
- Версия приложения остаётся `0.1.0-021.10`; это исправление установочного комплекта, runtime работающих серверов не меняется.
