# Техническое устройство SG-Gateway

Этот документ предназначен для пользователя, который понимает термины `inbound`, `outbound`, REALITY, TLS, XHTTP, systemd и Nginx, но не обязан изучать исходный код панели.

Линия документации: **SG-Gateway 021**
Версия приложения: **`0.1.0-021.7`**

## 1. Архитектурная граница

SG-Gateway управляет одним самостоятельным Ubuntu-сервером.

```text
Клиентские приложения
        |
        +-- Xray inbounds
        +-- AmneziaWG
        +-- Hysteria 2
        +-- Mihomo listeners
        |
        v
     Routing
        |
        +-- Direct
        +-- WARP
        +-- Block
        |
        v
     Интернет
```

В архитектуре отсутствуют:

- Controller;
- SG-Nodes;
- Cluster;
- Cascade;
- межсерверная оркестрация;
- распределённая клиентская база;
- редактор полного итогового JSON.

Панель собирает управляемые конфигурации из проверенных параметров интерфейса.

## 2. Основные компоненты

| Компонент | Назначение |
|---|---|
| Nginx | Публичный HTTP/HTTPS-доступ к панели |
| SG-Gateway | Веб-интерфейс и непривилегированная бизнес-логика |
| HostD | Отдельное выполнение разрешённых привилегированных операций |
| Xray-core | VLESS Reality, XHTTP и Hysteria 2 |
| AmneziaWG | WireGuard-совместимый семейный VPN-профиль |
| Mihomo Core | Mieru |
| sing-box | AnyTLS и TUIC v5 |
| WARP helper | Подготовка WARP-outbound |
| SQLite | Клиенты, устройства и состояние панели |
| systemd | Управление службами и их жизненным циклом |

Веб-процесс не должен напрямую выполнять произвольные root-команды.

## 3. Размещение файлов

```text
/opt/sg-gateway
    приложение, шаблоны, статика и Python-окружение

/etc/sg-gateway
    параметры установки и секреты движков

/var/lib/sg-gateway
    SQLite, runtime-state, TLS-state и рабочие данные

/var/log/sg-gateway
    журналы панели и операций
```

Закрытые ключи Let’s Encrypt находятся в системных каталогах Certbot и не читаются обычным веб-процессом.

## 4. Системные службы

Основные unit:

```text
sg-gateway.service
sg-hostd.service
xray.service
sg-gateway-awg.service
mihomo.service
sg-gateway-singbox.service
nginx.service
```

Пользовательский VPN-трафик обслуживается отдельными движками. Перезапуск веб-интерфейса сам по себе не должен останавливать уже работающие Xray, AmneziaWG или Mihomo-подключения.

## 5. Матрица Xray-профилей

| Профиль | Транспорт | Защита | Flow | VLESS Encryption | XMUX | Домен |
|---|---|---|---|---|---|---|
| VLESS Reality TCP | TCP | REALITY | `xtls-rprx-vision` | Нет, `encryption=none` | Нет | Не требуется |
| VLESS XHTTP Reality | XHTTP | REALITY | `xtls-rprx-vision` | Да | Да | Не требуется |
| VLESS XHTTP TLS | XHTTP | TLS | `xtls-rprx-vision` | Да | Да | Требуется |
| Hysteria 2 | QUIC/UDP | TLS | Не применяется | Не применяется | Не применяется | Требуется |

## 6. XTLS Vision

Для VLESS-профилей SG-Gateway использует:

```text
flow=xtls-rprx-vision
```

Vision относится к потоку VLESS-клиента и не является заменой TLS, REALITY или VLESS Encryption.

В SG-Gateway Vision применяется к:

- VLESS Reality TCP;
- VLESS XHTTP Reality;
- VLESS XHTTP TLS.

Классический Reality TCP использует:

```text
encryption=none
flow=xtls-rprx-vision
type=tcp
security=reality
```

Значение `encryption=none` здесь является нормальной частью классического VLESS Reality TCP и не означает отсутствие REALITY или Vision.

## 7. VLESS Encryption

VLESS Encryption используется двумя XHTTP-профилями:

- XHTTP Reality;
- XHTTP TLS.

SG-Gateway хранит связанную пару:

- клиентское значение `encryption`;
- серверное значение `decryption`.

Пара создаётся с ML-KEM-768, нормализуется и проверяется установленным Xray до сохранения.

Серверный inbound получает:

```json
{
  "settings": {
    "clients": [],
    "decryption": "<server value>"
  }
}
```

Клиентская ссылка получает:

```text
encryption=<client value>
```

