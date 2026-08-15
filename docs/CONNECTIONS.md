# Connections и клиентские профили

## AmneziaWG

SG-Gateway использует внешний UDP-порт `585`. Настройки сервера включают адрес, DNS, ключи и параметры профиля. Для каждого устройства создаётся отдельная клиентская конфигурация.

## Xray

### VLESS Reality TCP

TCP/Reality-профиль с XTLS Vision.

### VLESS XHTTP Reality

Клиентская ссылка содержит XHTTP mode, VLESS Encryption и XMUX для РФ. Сервер использует поддерживаемый XHTTP-режим автоматически.

### VLESS XHTTP TLS

Требует готового HTTPS-домена. Клиентская ссылка содержит XHTTP mode, VLESS Encryption и XMUX-профиль.

### Hysteria 2

Использует QUIC/UDP и TLS. Salamander FinalMask настраивается отдельно и проверяется перед применением.

## XMUX для РФ

Профиль применяется к обоим XHTTP-профилям:

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

Эти значения добавляются в `extra.xmux` клиентских ссылок и не записываются в серверный inbound.

## Mihomo и sing-box

- Mieru обслуживается Mihomo;
- AnyTLS и TUIC v5 обслуживаются отдельным sing-box.

Каждый движок имеет собственное runtime-состояние, а панель объединяет их результаты в одном интерфейсе. Выключенный профиль не выдаётся клиентам как доступный, при этом сохранённые реквизиты остаются в базе для повторного включения.
