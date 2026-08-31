# SG-Gateway 0.1.0-022.06 · команды GitHub

Канал: `stable-02206`. Поддерживается Ubuntu 24.04.

## Чистая установка

Только для сервера без установленного SG-Gateway. Команда закреплена на проверенный исходный commit `e7cd63deab9c3a34b6aee910c61017ff8a8b9c6e`:

```bash
curl -4 -fsSL \
  https://raw.githubusercontent.com/s-gor/sg-gateway-v22/e7cd63deab9c3a34b6aee910c61017ff8a8b9c6e/deploy/install-from-github.sh \
| sudo env \
  SG_GATEWAY_GITHUB_BRANCH=stable-02206 \
  SG_GATEWAY_SOURCE_COMMIT=e7cd63deab9c3a34b6aee910c61017ff8a8b9c6e \
  bash
```

## Обновление

Для уже установленного SG-Gateway:

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02206/deploy/update-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02206 bash
```

## Полное удаление

Удаляются приложение, конфигурация, база, резервные копии, SG-службы и установленные SG runtime. Системные пакеты Ubuntu остаются установленными.

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02206/deploy/uninstall-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02206 bash
```

Для подтверждения необходимо ввести точно:

```text
DELETE SG-GATEWAY
```
