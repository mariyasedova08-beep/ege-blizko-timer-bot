# ПРЕПОДМИН — автоматические тесты и отдельное безопасное развёртывание

Дата: 14.10.2026. Существующий **ЕГЭ БЛИЗКО не затрагивать**.

## Что подготовлено

- [x] GitHub Actions: `.github/workflows/prepodmin-ci.yml` в ветке `feature/prepodmin-timeweb-migration-20261013`, триггер на её изменения, ограниченный набор тестов на **временных SQLite**. Без SSH-ключей, без запуска продакшена.
- [x] GitHub Actions: `.github/workflows/prepodmin-safe-deploy.yml` в **main**. Запускается только `workflow_dispatch` (вручную), только из `main`, при явном выборе `DEPLOY_PREPODMIN_ONLY`. Проверяет SHA последней версии целевой ветки и **успешный push CI на том же SHA**.
- [x] Защищённый выпуск через `prepodmin-production` (GitHub Environment), три отдельных секрета `PREPODMIN_SSH_KEY`, `PREPODMIN_SSH_HOST`, `PREPODMIN_SSH_KNOWN_HOSTS`.
- [x] Серверный скрипт `deployment/prepodmin/prepodmin_release_runner.sh`: проверка адреса ветки, разрешённых файлов, незапятнанного Git-каталога, snapshot SQLite перед выпуском, рестарт **только** `prepodmin.service`, проверка `/health` + HTTPS `/webapp` и `/student`, откат к предыдущему коммиту при сбое.
- [x] Ограниченная SSH-команда `prepodmin_ssh_gate.sh` для отдельного пользователя `prepodmin-deploy`. Никакой интерактивной оболочки и port-forwarding для ключа GitHub.
- [ ] На Timeweb установить root-owned `/usr/local/sbin/prepodmin-release` и SSH-gate, ограниченную учётную запись. **До этого GitHub Actions не сможет развернуть код**.
- [ ] Создать отдельный ключ с рабочей машины; установить только публичную часть на сервер; сохранить **приватную часть только как GitHub Environment secret**, не в репозитории и не в чате.
- [ ] В GitHub создать Environment `prepodmin-production`, настроить approval (reviewer), три environment secrets.
- [ ] Выполнить тестовый ручной запуск и проверить, что поломанный выпуск автоматически откатывает код, а `ege-blizko` остаётся active.
- [ ] Независимые off-site резервные копии, проверка восстановления, юридическая/безопасностная оценка перед приёмом чужих персональных данных.

**Никаких автоматических релизов от push пока нет.** Это намеренная защита до завершения пилота.

## Единоразовая серверная настройка

Только после успешного CI, через знакомый доверенный SSH вход root с Windows PowerShell:

```powershell
ssh root@77.233.212.200 "set -e; runuser -u prepodmin -- git -C /opt/bots/prepodmin/current pull --ff-only origin feature/prepodmin-timeweb-migration-20261013; bash /opt/bots/prepodmin/current/deployment/prepodmin/install_deploy_access.sh"
```

Ожидаем `PREPODMIN_DEPLOY_ACCESS_PREPARED`. Эта команда **не перезапускает** боты. Скрипт создаёт пользователя `prepodmin-deploy` без входа по паролю, отдельную директорию `authorized_keys`, копии проверенных скриптов с правами `root:root`, ограниченное sudo. **Не давай доступ GitHub через root-ключ Timeweb или ключ ЕГЭ БЛИЗКО.**

Создать отдельный SSH-ключ локально (Windows PowerShell):

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\prepodmin-gha" -C "prepodmin-gha"
```

При запросе passphrase нажать Enter дважды (ключ без пароля предназначен только для GitHub Actions с ограниченным доступом). Не показывать приватный ключ в чате. Публичную часть установить так:

```powershell
Get-Content "$env:USERPROFILE\.ssh\prepodmin-gha.pub" | ssh root@77.233.212.200 "bash /opt/bots/prepodmin/current/deployment/prepodmin/install_deploy_public_key.sh"
```

Ожидаем `PREPODMIN_RESTRICTED_PUBLIC_KEY_INSTALLED`. Скрипт откажется повторно добавлять ключ и не затронет root-SSH.

## Github Environment и секреты

В `https://github.com/mariyasedova08-beep/ege-blizko-timer-bot/settings/environments` создать окружение `prepodmin-production`; включить Required reviewers и назначить согласующего с учётом политик самоподтверждения. Добавить **environment secrets** (не repository secrets):

| Secret | Значение |
|---|---|
| `PREPODMIN_SSH_HOST` | `77.233.212.200` |
| `PREPODMIN_SSH_KEY` | Полный приватный ключ `prepodmin-gha` с локального компьютера (не отправлять в чат) |
| `PREPODMIN_SSH_KNOWN_HOSTS` | Проверенная host-key строка `77.233.212.200 ssh-ed25519 AAAA...` |

Получить публичный **host key** через уже проверенный SSH root, а не доверять слепо `ssh-keyscan`. Его fingerprint можно сверить с SSH known_hosts и консолью Timeweb. Приватные host key-файлы никогда не копировать.

## Ручной выпуск

1. Убедиться, что последний `PREPODMIN — isolated tests` завершился `success` на нужном SHA.
2. GitHub → Actions → `PREPODMIN — guarded manual Timeweb release` → Run workflow → ветка **main**.
3. Указать полный SHA уже проверенного коммита из целевой ветки и выбрать `DEPLOY_PREPODMIN_ONLY`.
4. После успешного CI gate подтвердить deployment в окружении `prepodmin-production`, если настроено требование согласования.
5. Проверить `PREPODMIN_DEPLOY_OK`, `EGE_BLIZKO_UNTOUCHED_AND_ACTIVE`, `/health`, открытие преподавательского WebApp и работу Telegram.

**Если провал:** скрипт пытается откатить **код** к предыдущему коммиту и перезапустить только ПРЕПОДМИН. Копия БД создана и сохраняется для ручного восстановления. Он не делает автоматический rollback схемы SQLite; будущие несовместимые миграции требуют отдельного плана. При проблемах не запускать повторный релиз вслепую.

## Контрольные ограничения

- Не менять `.github/workflows/timeweb-safe-deploy.yml`, `/opt/bots/ege-blizko`, `ege-blizko.service` и ключи/секреты ЕГЭ.
- GitHub release workflow разрешён только из `main` и только через выбор и успешный CI нужного SHA; push не выпускает бота.
- Root исполняет только файл `/usr/local/sbin/prepodmin-release`, заранее установленный и принадлежащий root; **не исполнять от root `/opt/bots/prepodmin/current/deployment/prepodmin/prepodmin_release_runner.sh` непосредственно при каждом выпуске**, т.к. это код в рабочем дереве владельца `prepodmin`.
- Не добавлять ключи или .env в публичный репозиторий.
- GitHub Actions CI не доказывает отсутствие всех ошибок: перед приглашением чужих преподавателей проверить реальную безопасность API, восстановление SQLite из off-site копии, уведомления, тест двух отдельных преподавателей.
- Дополнительный риск: текущий `prepodmin-backup.service` запускает root процесс Python из изменяемого Git checkout. Для эксплуатации с чужими данными нужно перевести его на root-owned фиксированный экземпляр или непривилегированный резервный сервис; текущие локальные копии работают, но эта настройка требует hardening.
