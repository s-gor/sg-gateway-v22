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

## Документация

- [Полная справка SG-Gateway 022.06](docs/SG-GATEWAY-02206-GUIDE.md) — базовые эксплуатационные и runtime-контракты, унаследованные 22.08.
- [Отличия 022.06 от 022.04](docs/CHANGES-02204-TO-02206.md) — история функциональной линии.
- [Техническое устройство SG-Gateway](docs/TECHNICAL.md).

## Проверка выпуска

Перед публикацией обязательны source integrity, полный pytest с browser geometry, сборка и `--verify-only` FULL-пакета, Clean Install и Full Uninstall → Reinstall на Ubuntu 24.04.

Публичные команды после promotion публикуются в `deploy/GITHUB-COMMANDS.md`; Clean Install закрепляется на проверенный exact source commit, Update и Full Uninstall — на `stable-02208`.

## Команды

### Clean Install

```bash
curl -4 -fsSL \
  https://raw.githubusercontent.com/s-gor/sg-gateway-v22/1a74b6e53fc1dd3343c77c1f05678dff2cec225e/deploy/install-from-github.sh \
| sudo env \
  SG_GATEWAY_GITHUB_BRANCH=stable-02208 \
  SG_GATEWAY_SOURCE_COMMIT=1a74b6e53fc1dd3343c77c1f05678dff2cec225e \
  bash
```

### Update

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/update-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```

### Full Uninstall

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/uninstall-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```
