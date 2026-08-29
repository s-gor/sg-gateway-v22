# SG-Gateway 0.1.0-022.06 · команды GitHub

Канал: `stable-02206`. Поддерживается Ubuntu 24.04.

## Чистая установка

Только для сервера без установленного SG-Gateway:

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02206/deploy/install-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02206 bash
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
