# ПРЕПОДМИН — запуск с чистой базой на Timeweb

**Решение владельца от 13.10.2026:** начать ПРЕПОДМИН с чистой БД, **не переносить** старые записи преподавателей/учеников/оплат/ДЗ/расписаний из Railway. Приложение и его функции сохранить. ЭТО ПОДГОТОВКА К ПЕРЕНОСУ; никакой запуск на Timeweb этим коммитом не производится.

## Сохраняем и не трогаем

- **ПРЕПОДМИН**: существующий Telegram-бот `@prepodmin_bot`; код `teacher_product_*.py`, HTML WebApp из GitHub. Запуск `python teacher_product_runner.py`.
- **ЕГЭ БЛИЗКО**: действующий Timeweb production `ege-blizko` и его `/opt/bots/ege-blizko`, БД, задачи, токен; **не менять**.
- Личный бот `sedova-pill-tracker-bot`: **не менять**.
- Старый `teacher-admin-pilot-volume` в Railway **не удалять**; возврат прежних данных после решения о чистом старте в этот план не входит.

### Исходное состояние

Railway: проект с заголовком `sedova-pill-tracker-bot` содержит отдельный **сервис** `teacher-admin-pilot` и том `teacher-admin-pilot-volume` монтируемый в `/data`. Railway trial закончился, сервис offline. В разделе Backups отображается `No Backups`. CLI `volume files list /` отказал с `has no active deployment`. Это не свидетельствует об отсутствии данных, но получать их уже **не требуется по решению владельца**. Любое возобновление платной подписки может перезапустить старые сервисы; такого действия не выполнять.

Код ПРЕПОДМИН сейчас живёт в **общем** GitHub-репозитории `mariyasedova08-beep/ege-blizko-timer-bot`. Ветка подготовки `feature/prepodmin-timeweb-migration-20261013` содержит только изменения, относящиеся к ПРЕПОДМИН. **Не запускать workflow Timeweb для ЕГЭ** для установки ПРЕПОДМИН.

## Изоляция Timeweb

| Предмет | Значение |
|---|---|
| Сервер | Timeweb VPS `77.233.212.200` |
| systemd user | `prepodmin`, не `root` |
| code directory | `/opt/bots/prepodmin/current` (отдельная копия кода, закреплённая ветка) |
| fresh SQLite | `/opt/bots/prepodmin/data/teacher_product.sqlite3` |
| service | `prepodmin.service` (не `ege-blizko`) |
| localhost HTTP | `127.0.0.1:8091` |
| HTTP path | `/health`, `/webapp`, `/student` |
| public HTTPS | `https://prepodmin.77-233-212-200.sslip.io` (сертификат действителен до 11.01.2027) |

Исходный код: `teacher_product_runner.py` уже выполняет `ensure_tables()` для всех разделов при запуске, а `teacher_product_pilot_selftest.py` тестирует данные на **временной** SQLite, не на живой базе. Если нет `TEACHER_PRODUCT_BOT_TOKEN`, в runner запускается локальный HTTP health-сервер, но polling Telegram **не начинается**. Для Timeweb в `teacher_product_webapp.py` добавлена настройка `TEACHER_PRODUCT_BIND_HOST=127.0.0.1`; по умолчанию на Railway сохранено `0.0.0.0`.

## Порядок безопасной установки — только с отдельного согласия на развёртывание

**1. Read-only диагностика Timeweb.** Проверить `ege-blizko` active, свободен ли порт 8091, версии Python/Git, доступное место, наличие HTTPS reverse proxy и независимых резервных копий ЕГЭ. Не менять системные сервисы. Проверить актуальный SHA целевой ветки перед установкой.

**2. Отдельное окружение.** Создать системного пользователя `prepodmin`, защищённые каталоги `/opt/bots/prepodmin/current`, `/opt/bots/prepodmin/data`, `/etc/prepodmin` и отдельный Python venv. Поместить в `current` **только отдельную копию репозитория** из ветки подготовки; никогда не делать `git pull/reset/clean` в каталоге ЕГЭ. Установить зависимости из `requirements.txt` в отдельную `.venv`.

**3. Пустая БД — вместо Railway data copy.** Запустить `deployment/prepodmin/bootstrap_empty_db.py` от пользователя `prepodmin` с параметром:
```bash
python3 deployment/prepodmin/bootstrap_empty_db.py \
  --db /opt/bots/prepodmin/data/teacher_product.sqlite3
```
Утилита НЕ открывает Railway и отказывается перезаписать даже существующий пустой файл. Перед запуском убедиться, что целевой каталог существует и доступен пользователю `prepodmin`. БД имеет права 0600, `PRAGMA integrity_check=ok`; пользовательских записей нет.

**4. Только health-проверка без Telegram.** В отдельном `/etc/prepodmin/prepodmin.env` оставить `TEACHER_PRODUCT_BOT_TOKEN` пустым, задать `TEACHER_PRODUCT_BOT_USERNAME=prepodmin_bot`. Настроить `deployment/prepodmin/prepodmin.service.example` как отдельный systemd unit (сначала `disabled`). Unit запускает **`deployment/prepodmin/launch_timeweb.py`**, который перед запуском приложения проверяет пользователя Linux, путь и тип свежей БД, SQLite integrity, локальный порт и адрес. При появлении токена он дополнительно требует раздельные HTTPS WebApp URL, иначе отказывает в запуске Telegram polling. Локальный bind `127.0.0.1:8091`, **не открывать порт 8091 во внешний интернет**. Запустить только `prepodmin` для проверки `curl -fsS http://127.0.0.1:8091/health` и логов. `ensure_tables()` в этот момент создаст пустую рабочую схему. При ошибке — останавливать ТОЛЬКО `prepodmin`.

