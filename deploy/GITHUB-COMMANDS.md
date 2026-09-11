# SG-Gateway 0.1.0-022.08 · команды GitHub

Канал: `stable-02208`. Поддерживается Ubuntu 24.04.

Проверенный production source: `dfe760756636f675934a4f085f7ddd35f336d4a7`.

## Чистая установка

Только для нового сервера без установленного SG-Gateway. Clean Install закреплён на точный проверенный source commit:

```bash
curl -4 -fsSL \
  https://raw.githubusercontent.com/s-gor/sg-gateway-v22/dfe760756636f675934a4f085f7ddd35f336d4a7/deploy/install-from-github.sh \
| sudo env \
  SG_GATEWAY_GITHUB_BRANCH=stable-02208 \
  SG_GATEWAY_SOURCE_COMMIT=dfe760756636f675934a4f085f7ddd35f336d4a7 \
  bash
```

## Обновление

Для уже установленного SG-Gateway 22.08. Перед переключением кода Update создаёт Safety Backup и проверяет panel, HostD, HTTPS/Nginx, Clients/credentials и runtime. При критической ошибке выполняется rollback.

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

## Текущий AmneziaWG runtime в 22.08

Активный AmneziaWG-профиль текущей линии — **AWG 3.1**. Legacy runtime AWG 2.0 и AWG 3.0 выведен из эксплуатации и очищается штатной maintenance/update логикой. Сохранённые legacy database records и credentials не удаляются этим runtime cleanup вслепую.