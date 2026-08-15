# Руководство пользователя SG-Gateway

Это краткий маршрут по панели в том же порядке, что и встроенная справка.

## System

Показывает ресурсы сервера, версии и состояние основных служб. С этой страницы удобно начинать проверку после установки или изменений.

![System](screenshots/system.png)

## Clients

Клиент — логическая запись пользователя. Устройство — отдельный набор реквизитов доступа.

Рабочий порядок:

1. создать клиента;
2. добавить устройство;
3. выбрать доступные подключения;
4. применить изменения;
5. получить ссылку, QR-код, файл конфигурации или SG Client subscription;
6. при необходимости временно отключить устройство или клиента.

| Список клиентов | Карточка клиента |
| --- | --- |
| ![Список клиентов](screenshots/clients.png) | ![Карточка клиента](screenshots/client-card.png) |

| Добавление устройства | Выбор подключений |
| --- | --- |
| ![Добавление устройства](screenshots/add-device.png) | ![Выбор подключений](screenshots/device-connections.png) |

## Connections

Здесь настраиваются серверные подключения AmneziaWG, Xray и дополнительные протоколы.

![Connections](screenshots/connections.png)

### Xray

Поддерживаются VLESS Reality TCP, VLESS XHTTP Reality, VLESS XHTTP TLS и Hysteria 2.

![Xray](screenshots/xray-settings.png)

### AmneziaWG

AmneziaWG использует отдельный профиль сервера и индивидуальные реквизиты устройств.

![AmneziaWG](screenshots/amneziawg.png)

### Mieru, AnyTLS и TUIC v5

Mieru обслуживается Mihomo, AnyTLS и TUIC v5 — sing-box.

![Дополнительные протоколы](screenshots/extra-protocols.png)

## Outbounds

- `Direct` — выход через публичный IP сервера;
- `WARP` — выход через Cloudflare WARP;
- `Block` — блокировка трафика.

![WARP](screenshots/warp-outbound.png)

## Routing и GeoFiles

Routing назначает действие для доменов, IP и готовых категорий. GeoFiles всегда применяются связанной парой `geoip.dat` + `geosite.dat`.

Обычное обновление простое: **выберите источник → нажмите «Проверить источник» → после успешной проверки нажмите «Обновить GeoFiles»**. Вручную заменять файлы на сервере не нужно. SG-Gateway сам проверит категории и будущую конфигурацию Xray, сохранит резервную копию и выполнит безопасное переключение.

![Routing и GeoFiles](screenshots/routing.png)

Подробная пошаговая инструкция с тремя реальными скриншотами — выбор и проверка источника, подтверждение обновления и результат — находится в [Routing и GeoFiles](ROUTING.md).

## Maintenance

Здесь находятся резервные копии, журналы, диагностика и независимые обновления панели и runtime-компонентов.

| Maintenance | Обновления |
| --- | --- |
| ![Maintenance](screenshots/maintenance.png) | ![Обновления](screenshots/updates.png) |

## Security

Раздел отвечает за режим доступа к панели, домен и сертификат Let’s Encrypt.

| Security | Сертификат |
| --- | --- |
| ![Security](screenshots/security.png) | ![Сертификат](screenshots/certificate-status.png) |

## Help

Встроенная справка повторяет структуру панели и даёт короткие инструкции по типовым операциям.

![Help](screenshots/help.png)
