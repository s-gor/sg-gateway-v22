# SG-Gateway 0.1.0-022.08 — финальный стабильный выпуск

Статус: **FINAL / STABLE**. Основная ветка: `main`. Стабильный канал: `stable-02208`.

> **Один сервер. Одна панель. Быстрый домашний VPN без серверной акробатики.**

022.08 — не выпуск «ещё одной кнопки». В этой версии мы прошли практически всю панель и убрали накопившуюся тяжёлую работу, которая выполнялась при обычных переходах между страницами. Результат заметен именно в повседневной работе: Clients, карточки клиентов, Connections, Routing, System, Maintenance и Recovery открываются легче, а фоновые проверки меньше мешают интерфейсу.

## Команды

### Clean Install — только новый сервер

```bash
curl -4 -fsSL \
  https://raw.githubusercontent.com/s-gor/sg-gateway-v22/6d8b07125289566a6e8a7ba206094d8969e92125/deploy/install-from-github.sh \
| sudo env \
  SG_GATEWAY_GITHUB_BRANCH=stable-02208 \
  SG_GATEWAY_SOURCE_COMMIT=6d8b07125289566a6e8a7ba206094d8969e92125 \
  bash
```

### Update — уже установленный SG-Gateway

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/update-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```

### Full Uninstall

```bash
curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/deploy/uninstall-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash
```

Подтверждение полного удаления:

```text
DELETE SG-GATEWAY
```

## Главное в 022.08

- **Панель стала быстрее.** Убраны повторные SQL-запросы, лишние загрузки credentials/settings и тяжёлые проверки, которые раньше могли выполняться просто при открытии страницы.
- **Clients и карточка клиента больше не делают N+1 работу.** Credentials устройств загружаются пакетно и повторно используются при построении access/export.
- **Connections и Routing легче работают с настройками.** Несколько отдельных чтений заменены пакетной загрузкой и переиспользованием уже полученных данных.
- **System больше не собирает весь список клиентов ради четырёх счётчиков.** Для фоновой активности используется отдельный агрегированный SQL-запрос.
- **Recovery не выполняет один и тот же health scan дважды.**
- **Maintenance загружает данные только нужной вкладки.**
- **Обычная навигация больше не запускает полный диагностический health scan.** Полные проверки остались там, где они нужны: System, Recovery, Maintenance и явная диагностика.
- **Короткие runtime-проверки кэшируются.** Xray, TLS, Mihomo, systemd и server identity не опрашиваются заново без необходимости.

## AmneziaWG: один актуальный runtime

В линии 022.08 активным AmneziaWG-профилем является **AWG 3.1**.

Legacy runtime **AWG 2.0** и **AWG 3.0** выведен из эксплуатации. Штатная maintenance/update логика останавливает старые службы, удаляет старые interfaces/config и не затрагивает AWG 3.1.

При этом runtime-cleanup не удаляет вслепую сохранённые legacy database records и credentials. Это важно для совместимости старых backup и аккуратного перехода между выпусками.

## Update остаётся безопасным Update

Обновление не превращено в повторный Clean Install.

Перед переключением исходников SG-Gateway создаёт **Safety Backup**. После обновления проверяются Clients/credentials, HTTPS, Nginx, runtime-состояние, Panel и HostD. При критической ошибке предусмотрен rollback.

То есть обновление панели не должно молча менять сертификаты, Nginx, клиентские ключи или работающий AWG 3.1 runtime.

## Что проверено перед выпуском

Финальный 022.08 проходит отдельный release-contract для актуальной архитектуры — **95 тестов** на performance, Clients, AWG3.1, retirement AWG2/AWG3.0, Clean Install, Update, release metadata и runtime preservation.

До этого финальный performance-кандидат отдельно прошёл **31 focused regression test**. Дополнительно проверены Python syntax, vendor/runtime SHA-256 и целостность Xray, Mihomo, sing-box, WARP и AmneziaWG runtime-файлов.

Тот же production-код был установлен штатным Update на реальный сервер. После обновления подтверждены:

- `nginx.service` — active;
- `sg-hostd.service` — active;
- `sg-gateway.service` — active;
- `sg-gateway-awg31.service` — active;
- Panel `/health` — `ok`;
- HostD `/health` — `ok`;
- основные страницы панели вручную пройдены на живом сервере.

Публикация GitHub Release выполняется только после успешной проверки source integrity и сборки/`--verify-only` FULL-пакета.

Проверенный production source Clean Install:

`6d8b07125289566a6e8a7ba206094d8969e92125`

## Для кого этот выпуск

Если SG-Gateway уже работает — используйте **Update**. Клиентов, ключи и рабочие настройки переносить вручную не нужно.

Если ставите SG-Gateway на новый Ubuntu 24.04 сервер — используйте **Clean Install**.

Если хотите полностью убрать SG-Gateway и его данные с сервера — используйте **Full Uninstall**.

## Документация

- **[Публичные команды GitHub](deploy/GITHUB-COMMANDS.md)** — актуальные Clean Install, Update и Full Uninstall.
- **[Полная справка SG-Gateway 022.06](docs/SG-GATEWAY-02206-GUIDE.md)** — базовая эксплуатационная справка по унаследованным функциям.
- **[Что изменилось между 022.04 и 022.06](docs/CHANGES-02204-TO-02206.md)** — история предыдущей стабильной линии.
- **[Техническое устройство SG-Gateway](docs/TECHNICAL.md)**.

Если после обновления какая-то конкретная страница всё ещё открывается медленно или появляется реальная ошибка — это уже лучший материал для следующего точечного исправления. Пишите с описанием страницы и сценария воспроизведения.
