# SG-Gateway 0.1.0-022.06 — финальный стабильный выпуск

Статус: **FINAL / STABLE**. Основная ветка: `main`. Стабильный канал: `stable-02206`.

Версия завершает линию 022.06 и объединяет независимые AWG 2.0, AWG 3.0 и AWG 3.1, безопасное обновление, переносимые резервные копии, персональные подписки и накопленные исправления панели.

## Документация

- **[Полная справка SG-Gateway 022.06](docs/SG-GATEWAY-02206-GUIDE.md)** — установка, первый запуск, протоколы, клиенты, подписки, Routing, HTTPS, Backup/Restore и диагностика.
- **[Отличия 022.06 от 022.04](docs/CHANGES-02204-TO-02206.md)** — полный перечень новых возможностей и функций, унаследованных от предыдущего выпуска.
- **[Публичные команды GitHub](deploy/GITHUB-COMMANDS.md)** — Clean Install, Update и Full Uninstall.

В руководстве зарезервированы восемь пронумерованных мест для новых скриншотов.

## Главное

- **Три независимых поколения AmneziaWG:** AWG 2.0, AWG 3.0 userspace и AWG 3.1 userspace работают как отдельные профили с отдельными runtime, портами и клиентскими credentials.
- **Полный набор для первого администратора:** `sg-admin` получает VLESS Reality TCP, VLESS XHTTP Reality, AWG 2.0, AWG 3.0, AWG 3.1, Mieru и скрытый SG Client access.
- **Безопасное создание клиентов:** неполные AWG credentials и отключённые Xray-профили не выдаются как рабочие; изменения откатываются атомарно.
- **Full Backup/Restore:** сохраняются база, клиенты, ключи, сертификаты и runtime-состояние; восстановление проверяет сервисы и выполняет safety rollback при ошибке.
- **Безопасный Update:** exact commit, source integrity, Safety Backup, staging, проверка panel/hostd/runtime и автоматический rollback.
- **Тихая пошаговая установка:** этапы отображаются с зелёным индикатором, а технический вывод `apt`, `curl`, распаковки и настройки сохраняется в журнале и показывается только при ошибке.
- **Публичные команды GitHub:** Clean Install закреплён одновременно на стабильный канал и проверенный source commit; Update и Full Uninstall используют стабильный канал.
- **Системная диагностика:** исправлена атрибуция памяти и пороги предупреждений диска и RAM.
- **Интерфейс:** унифицированы карточки AWG, QR и загрузка ключей, операции восстановления и адаптация для низкого разрешения.

## Проверка выпуска

Перед публикацией финальной версии подтверждены:

- полный `pytest` на принятом дереве;
- source integrity;
- сборка FULL-пакета и `--verify-only`;
- Clean Install на Ubuntu 24.04;
- Full Uninstall и повторная установка на том же сервере;
- создание и применение дополнительного AWG 3.0 клиента;
- активные AWG 3.0 и AWG 3.1 interfaces, sockets и порты `586/587`;
- имена AWG 2.0, AWG 3.0 и AWG 3.1 в подписке первого администратора после чистой установки: `sg-admin`, без резервного суффикса `Устройство`;
- новая тихая пошаговая установка без сырого служебного вывода;
- реальная чистая установка после полного удаления.

## Команды

### Clean Install

```bash
curl -4 -fsSL \
  https://raw.githubusercontent.com/s-gor/sg-gateway-v22/2e96ea97992509f8ff2fdce8b8d23aa0dc5a1dff/deploy/install-from-github.sh \
| sudo env \
  SG_GATEWAY_GITHUB_BRANCH=stable-02206 \
  SG_GATEWAY_SOURCE_COMMIT=2e96ea97992509f8ff2fdce8b8d23aa0dc5a1dff \
  bash
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
