# Документация SG-Gateway

Документация относится к линии **SG-Gateway 021** и версии приложения **`0.1.0-021.7`**.

## Две дороги

### Пользовательская

Для установки и обычной работы:

1. [Главный README](../README.md)
2. [Установка и обновление](INSTALLATION.md)
3. [Руководство пользователя](USER-GUIDE.md)
4. [Connections и клиентские профили](CONNECTIONS.md)
5. [Routing и GeoFiles](ROUTING.md)
6. [HTTPS и безопасность](security.md)
7. [Maintenance и диагностика](MAINTENANCE.md)
8. [Полное удаление](UNINSTALL.md)

### Техническая

Для пользователя, который хочет понимать устройство профилей и служб:

- [Техническое устройство SG-Gateway](TECHNICAL.md)

В техническом документе подробно разобраны:

- XTLS Vision;
- VLESS Encryption;
- XHTTP;
- XMUX для РФ;
- REALITY и TLS;
- AmneziaWG;
- Mihomo;
- WARP;
- Routing и GeoFiles;
- службы, порты и размещение файлов;
- обновление и сохранность данных;
- осознанные ограничения проекта.

## Разделы панели

```text
System       ресурсы, службы и состояние
Clients      клиенты, устройства, QR и subscriptions
Connections  AmneziaWG, Xray и Mihomo
Outbounds    Direct, WARP и Block
Routing      правила и GeoFiles
Maintenance  копии, журналы, обновления
Security     доступ, HTTPS и защита
Help         встроенная справка
```

## Главное правило

Любое изменение серверных подключений или Routing сначала проверяется. Применение выполняется только после успешной проверки candidate-конфигурации. Перед рискованными изменениями создаётся страховочная копия, а при ошибке выполняется rollback.
