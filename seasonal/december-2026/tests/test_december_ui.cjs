const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const js = fs.readFileSync(path.join(root,'theme/december.js'),'utf8');
const css = fs.readFileSync(path.join(root,'theme/december.css'),'utf8');
const mascot = 'data:image/webp;base64,' + fs.readFileSync(path.join(root,'theme/kulek.webp')).toString('base64');
const start = Date.parse('2026-11-30T21:00:00Z');
const pause = p => p.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
async function setup(browser, surface, time, enabled=true, mobile=false) {
 const page=await browser.newPage({viewport:mobile?{width:375,height:812}:{width:1100,height:800}});
 await page.setContent(`<style>.page{display:none}.page.on{display:block}body{margin:0}.app{padding:16px}canvas{background:#fff;touch-action:none}.tube{background:rgb(180,20,130)}</style><style>${css}</style><div id="app" class="app"><div class="top">ЕГЭ БЛИЗКО</div><div id="view-home"><div class="top">Привет, Алина</div><button id="action">Уроки</button></div><section id="lesson" class="page"><canvas width="200" height="100"></canvas><div class="tube">Раствор</div></section></div>`);
 await page.evaluate(now=>{Date.now=()=>now; window.clicked=0;document.getElementById('action').onclick=()=>window.clicked++;},time);
 await page.evaluate(({js,surface,mascot,enabled})=>{const s=document.createElement('script');s.dataset.enabled=String(enabled);s.dataset.surface=surface;s.dataset.mascot=mascot;s.textContent=js;document.body.append(s);},{js,surface,mascot,enabled});
 await pause(page); return page;
}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE,args:['--no-sandbox']});
 let checks=0;
 try {
  for(const surface of ['student','teacher','lab']){
   const p=await setup(browser,surface,start-1);
   assert.equal(await p.locator('.ege-december-banner').count(),0);checks++;
   await p.evaluate(now=>{Date.now=()=>now;window.dispatchEvent(new Event('pageshow'));},start);
   await pause(p);
   assert.equal(await p.locator('.ege-december-banner').count(),1);checks++;
   await p.evaluate(()=>window.dispatchEvent(new Event('pageshow')));await pause(p);
   assert.equal(await p.locator('.ege-december-banner').count(),1);checks++;
   if(surface!=='lab'){
    await p.locator('#action').click();assert.equal(await p.evaluate(()=>window.clicked),1);checks++;
    await p.evaluate(s=>{if(s==='teacher')document.getElementById('app').innerHTML='<div class="top">Новая карточка</div>';else document.getElementById('view-home').innerHTML='<div class="top">Новая карточка</div>';},surface);
    await pause(p);assert.equal(await p.locator('.ege-december-banner').count(),1);checks++;
   } else {
    assert.equal(await p.locator('.ege-december-banner').isVisible(),false);checks++;
    await p.evaluate(()=>document.getElementById('lesson').classList.add('on'));
    assert.equal(await p.locator('.ege-december-banner').isVisible(),true);checks++;
    assert.equal(await p.locator('canvas').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(255, 255, 255)');checks++;
    assert.equal(await p.locator('.tube').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(180, 20, 130)');checks++;
    await p.locator('canvas').evaluate(c=>{c.getContext('2d').fillRect(3,3,1,1);c.addEventListener('pointerdown',()=>window.clicked++);});
    await p.locator('canvas').click({position:{x:10,y:10}});
    assert.equal(await p.evaluate(()=>window.clicked),1);checks++;
    await p.evaluate(()=>document.getElementById('lesson').requestFullscreen());
    assert.equal(await p.locator('.ege-december-banner').isVisible(),false);checks++;
    await p.evaluate(()=>document.exitFullscreen());
   }
   await p.close();
   const disabled=await setup(browser,surface,start+1000,false);
   assert.equal(await disabled.locator('.ege-december-banner').count(),0);checks++;await disabled.close();
   const mobile=await setup(browser,surface,start,true,true);
   if(surface==='lab')await mobile.evaluate(()=>document.getElementById('lesson').classList.add('on'));
   assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);checks++;
   await mobile.emulateMedia({media:'print'});assert.equal(await mobile.locator('.ege-december-banner').isVisible(),false);checks++;
   await mobile.close();
  }
  console.log('BROWSER_OK:',checks,'checks; date boundary, flags, rerenders, controls, mobile, fullscreen, print, canvas and tube colors');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