Профиль XHTTP не считается готовым, если корректная пара VLESS Encryption отсутствует. Пользователю не нужно копировать значения между сервером и клиентом вручную.

### Важно

VLESS Encryption, XTLS Vision и TLS/REALITY решают разные задачи:

- `Vision` — flow VLESS;
- `TLS` или `REALITY` — защита транспорта;
- `VLESS Encryption` — связанная клиентская и серверная криптографическая пара для XHTTP.

## 8. XHTTP

Серверные XHTTP-inbound собираются с режимом:

```text
mode=auto
```

Клиентский режим хранится отдельно в профиле.

Текущие значения по умолчанию:

- XHTTP Reality: `stream-one`;
- XHTTP TLS: `auto`.

Панель поддерживает допустимые режимы XHTTP из интерфейса и передаёт выбранное значение в клиентскую ссылку.

### XHTTP Reality

Клиентская ссылка содержит:

```text
type=xhttp
security=reality
flow=xtls-rprx-vision
encryption=<client VLESS Encryption>
path=<profile path>
mode=<client mode>
extra={"xmux":{...}}
```

Дополнительно используются Reality Public Key, ShortID, SNI и fingerprint.

### XHTTP TLS

Клиентская ссылка содержит:

```text
type=xhttp
security=tls
flow=xtls-rprx-vision
encryption=<client VLESS Encryption>
sni=<panel domain>
alpn=h2
path=<profile path>
mode=<client mode>
extra={"xmux":{...}}
```

Профиль доступен только при готовом HTTPS-состоянии.

## 9. XMUX для российских сетей

XMUX постоянно добавляется к обоим XHTTP-профилям:

```json
{
  "maxConcurrency": 0,
  "maxConnections": 6,
  "cMaxReuseTimes": 0,
  "hMaxRequestTimes": "600-900",
  "hMaxReusableSecs": "1800-3000",
  "hKeepAlivePeriod": 0
}
```

XMUX является клиентской частью ссылки:

```json
{
  "extra": {
    "xmux": {}
  }
}
```

Он не добавляется в серверный inbound Xray.

В интерфейсе нет отдельного переключателя: это встроенный профиль SG-Gateway для XHTTP. Параметры можно просмотреть, но пользователю не требуется включать их вручную.

## 10. Reality

REALITY-профили используют:

- private/public key pair;
- ShortID;
- server name;
- destination;
- fingerprint;
- XTLS Vision.

Private key остаётся на сервере. Клиентские ссылки получают public key и ShortID.

## 11. Hysteria 2

Hysteria 2 работает через Xray с TLS и UDP/QUIC.

Поддерживаются:

- TLS-сертификат домена;
- клиентская авторизация;
- Salamander;
- FinalMask;
- проверка candidate-конфигурации до применения.

TLS-профиль Hysteria 2 требует готового домена и сертификата.

## 12. AmneziaWG

SG-Gateway использует фиксированный внешний порт:

```text
UDP 585
```

Каждое устройство получает отдельные ключи и адрес. Панель управляет серверной конфигурацией и клиентскими файлами, но не смешивает AmneziaWG с Xray JSON.

## 13. Mihomo и sing-box

Рабочая схема разделяет дополнительные протоколы:

| Протокол | Движок | Транспорт |
|---|---|---|
| Mieru | Mihomo | TCP или UDP |
| AnyTLS | sing-box | TCP + TLS |
| TUIC v5 | sing-box | UDP + TLS |

`clients.apply` считает критическими только AmneziaWG и Xray. Mihomo,
sing-box и формирование SG Client subscription выполняются отдельно и
возвращают предупреждение, но не откатывают изменение клиента либо всю
установку панели.

Сертификаты Mihomo при необходимости хранятся внутри разрешённого каталога:

```text
/var/lib/mihomo/tls/fullchain.pem
/var/lib/mihomo/tls/privkey.pem
```

Клиентские ссылки строятся из сохранённых и применённых реквизитов. Они не
зависят от мгновенного результата проверки порта сразу после перезапуска
службы.

## 14. Outbounds

Основные действия:

```text
Direct
WARP
Block
```

`Direct` отправляет трафик напрямую.
`WARP` направляет выбранный трафик через Cloudflare WARP.
`Block` запрещает соединение.

WARP является outbound, а не отдельным типом Routing-правила.

## 15. Routing

Панель формирует управляемые правила для доменов, IP и Geo-категорий.

Перед применением:

