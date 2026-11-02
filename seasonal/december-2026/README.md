# ЕГЭ БЛИЗКО — декабрьская тема с Кульком

Review package only. Target start: **1 December 2026, 00:00 Europe/Moscow**
(`2026-11-30T21:00:00Z`). The package is disabled unless explicitly enabled in
an injected script. It does not schedule a server deployment or send messages.

## Scope

Student and teacher cabinet decoration plus a compact banner inside the lab's
`#lesson` page. Uses the existing tricolor Kulyok mascot with upright ears;
the red hat is a separate CSS accessory. Existing course data, buttons,
reward accounting, chemistry, tube colors, PDFs and canvas handlers are retained.
This is the theme implementation, not a redesign of the cabinet navigation or
an implementation of the concept board's sample progress figures.

No animation, cursor interception, sounds, account reads, network calls, storage
writes or background snow. Print and fullscreen hide the decoration. The lab
theme never attaches drawing/pointer handlers or redraws the lesson canvas.

## Prepare a review copy

`python3 prepare_december_theme.py INPUT.html OUTPUT.html --surface student`

Supported surfaces: `student`, `teacher`, `lab`. The output must be new and
outside managed service paths. The command never imports the bot or edits the
source. Add `--enable-date-switch` only in an isolated review copy to exercise
the date gate. Before December the existing appearance remains intact.

## Integration and release

Keep cabinet and lab releases separate. Before publication compare the exact
live templates with the reviewed sources: the lab sandbox is changing in a
separate work stream. Adapt to the live lab container only if its lesson page
has changed from `#lesson.page.on`. Never overwrite the live lab with this
package's reference preview.

Cabinet adapters target the existing student `#view-home > .top` and teacher
`#app > .top`. Renders are observed without replacing app markup. The December
CSS hides the prior November banner once active, preserving its underlying code.

Before enabling release: check actual VPS template rendering/CSP, mobile width,
screen reader order, fullscreen, saved pen/marker settings, PDF export and all
existing cabinet buttons. A correct local preview does not verify the VPS.

The mascot is a 288 px WebP export of the existing transparent PNG (about 25 KB),
embedded in each review document to avoid adding an unreviewed static asset route.
Its markings and proportions are retained; the hat is a separate UI accessory.

## Rollback

Before a separately approved release save the exact live templates and hashes,
preserving owner and mode. To roll back restore only those templates from the
release backup, or remove the two marked `data-ege-december-package` elements.
Keep the old source intact until acceptance. No DB rollback/migration is needed.
Do not restart services, merge or install automatically from this branch.
