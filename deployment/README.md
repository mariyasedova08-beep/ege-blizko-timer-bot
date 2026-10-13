# ЕГЭ БЛИЗКО — проверяемые обновления GitHub → Timeweb

## Рабочая конфигурация (13.10.2026)

- Только ЕГЭ БЛИЗКО: сервер Timeweb, `/opt/bots/ege-blizko`, systemd `ege-blizko`.
- Служба переведена на непривилегированного системного пользователя `ege-bot`, health `http://127.0.0.1:8080/health`.
- SSH-пользователь GitHub Actions — `ege-deploy`; окружение `timeweb-production` требует ручного подтверждения владельца.
- Первый развёрнутый выпуск двух файлов прошёл успешно 13.10.2026; тренажёр на 50 вопросов пока подготовлен в этой ветке и НЕ выпущен.
- Серверный helper `/usr/local/sbin/ege-blizko-deploy` принадлежит root; sudoers разрешает `ege-deploy` запускать только этот исполняемый файл.
- Изменения в рабочем дереве (`ege_lab_webapp.py`), секретные `runtime-vars.json`, `timeweb_runner.py` и `data/` не трогать. Не использовать git pull/reset/clean в рабочем каталоге.
- Боты ПРЕПОДМИН и медицинский бот не затрагивать.

## Выпуск тренажёра «Кислые, основные и комплексные соли» (PR №10)

Релизная ветка `feature/timeweb-safe-deploy-20261012` содержит объединённые и проверенные для совмещения с ОГЭ-модулем файлы:
- `run_bot_production.py`
- `oge9_trainer_notifications.py`
- `special_salts_trainer.py`
- `special_salts_trainer_bank.py` (50 вопросов, четыре ответа и объяснения)

**Один ручной шаг необходим до первого запуска расширенного workflow:** обновить серверный root-owned helper из `deployment/timeweb_safe_deploy.sh` этой ветки. Прежняя серверная версия разрешает только два файла; изменение GitHub workflow без обновления серверного helper не установит новые модули. Не переносить загруженный workflow из staging в root как исполняемый файл.

Для обновления helper (связь SSH как root, из Windows PowerShell):

```powershell
ssh root@77.233.212.200 "git -C /opt/bots/ege-blizko fetch -q origin feature/timeweb-safe-deploy-20261012:refs/remotes/origin/feature/timeweb-safe-deploy-20261012 && echo FETCH_OK"
ssh root@77.233.212.200 "git -C /opt/bots/ege-blizko show origin/feature/timeweb-safe-deploy-20261012:deployment/timeweb_safe_deploy.sh > /tmp/ege-deploy-new.sh && bash -n /tmp/ege-deploy-new.sh && grep -q 'special_salts_trainer_bank.py' /tmp/ege-deploy-new.sh && install -o root -g root -m 755 /tmp/ege-deploy-new.sh /usr/local/sbin/ege-blizko-deploy && echo HELPER_UPDATED"
```

Обе команды **не перезапускают** Telegram-бота. Затем владелец вручную запускает GitHub Actions `Timeweb — EGE BLIZKO manual release` из ветки `feature/timeweb-safe-deploy-20261012`, подтверждает `timeweb-production` и смотрит `Success` и логи `DEPLOY SUCCESS`.

Серверный helper принимает только четыре перечисленных файла: копирует их из staging в собственную закрытую папку, проверяет синтаксис и набор вопросов, создаёт online backup SQLite и копии исходных файлов, затем меняет только эти файлы и перезапускает только `ege-blizko`. Проверяет `/health` и маркеры запуска нового тренажёра и ОГЭ, при сбое восстанавливает старый код, не откатывая автоматически работающую базу данных. Новые отдельные таблицы тренажёра создаются самим приложением при старте.

Рекомендуемая пользовательская проверка после выпуска: `/start specialsalts` в Telegram-боте; варианты 10/20/25/50, «Мои ошибки», «Моя статистика», а также прежние тренажёры ОГЭ и кабинет. Расссылки детям не отправлять без отдельного выбора преподавателя.
