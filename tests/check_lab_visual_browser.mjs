// Browser-only visual smoke test; no Telegram credentials or server access.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium } from 'playwright';

const target = 'lab-visual-preview';
const html = fs.readFileSync(target + '/lab.html', 'utf8');
const payload = JSON.parse(fs.readFileSync(target + '/fixture.json', 'utf8'));
const cases = [
  { id: 'copper-hydroxide', pair: ['cuso4', 'naoh'], texture: 'gel' },
  { id: 'iron-two-hydroxide', pair: ['feso4', 'naoh'], texture: 'gel' },
  { id: 'iron-three-hydroxide', pair: ['fecl3', 'naoh'], texture: 'gel' },
  { id: 'aluminium-hydroxide', pair: ['alcl3', 'naoh'], texture: 'gel' },
  { id: 'barium-sulfate', pair: ['bacl2', 'h2so4'], texture: 'fine' },
  { id: 'lead-iodide', pair: ['pbno3', 'ki'], texture: 'crystal' },
  { id: 'copper-oxide-dissolves', pair: ['cuo', 'hcl'], dissolves: true, blue: true },
  { id: 'calcium-carbonate-dissolves', pair: ['caco3', 'hcl'], dissolves: true, gas: 'CO₂' },
];
const url = 'https://lab-preview.invalid/lab-app';
const browser = await chromium.launch({ headless: true });
try {
  for (const viewport of [
    { name: 'desktop', width: 1280, height: 800 },
    { name: 'mobile', width: 390, height: 844 },
  ]) {
    const page = await browser.newPage({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: 1,
    });
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(String(error)));
    await page.route('https://telegram.org/js/telegram-web-app.js', route =>
      route.fulfill({ status: 200, contentType: 'application/javascript',
        body: 'window.Telegram={WebApp:{ready(){},expand(){},initData:"",initDataUnsafe:{}}};' }));
    await page.route(url + '/api', route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) }));
    await page.route(url, route =>
      route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: html }));
    await page.goto(url, { waitUntil: 'load', timeout: 25000 });
    await page.waitForFunction(() =>
      document.querySelectorAll('#tubes .tube-slot').length === 4, null, { timeout: 15000 });

    for (const c of cases) {
      await page.evaluate(pair => {
        for (let i = 0; i < 4; i++) {
          tubes[i] = [];
          tubeHeat[i] = false;
          tubeExcess[i] = '';
        }
        tubes[0] = pair;
        selectedTube = 0;
        syncTubePicker();
        renderTubes();
      }, c.pair);
      await page.waitForTimeout(600);
      const state = await page.evaluate(() => {
        const selected = document.querySelector('#tubes .tube-slot.active-slot');
        const tube = selected?.querySelector('.tube');
        const card = selected?.querySelector('.tube-callout');
        const tubeRects = [...document.querySelectorAll('#tubes .tube-slot .tube')].map(node => {
          const r = node.getBoundingClientRect();
          return { x: r.x, right: r.right, width: r.width, height: r.height };
        });
        const tip = card?.getBoundingClientRect();
        return {
          visual: tube?.outerHTML || '',
          callout: card?.innerText || '',
          tubeRects, cardRect: tip ? { top: tip.top, bottom: tip.bottom } : null,
          liquid: tube?.querySelector('.liq')?.getAttribute('style') || '',
          animation: tube?.querySelector('.solidBed.dissolving-solid')
            ? getComputedStyle(tube.querySelector('.solidBed.dissolving-solid')).animationName : '',
          viewportWidth: window.innerWidth, viewportHeight: window.innerHeight,
          navRight: Math.max(...[...document.querySelectorAll('.lab-nav a,.lab-nav button')]
            .map(el => el.getBoundingClientRect().right)),
        };
      });
      const label = viewport.name + ' / ' + c.id;
      assert.equal(state.tubeRects.length, 4, label + ': number of tubes');
      assert.ok(state.tubeRects.every(r => r.width > 10 && r.height > 50),
        label + ': four visible tubes');
      assert.ok(state.tubeRects.every(r => r.x >= -3 && r.right <= state.viewportWidth + 3),
        label + ': tubes fit viewport');
      assert.ok(state.callout.includes('Признак:'), label + ': observation is visible');
      assert.ok(state.navRight <= state.viewportWidth + 2, label + ': header fits viewport');
      if (c.id === 'barium-sulfate' || c.id === 'aluminium-hydroxide')
        assert.ok(state.visual.includes('light-ppt'), label + ': pale precipitate contrasted');
      assert.ok(state.cardRect?.top >= -2 &&
        state.cardRect?.bottom <= state.viewportHeight + 2,
        label + ': result card stays in viewport');
      if (c.texture === 'gel') assert.ok(state.visual.includes('gel-sediment'), label);
      if (c.texture === 'fine') assert.ok(state.visual.includes('particle fine'), label);
      if (c.texture === 'crystal') assert.ok(state.visual.includes('particle crystal'), label);
      if (c.dissolves) {
        assert.ok(state.visual.includes('dissolving-solid'), label + ': consuming solid');
        assert.ok(state.animation.includes('solidConsume'), label + ': decay animated');
      }
      if (c.blue) assert.ok(state.liquid.includes('#42baf5'), label + ': blue solution');
      if (c.gas) {
        assert.ok(state.visual.includes('bubbleLayer'), label + ': rising gas');
        assert.equal((state.visual.match(/class="bubble"/g) || []).length, 22,
          label + ': a carbonate solid must fizz locally, not boil');
        assert.ok(state.callout.includes(c.gas), label + ': gas named');
      }
      await page.screenshot({ path: target + '/' + viewport.name + '-' + c.id + '.png',
        fullPage: false });
      console.log('LAB_VISUAL_OK ' + label);
    }
    assert.deepEqual(pageErrors, [], viewport.name + ': uncaught browser errors');
    await page.close();
  }
} finally {
  await browser.close();
}
console.log('LAB_VISUAL_CHECKS_COMPLETE 8 reactions x 2 viewports');
