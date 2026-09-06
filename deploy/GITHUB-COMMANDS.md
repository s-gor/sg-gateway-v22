# SG-Gateway 0.1.0-022.08 · команды GitHub

Канал: `stable-02208`. Поддерживается Ubuntu 24.04.

## Чистая установка

Только для сервера без установленного SG-Gateway. Команда закреплена на проверенный исходный commit `cde152df4b957c254950e3b4a2276b76561653c9`:

```bash
curl -4 -fsSL \
  https://raw.githubusercontent.com/s-gor/sg-gateway-v22/cde152df4b957c254950e3b4a2276b76561653c9/deploy/install-from-github.sh \
| sudo env \
  SG_GATEWAY_GITHUB_BRANCH=stable-02208 \
  SG_GATEWAY_SOURCE_COMMIT=cde152df4b957c254950e3b4a2276b76561653c9 \
  bash
```

## Обновление

Для уже установленного SG-Gateway:

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/update-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```

## Полное удаление

Удаляются приложение, конфигурация, база, резервные копии, SG-службы и установленные SG runtime. Системные пакеты Ubuntu остаются установленными.

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/uninstall-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```

Для подтверждения необходимо ввести точно:

```text
DELETE SG-GATEWAY
```
