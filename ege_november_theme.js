/* Decorative only: never reads student data, sends requests or edits deadlines. */
(function () {
 'use strict';
 var source = document.currentScript;
 var role = source && source.getAttribute('data-cabinet-role');
 if (role !== 'teacher' && role !== 'student') return;
 // 1 November 2026, 00:00 Europe/Moscow (UTC+03:00), independent of
 // the browser's selected time zone. Until then the current skin is untouched.
 var startsAt = Date.parse('2026-10-31T21:00:00Z');
 var activated = false;
 var clockTimer;
 function activate() {
 if (document.body.getAttribute('data-ege-season') === 'november-2026') return;
 document.body.setAttribute('data-ege-season', 'november-2026');
 document.body.classList.add('ege-november');
 var app = document.getElementById('app');
 if (!app) return;
 // A small original vector illustration: bare branches, two leaves, frost
 // and Kulek's upright ears with a dusty rose scarf. No photo/network asset.
 var art = '<svg class="november-art" viewBox="0 0 180 200" aria-hidden="true" focusable="false">'+
 '<g fill="none" stroke="#887184" stroke-width="1.2" opacity=".55"><path d="M159 180Q146 117 165 19M157 95L126 57 118 30M151 119L178 85M160 63L178 38M146 163L124 140"/><path d="M128 60L104 55M127 59L135 37M173 91L177 64M163 36L150 19"/></g>'+
 '<g fill="none" stroke="#FFFDFC" stroke-width=".8" opacity=".85"><path d="M164 24L162 61M119 31L126 55M152 120L175 89"/><path d="M34 29v12m-5-6h10m-8-4 6 8m0-8-6 8M92 19v8m-3-4h6"/></g>'+
 '<g fill="#B98D90" opacity=".8"><path d="M120 129q-16-12-16 4 9 11 16-4Z"/><path d="M145 174q-13-5-10 9 11 4 10-9Z"/></g>'+
 '<ellipse cx="91" cy="188" rx="42" ry="4" fill="#998094" opacity=".12"/>'+
 '<path d="M62 156q-11 7-9 27h71q0-21-17-29" fill="#FFF9F2" stroke="#695664" stroke-width="1.2"/>'+
 '<path d="M62 116L53 62q-2-11 7-4l29 37M91 95l31-36q8-9 6 4l-6 55" fill="#3C343D" stroke="#3C343D" stroke-width="2" stroke-linejoin="round"/>'+
 '<path d="M62 91l-3-22 18 24M104 93l17-24-4 28" fill="#BA9D9F"/>'+
 '<path d="M61 104q27-25 55 0l9 33q-1 29-34 30-34-1-37-28Z" fill="#423943" stroke="#695664" stroke-width="1.1"/>'+
 '<path d="M89 94q-6 21-13 34l-6 22q19 21 41 0l-6-22q-11-16-12-34" fill="#FFF9F2"/>'+
 '<path d="M61 116q8-7 16 1l-4 8-13-1M104 118q7-8 15-1l1 7-13 1" fill="#BA916D"/>'+
 '<ellipse cx="72" cy="126" rx="2.5" ry="3" fill="#221F25"/><ellipse cx="109" cy="126" rx="2.5" ry="3" fill="#221F25"/>'+
 '<path d="M84 140q7-5 14 0-1 7-7 8-7-2-7-8" fill="#29242D"/><path d="M91 148v6m-6 0q6 5 12 0" fill="none" stroke="#695664" stroke-width="1.2" stroke-linecap="round"/>'+
 '<path d="M58 158q34 11 65-1l1 15q-35 12-68-1Z" fill="#AA6387"/><path d="M106 166l13 3 3 22-16-3Z" fill="#B77A99"/><path d="M109 189v4m5-3v4m5-3v3" stroke="#AA6387" stroke-width="1.5"/>'+
 '</svg>';
 function banner() {
  var section = document.createElement('section');
  section.className = 'november-banner';
  section.setAttribute('aria-label', 'Ноябрь. Зима близко');
  section.innerHTML = '<div class="november-eyebrow">Ноябрь · ЕГЭ БЛИЗКО</div>'+
   '<h2 class="november-title">Зима близко.<br><em>ЕГЭ тоже.</em></h2>'+
   '<p class="november-copy">'+(role === 'teacher' ?
    'Твой штаб подготовки.<br>Всё важное — под рукой.' :
    'За окном прохладнее.<br>В знаниях — больше уверенности.')+'</p>'+art+
   '<span class="november-label">Кулёк рядом</span>';
  return section;
 }
 function decorate() {
  var top = role === 'student' ? app.querySelector('#view-home > .top') : app.querySelector(':scope > .top');
  if (!top || (top.nextElementSibling && top.nextElementSibling.classList.contains('november-banner'))) return;
  top.insertAdjacentElement('afterend', banner());
 }
 var pending = false;
 var observer = new MutationObserver(function () {
  if (pending) return;
  pending = true;
  requestAnimationFrame(function () { pending = false; decorate(); });
 });
 decorate();
 observer.observe(app, {childList: true, subtree: role === 'student'});
 window.addEventListener('pagehide', function (event) {
  if (!event.persisted) observer.disconnect();
 });
 }
 function checkClock() {
  if (activated) return;
  if (clockTimer) window.clearTimeout(clockTimer);
  var remaining = startsAt - Date.now();
  if (remaining <= 0) {
   activated = true;
   document.removeEventListener('visibilitychange', checkClock);
   window.removeEventListener('pageshow', checkClock);
   activate();
   return;
  }
  // Recheck clock adjustments and wake-ups; no network or server jobs.
  clockTimer = window.setTimeout(checkClock, Math.min(remaining, 60000));
 }
 document.addEventListener('visibilitychange', checkClock);
 window.addEventListener('pageshow', checkClock);
 checkClock();
}());