1. строится полная будущая конфигурация;
2. выполняется проверка ссылок на GeoFiles;
3. Xray тестирует candidate;
4. только после успеха меняется live-состояние;
5. при ошибке сохраняется предыдущая рабочая конфигурация.

Отсутствующая Geo-категория блокирует применение. SG-Gateway не удаляет пользовательские правила автоматически.

## 16. GeoFiles

GeoFiles применяются парой:

```text
geoip.dat
geosite.dat
```

Источники включают:

- встроенную пару SG Client;
- Loyalsoldier;
- RunetFreedom;
- RoscomVPN;
- пользовательские HTTPS-адреса;
- загруженную пару;
- локальные пути сервера.

Панель показывает размер, дату и SHA-256, проверяет категории и создаёт резервные копии.

## 17. HTTPS

Публичная панель по умолчанию использует порт:

```text
63443
```

Внутренний backend:

```text
127.0.0.1:18080
```

HTTPS-транзакция выполняется привилегированным процессом и включает:

1. DNS-проверку;
2. получение или обновление сертификата;
3. резервную копию Nginx и TLS-state;
4. генерацию candidate-конфигурации Nginx;
5. `nginx -t`;
6. переключение доступа;
7. проверку backend;
8. проверку внешнего HTTPS;
9. rollback при ошибке.

Веб-интерфейс читает только безопасное состояние сертификата, а не закрытый ключ.

## 18. Порты

Основные значения по умолчанию:

| Назначение | Порт |
|---|---|
| Публичная панель | TCP `63443` |
| Backend панели | TCP `18080`, localhost |
| VLESS Reality TCP | TCP `443` |
| VLESS XHTTP Reality | TCP `8444` |
| VLESS XHTTP TLS | TCP `8445` |
| Hysteria 2 | UDP `8446` |
| AmneziaWG | UDP `585` |

Порты Xray и Mihomo проверяются на конфликты перед применением. Значения профилей, кроме архитектурно фиксированных, могут изменяться через интерфейс.

## 19. Клиенты и устройства

SQLite хранит клиента отдельно от его устройств.

Устройство содержит собственные реквизиты и выбранные deployments:

- Xray Reality TCP;
- XHTTP Reality;
- XHTTP TLS;
- Hysteria 2;
- AmneziaWG;
- Mieru;
- AnyTLS;
- TUIC v5.

Экспорт может формировать:

- URI;
- QR-код;
- файл конфигурации;
- SG Client subscription.

Отключение клиента или устройства не требует удаления записи.

## 20. Сохранность при обновлении

Штатное обновление использует тот же GitHub installer, что и новая установка.

Перед изменениями сохраняются:

- SQLite;
- управляемые конфигурации;
- ключи Reality;
- VLESS Encryption;
- TLS-state;
- данные клиентов;
- настройки Routing и GeoFiles;
- состояние дополнительных движков.

После установки выполняются проверки служб и конфигураций. При ошибке предусмотрен rollback.

## 21. Резервные копии и диагностика

Maintenance предоставляет:

- создание копии;
- просмотр доступных копий;
- восстановление;
- системные журналы;
- диагностику служб;
- проверку конфигурации;
- обновление компонентов.

Привилегированные операции выполняются через ограниченный HostD-контур.

## 22. Учёт трафика

Персональный учёт трафика клиентов в линии 021 отсутствует.

Панель не создаёт:

- месячные лимиты;
- квоты;
- тарифы;
- рейтинг семейного потребления;
- биллинг.

Это осознанное ограничение текущей семейной версии. Возможность может быть рассмотрена позднее как необязательный модуль после оценки реального спроса.

## 23. Осознанные ограничения

SG-Gateway рассчитан на один сервер и не предоставляет:

- SG-Nodes;
- Cluster;
- Cascade;
- автоматическую миграцию клиентов между VPS;
- межсерверную отказоустойчивость;
- полный ручной JSON-редактор;
- биллинг;
- персональную статистику трафика.

Для распределённой инфраструктуры предназначена SG-Panel.

## 24. Установка, обновление и удаление

Установка и обновление:

```bash
curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway/main/deploy/install-from-github.sh | sudo bash
```

Полное удаление:

```bash
curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway/main/deploy/full-uninstall-ubuntu.sh | sudo bash
```

Подтверждение удаления:

```text
DELETE SG-GATEWAY
```

## 25. Проверка исходного кода

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app hostd/sg_hostd tests
find . -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
```

GitHub Actions выполняет финальную проверку каждого опубликованного изменения.

---

**SG-Gateway сохраняет современный сетевой стек, но убирает инфраструктурную сложность, которая не нужна одному семейному серверу.**
