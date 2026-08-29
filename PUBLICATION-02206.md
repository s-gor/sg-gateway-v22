# SG-Gateway 0.1.0-022.06 — стабильный выпуск

Статус: **STABLE**. Ветка выпуска: `stable-02206`. Тег: `v0.1.0-022.06`.

Версия завершает линию 022.06 и объединяет независимые AWG 2.0, AWG 3.0 и AWG 3.1, безопасное обновление, переносимые резервные копии, персональные подписки и накопленные исправления панели.

## Главное

- **Три независимых поколения AmneziaWG:** AWG 2.0, AWG 3.0 userspace и AWG 3.1 userspace работают как отдельные профили с отдельными runtime, портами и клиентскими credentials.
- **Полный набор для первого администратора:** `sg-admin` получает VLESS Reality TCP, VLESS XHTTP Reality, AWG 2.0, AWG 3.0, AWG 3.1, Mieru и скрытый SG Client access.
- **Безопасное создание клиентов:** неполные AWG credentials и отключённые Xray-профили не выдаются как рабочие; изменения откатываются атомарно.
- **Full Backup/Restore:** сохраняются база, клиенты, ключи, сертификаты и runtime-состояние; восстановление проверяет сервисы и выполняет safety rollback при ошибке.
- **Безопасный Update:** exact commit, source integrity, Safety Backup, staging, проверка panel/hostd/runtime и автоматический rollback.
- **Публичные команды GitHub:** отдельные стабильные команды Clean Install, Update и Full Uninstall.
- **Системная диагностика:** исправлена атрибуция памяти и пороги предупреждений диска и RAM.
- **Интерфейс:** унифицированы карточки AWG, QR и загрузка ключей, операции восстановления и адаптация для низкого разрешения.

## Проверка выпуска

Перед повышением в STABLE подтверждены:

- полный `pytest` на принятом дереве;
- source integrity;
- сборка FULL-пакета и `--verify-only`;
- Clean Install на Ubuntu 24.04;
- Full Uninstall и повторная установка на том же сервере;
- создание и применение дополнительного AWG 3.0 клиента;
- активные AWG 3.0 и AWG 3.1 interfaces, sockets и порты `586/587`;
- реальная чистая установка пользователем после публикации обеих GitHub-команд.

## Команды

### Clean Install

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02206/deploy/install-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02206 bash
```

### Update

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02206/deploy/update-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02206 bash
```

### Full Uninstall

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02206/deploy/uninstall-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02206 bash
```

Подтверждение удаления: `DELETE SG-GATEWAY`.
