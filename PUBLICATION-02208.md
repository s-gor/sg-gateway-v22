# SG-Gateway 0.1.0-022.08 — финальный стабильный выпуск

Статус: **FINAL / STABLE**. Стабильный канал: `stable-02208`. Финальный тег: `v0.1.0-022.08-final`.

Версия 22.08 переносит интерфейс SG-Gateway на единый UI-контракт без изменения проверенных протокольных и backup/runtime гарантий предыдущей линии.

## Главное

- единая система UI primitives и layout для основных страниц панели;
- согласованная геометрия Connections, Clients, Routing, Security, System, Maintenance и Outbounds;
- единый standalone-frame для Login и Recovery;
- Help и Operation Job переведены на тот же 22.08 UI-контракт;
- real-browser проверки Chromium на desktop, tablet и mobile widths в dark/light;
- сохранены AWG 2.0, AWG 3.0, AWG 3.1, Xray, NaiveProxy, backup/restore, update rollback и clean-install/reinstall contracts.

## Проверка выпуска

Перед публикацией обязательны source integrity, полный pytest с browser geometry, сборка и `--verify-only` FULL-пакета, Clean Install и Full Uninstall → Reinstall на Ubuntu 24.04.

Публичные команды после promotion публикуются в `deploy/GITHUB-COMMANDS.md`; Clean Install закрепляется на проверенный exact source commit, Update и Full Uninstall — на `stable-02208`.
