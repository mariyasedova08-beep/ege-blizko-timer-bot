# Компактная панель урока — 02.11.2026

Статус: обновление обнаружено на публичном тестовом HTTPS; build e7da155c21fb48ae и контрольные суммы совпали. Независимые read-only SSH и публичные браузерные сценарии завершились успешно.

Уменьшены отступы/промежутки, высоты кнопок 44 → 32px (−27%), значки 19 → 15px и подписи панели презентации. Более плотная укладка освобождает высоту для PDF, без масштабирования самого слайда или страницы браузера. На touch-first устройствах через pointer:coarse сохранены зоны нажатия 44px. Подписи, отдельные цвета инструментов, сворачивание, настройки и выход из режима всего окна сохранены. Панель пробирок и химия не изменяются.

Браузерные сценарии реального локального sandbox прошли для 1440×1000 и 820×1180; скриншоты проверены визуально. Проверены кнопки от 32px, отсутствие обрезания кнопки разворачивания, письмо, PDF/доска, навигация, полноэкранный режим и экспорт.

Установка использует прежний sandbox-механизм: точный commit, SHA-256, backup, проверка health и автоматический откат; перезапускается только ege-lab-sandbox-preview.service. Nginx, сертификаты, бот, ПРЕПАДМИН, рабочая лаборатория и базы не меняются.

Откат: `python3 /var/lib/ege-lab-sandbox/installer.py --rollback`.

Runtime commit: `b84092fd794a115291a67a9242f1e1015bd5170a`.
Build: `e7da155c21fb48ae`.
Bundle SHA-256: `2cadb6e2c4e50de44bd7d1b8948899852addda0b0ef0272424ae0ea5728d1d29`.
Installer SHA-256: `71c27c911d0811cd5a4bba0b92e827451a45a42270afb282e546453645bcc02d`.

Команда установки опубликованного пакета (только sandbox):

```bash
bash <<'BASH'
set -euo pipefail
update_file=$(mktemp /tmp/lab-test-update-XXXXXX.py)
trap 'rm -f "$update_file"' EXIT
curl -fsSL --connect-timeout 10 --max-time 60 \
  'https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/c871867322467fda58030fe3023cd74cf9ab0998/deploy/bootstrap_lab_sandbox.py' \
  -o "$update_file"
printf '%s  %s\n' \
  '71c27c911d0811cd5a4bba0b92e827451a45a42270afb282e546453645bcc02d' \
  "$update_file" | sha256sum -c -
python3 "$update_file"
BASH
```

Локально выполнены 85 из 87 тестов, 2 nginx-теста пропущены из-за отсутствия nginx. Общий CI и отдельная HTTPS/nginx-проверка запускаются на одноразовом GitHub runner.

Отдельная HTTPS/nginx-проверка: https://github.com/mariyasedova08-beep/ege-blizko-timer-bot/actions/runs/41512095553 — success.
Общий CI: https://github.com/mariyasedova08-beep/ege-blizko-timer-bot/actions/runs/41512471188 — тесты пройдены, идёт подготовка браузера для повторного прогона.

Общий push CI того же финального commit: https://github.com/mariyasedova08-beep/ege-blizko-timer-bot/actions/runs/41512463314 — success (все тесты и desktop/tablet браузер). Дублирующий PR-прогон 41512471188 на момент отчёта ещё готовил Chromium.

## Проверка установленной версии

- Read-only SSH: https://github.com/mariyasedova08-beep/ege-blizko-timer-bot/actions/runs/41513601587 — success.
- Публичный HTTPS и браузер desktop/tablet: https://github.com/mariyasedova08-beep/ege-blizko-timer-bot/actions/runs/41513601268 — success.

Компактная панель доступна на https://lab-test.77-233-212-200.sslip.io/lab-app. Сохранить проект/записи перед обновлением вкладки. Production не изменялся.
