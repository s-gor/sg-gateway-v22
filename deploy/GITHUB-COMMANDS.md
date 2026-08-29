# SG-Gateway · команды GitHub

Канал: `dev-02206`. Поддерживается Ubuntu 24.04.

## Чистая установка

Команда предназначена только для сервера без установленного SG-Gateway:

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/dev-02206/deploy/install-from-github.sh | sudo env SG_GATEWAY_ALLOW_DEVELOPMENT=1 SG_GATEWAY_GITHUB_BRANCH=dev-02206 bash
```

## Полное удаление

Команда запускает официальный полный деинсталлятор. Он удаляет приложение, конфигурацию, базу, резервные копии, SG-службы и установленные SG runtime. Системные пакеты Ubuntu остаются установленными.

Перед удалением деинсталлятор потребует ввести точно `DELETE SG-GATEWAY`:

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/dev-02206/deploy/uninstall-from-github.sh | sudo env SG_GATEWAY_ALLOW_DEVELOPMENT=1 SG_GATEWAY_GITHUB_BRANCH=dev-02206 bash
```
