# SG-Gateway 0.1.0-022.08 — финальный стабильный выпуск

Статус: **FINAL / STABLE**. Основная ветка: `main`. Стабильный канал: `stable-02208`.

SG-Gateway 22.08 — это большая доводка рабочей панели: единый интерфейс, заметно более лёгкие страницы, безопасное штатное обновление и окончательно упрощённый AmneziaWG runtime.

## Что изменилось

### Панель стала легче

Большой проход выполнен по всем основным страницам, а не только по Clients.

- убраны N+1-запросы на списке клиентов;
- credentials карточки клиента загружаются пакетно и повторно используются при построении access/export;
- Connections и Routing переиспользуют уже загруженные connection settings;
- System получает счётчики клиентов и устройств одним агрегированным SQL-запросом;
- Recovery больше не запускает один и тот же health scan дважды;
- Maintenance не загружает тяжёлые данные соседних вкладок без необходимости;
- повторные проверки Xray, TLS, Mihomo, systemd и server identity кэшируются там, где это безопасно;
- обычная навигация по панели больше не запускает полный диагностический health scan в фоне.

Тяжёлые проверки не удалены: они остаются на System, Recovery, Maintenance и в явной диагностике — то есть там, где пользователь действительно ожидает полную проверку сервера.

### AmneziaWG 3.1 — текущий активный runtime

В 22.08 активным AmneziaWG-профилем остаётся **AWG 3.1**.

Legacy runtime AWG 2.0 и AWG 3.0 выведен из эксплуатации. Штатная maintenance/update логика останавливает старые службы, удаляет старые interfaces/config и не затрагивает AWG 3.1. Legacy database records и credentials при этом не удаляются вслепую runtime-cleanup процедурой.

### Безопасное обновление

Update остаётся отдельной операцией и не является повторным Clean Install.

Перед переключением исходников создаётся Safety Backup. После обновления проверяются Clients/credentials, HTTPS, Nginx, runtime-состояние, Panel и HostD. При критической ошибке предусмотрен rollback.

## Что проверено

Финальный performance-кандидат был проверен отдельным focused-набором: **31 тест прошёл успешно**. Дополнительно выполнены Python compile-проверки затронутых production-модулей, vendor/runtime integrity и проверка точного GitHub archive.

После этого тот же код был установлен штатным Update на реальный сервер. На сервере подтверждены:

- `nginx.service` — active;
- `sg-hostd.service` — active;
- `sg-gateway.service` — active;
- `sg-gateway-awg31.service` — active;
- Panel `/health` — `ok`;
- HostD `/health` — `ok`;
- основные страницы панели проверены вручную и работают штатно.

Проверенный production source:

`dfe760756636f675934a4f085f7ddd35f336d4a7`

## Команды

### Clean Install — только новый сервер

```bash
curl -4 -fsSL \
  https://raw.githubusercontent.com/s-gor/sg-gateway-v22/dfe760756636f675934a4f085f7ddd35f336d4a7/deploy/install-from-github.sh \
| sudo env \
  SG_GATEWAY_GITHUB_BRANCH=stable-02208 \
  SG_GATEWAY_SOURCE_COMMIT=dfe760756636f675934a4f085f7ddd35f336d4a7 \
  bash
```

### Update — существующий SG-Gateway

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/update-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```

### Full Uninstall

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/uninstall-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```

Подтверждение удаления:

```text
DELETE SG-GATEWAY
```

Актуальный набор публичных команд всегда лежит в [`deploy/GITHUB-COMMANDS.md`](deploy/GITHUB-COMMANDS.md).