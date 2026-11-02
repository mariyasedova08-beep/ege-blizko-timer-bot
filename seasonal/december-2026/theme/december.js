/* Presentation only. No account data, requests, storage or application handlers. */
(function () {
 'use strict';
 var script = document.currentScript;
 if (!script || script.dataset.enabled !== 'true') return;
 var surface = script.dataset.surface;
 if (['student', 'teacher', 'lab'].indexOf(surface) < 0) return;
 var asset = script.dataset.mascot;
 if (!asset) return;
 var starts = Date.parse('2026-11-30T21:00:00Z');
 var timer, pending = false, active = false, observer;
 function decorate() {
  if (!active) return;
  var host = surface === 'lab' ? document.getElementById('lesson') :
   document.querySelector(surface === 'student' ? '#view-home > .top' : '#app > .top');
  if (!host) return;
  var parent = surface === 'lab' ? host : host.parentElement;
  if (parent.querySelector(':scope > .ege-december-banner')) return;
  var banner = document.createElement('section');
  banner.className = 'ege-december-banner';
  banner.setAttribute('aria-label', 'Зимняя тема ЕГЭ БЛИЗКО');
  var title = document.createElement('strong');
  title.className = 'ege-december-title';
  title.textContent = surface === 'lab' ? 'Зимняя химическая мастерская' : 'Зима близко. Мы справимся.';
  var copy = document.createElement('span');
  copy.className = 'ege-december-copy';
  copy.textContent = surface === 'teacher' ? 'Твой уютный штаб подготовки' :
   surface === 'student' ? 'Маленькие шаги — большой прогресс' : 'Кулёк рядом';
  var mascot = document.createElement('span');
  mascot.className = 'ege-december-mascot';
  mascot.setAttribute('aria-hidden', 'true');
  var image = document.createElement('img');
  image.src = asset; image.alt = ''; image.width = 1212; image.height = 1297;
  image.draggable = false; image.decoding = 'async';
  var hat = document.createElement('span');
  hat.className = 'ege-december-hat';
  mascot.append(image, hat);
  banner.append(title, copy, mascot);
  if (surface === 'lab') host.prepend(banner);
  else host.insertAdjacentElement('afterend', banner);
 }
 function queueDecorate() {
  if (pending) return;
  pending = true;
  window.requestAnimationFrame(function () { pending = false; decorate(); });
 }
 function checkClock() {
  window.clearTimeout(timer);
  if (active) { queueDecorate(); return; }
  if (Date.now() >= starts) {
   active = true;
   document.body.classList.add(surface === 'lab' ? 'ege-december-lab' : 'ege-december-cabinet');
   decorate();
   var root = document.getElementById('app') || (surface === 'lab' && document.getElementById('lesson'));
   if (root) { observer = new MutationObserver(queueDecorate); observer.observe(root, {childList: true, subtree: true}); }
  } else timer = window.setTimeout(checkClock, Math.min(60000, starts - Date.now()));
 }
 document.addEventListener('visibilitychange', checkClock);
 window.addEventListener('pageshow', checkClock);
 window.addEventListener('pagehide', function (event) {
  if (!event.persisted) { window.clearTimeout(timer); if (observer) observer.disconnect(); }
 });
 checkClock();
}());
