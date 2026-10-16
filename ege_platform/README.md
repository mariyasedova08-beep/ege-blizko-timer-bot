# ЕГЭ БЛИЗКО — первая домашняя работа (разработка)

Статус: **серверный vertical slice в отдельной feature-ветке, не продакшен**. Ветку не сливать и не выпускать до приёмки UI и авторизации.

## Реализовано в этом репозитории

- `homework_core.py` — собственные таблицы `lms_*` с tenant-scoped курсами, уроками, двумя банками и публикацией неизменяемого снимка заданий.
- Назначение конкретному ученику, сдача и автопроверка кратких ответов, ручное подтверждение, возврат на доработку, история попыток и прогресс.
- `test_homework_core.py` — 8 тестов на **временной** SQLite, включая защита чужих учеников и закрытых ключей.
- `.github/workflows/ege-platform-homework-ci.yml` — независимый CI **без SSH, токенов и деплоя**.

На 16.10.2026 GitHub Actions run [#38877953726](https://github.com/mariyasedova08-beep/ege-blizko-timer-bot/actions/runs/38877953726): success на SHA `5aa471992f34825dd7e7f3c9c0f428bff776b4fe`.

## Тестировать

```sh
python -m unittest -v ege_platform.test_homework_core
```

## Что ещё НЕ сделано

- Реальная авторизация через существующие аккаунты и WebApp ЕГЭ БЛИЗКО.
- Подключение к сохранённым HTML-макетам генератора, проверки, курса и кабинета ученика.
- Проверенная миграция рабочей SQLite/backup/rollback.
- Два режима автоматического генератора, загрузка файлов, массовая проверка, расписание уведомлений.

Согласованные HTML-прототипы находятся в ChatGPT Library: `ege_blizko_homework_generator_prototype.html`, `ege_blizko_homework_review_prototype.html`, `ege_blizko_student_platform_cabinet_v3.html`, `ege_blizko_course_page_v1.html`. Прототипы НЕ считаются рабочим сервером.

**ЕГЭ БЛИЗКО и ПРЕПОДМИН не смешивать.** Working EGE Telegram bot, PREPODMIN and personal medical bot have not been changed.