**5. HTTPS и WebApp.** Предоставить отдельное имя/поддомен и обратный HTTPS-прокси `https://<PREPODMIN_HOST>/webapp` и `/student` → `127.0.0.1:8091`. Указать `TEACHER_PRODUCT_WEBAPP_URL`, `TEACHER_PRODUCT_STUDENT_WEBAPP_URL`. Не использовать старый Railway URL. Настроить TLS сертификат и проверить WebApp без публичного токена бота.

**6. Реальный переключатель Telegram — отдельное согласие владельца.** Убедиться, что Railway `teacher-admin-pilot` не работает и не будет автоматически включён. Локально настроить `TEACHER_PRODUCT_BOT_TOKEN` **без отправки токена в чат/репозиторий** (при необходимости перевыпуск через BotFather по согласованию). Запускать **только** `prepodmin.service`, проверить `/start` с тестовым аккаунтом, кабинеты преподавателя и ученика, группы, расписание, списание занятий, ДЗ, оплату, уведомления и health/logs. До реального запуска и тестовых сообщений запросить отдельное согласие.

**7. Долговременный режим.** После первых настоящих записей включить резервное копирование новой БД через `deployment/prepodmin/sqlite_snapshot.py` и регулярно проверять `integrity_check`, SHA-256 и возможность восстановления. Не смешивать БД двух ботов.

## Переменные и безопасность

Только названия (значения не публиковать): `TEACHER_PRODUCT_BOT_TOKEN`, `TEACHER_PRODUCT_BOT_USERNAME`, `TEACHER_PRODUCT_DB_PATH`, `TEACHER_PRODUCT_BIND_HOST`, `TEACHER_PRODUCT_WEBAPP_URL`, `TEACHER_PRODUCT_STUDENT_WEBAPP_URL`, `PORT`, опционально `OPENAI_API_KEY`. Прошлые ссылки приглашений на старую БД и старые пользовательские настройки не переносим; преподаватели повторно проходят онбординг.

## Подтверждённое состояние на 13.10.2026 (из проверок владельца)

- Timeweb: `prepodmin.service` **enabled + active**, порт `127.0.0.1:8091`, HTTPS `https://prepodmin.77-233-212-200.sslip.io` работает; `/health`, `/webapp`, `/student` отвечают HTTP 200. Telegram `@prepodmin_bot` подключён и отвечает, преподавательский кабинет открылся после завершения онбординга. `ege-blizko.service` отдельно `active`. Другие сервисы не меняли.
- С нуля создана база `/opt/bots/prepodmin/data/teacher_product.sqlite3`. В начальном снимке 48 таблиц, 1 преподаватель, 0 учеников, 0 групп.
- Первая согласованная резервная копия `/var/backups/prepodmin/prepodmin-initial-20261013.sqlite3` (430080 байт, integrity_check=ok) создана. Владелец сообщил, что скачал её на личный компьютер; удалённая проверка файла на компьютере не выполнялась.
- Не переносить старые записи Railway. Секреты хранить только в `/etc/prepodmin/prepodmin.env` (640 root:prepodmin), НЕ в GitHub.
- **Автоматические резервные копии подготовлены в GitHub, но до выполнения install_daily_backup.sh ещё не включены.**

## Автоматическое локальное резервное копирование — подключить отдельно

- Файлы: `deployment/prepodmin/daily_backup.py`, `prepodmin-backup.service.example`, `prepodmin-backup.timer.example` и `install_daily_backup.sh`.
- `systemd` расписание: ежедневно в 01:30 UTC (04:30 MSK); `Persistent=true` выполняет пропущенный запуск после включения сервера.
- Путь: `/var/backups/prepodmin/daily/`, права доступа root-only. Для SQLite используется online backup API, после каждой копии `PRAGMA integrity_check`. Копии старше 30 дней удаляются только после успешного нового снимка; исходная БД, исходный initial snapshot и чужие файлы не удаляются.
- Для установки: обновить **только копию GitHub в `/opt/bots/prepodmin/current`**, затем `bash /opt/bots/prepodmin/current/deployment/prepodmin/install_daily_backup.sh` от root. Инсталлятор проверяет оба живых сервиса, делает тестовый снимок, и только затем активирует таймер. Не перезапускает Telegram и не изменяет конфигурацию ЕГЭ.
- Проверка: `systemctl is-active prepodmin-backup.timer`, `systemctl list-timers prepodmin-backup.timer --no-pager`, `journalctl -u prepodmin-backup.service -n 20 --no-pager`.
- **ВАЖНО**: пока настроены только **локальные** ежедневные копии. Наличие ранней ручной копии на компьютере не означает, что новые данные автоматически туда попадают. Для защиты от потери всего Timeweb нужна регулярная отдельная внешняя копия; настроить её после выбора приватного внешнего хранилища, с шифрованием и отдельными credentials.
