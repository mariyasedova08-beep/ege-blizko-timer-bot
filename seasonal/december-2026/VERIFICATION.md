# Review validation — 2 November 2026

Target release date: **1 December 2026 at 00:00 Moscow**.

## Checked locally

- Five Python builder tests passed: original controls/canvas retained, Moscow
  boundary, explicit enable flag, duplicate injection refusal, partial/foreign
  document refusal.
- 28 Chromium checks passed: before/at midnight boundary for all three surfaces,
  disabled flag, repeat pageshow, rerender idempotency, working buttons,
  375 px mobile width, print, lab-only visibility, fullscreen,
  unchanged white canvas and purple tube, pointer drawing listener preserved.
- Real cabinet templates from main commit
  `53cb19b8c5e37224a88c5da3ea100579ea411595` rendered in Chromium using
  explicitly synthetic local fixtures, without page JavaScript errors.
- Laboratory reference from commit
  `7089040e6ecf2c13e790a47080595790dc266cee`,
  `preview/ege-blizko-lab-lesson-30-70-offline.html`, rendered in lesson mode
  without page JavaScript errors. This is a reference, not proof of current VPS
  compatibility: sandbox chemistry/board work is ongoing separately.
- Visual inspection of all three local screens: source mascot retained,
  compact hat leaves ear tips visible, banner does not overlap working controls.
- `node --check theme/december.js` passed.

## Reproduce from this directory

```
python3 -m unittest discover -s tests -v
node --check theme/december.js
PLAYWRIGHT_MODULE=/absolute/path/to/playwright \
CHROMIUM_EXECUTABLE=/absolute/path/to/chromium node tests/test_december_ui.cjs
```

The browser suite uses synthetic markup and does not contact Telegram or the
live VPS. Playwright/Chromium are test dependencies only, not bot dependencies.

## Release status

**Review package prepared; not installed and not scheduled on the server.**
No production, lab sandbox or PREPODMIN files/services were changed. No messages
sent, database writes performed, credentials accessed, or service restarts run.

Before a separately approved publication: compare live templates and package
hashes; verify CSP permits existing inline style/script and a data-image; make
and verify backups; apply separately to cabinets and to the current lab build;
test actual navigation, PDF export, pen/marker settings and full screen; verify
health and logs. Keep a restore path for each service/template set.

Do not present the earlier generated concept board's sample statistics or
navigation as implemented features. This package adds the reviewed seasonal
decoration to the existing screens.
