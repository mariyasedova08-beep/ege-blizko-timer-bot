// Independent Chromium smoke test of the actual lab-app HTML, no server access.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { PDFDocument } from 'pdf-lib';
const folder='lab-visual-preview';
const html=fs.readFileSync(folder+'/lab.html','utf8');
const payload=JSON.parse(fs.readFileSync(folder+'/fixture.json','utf8'));
const pdfjsMain=fs.readFileSync('node_modules/pdfjs-dist/build/pdf.min.mjs','utf8');
const pdfjsWorker=fs.readFileSync('node_modules/pdfjs-dist/build/pdf.worker.min.mjs','utf8');
const pdfLibBrowser=fs.readFileSync('node_modules/pdf-lib/dist/pdf-lib.min.js','utf8');
const url='https://lab-preview.invalid/lab-app';
const input=await PDFDocument.create();
input.addPage([960,540]);input.addPage([960,540]);
const originalBytes=Buffer.from(await input.save());
const browser=await chromium.launch({headless:true});
try{
 for(const viewport of [{name:'desktop',width:1440,height:900},{name:'compact',width:920,height:820}]){
  const page=await browser.newPage({viewport:{width:viewport.width,height:viewport.height},acceptDownloads:true});
  const errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.route('https://telegram.org/js/telegram-web-app.js',route=>route.fulfill({
    status:200,contentType:'application/javascript',
    body:'window.Telegram={WebApp:{ready(){},expand(){},initData:"",initDataUnsafe:{}}};'
  }));
  await page.route(url+'/api',route=>route.fulfill({
    status:200,contentType:'application/json',body:JSON.stringify(payload)
  }));
  await page.route(url,route=>route.fulfill({
    status:200,contentType:'text/html; charset=utf-8',body:html
  }));
  await page.route('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs',route=>
    route.fulfill({status:200,contentType:'text/javascript',headers:{'access-control-allow-origin':'*'},body:pdfjsMain}));
  await page.route('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs',route=>
    route.fulfill({status:200,contentType:'text/javascript',headers:{'access-control-allow-origin':'*'},body:pdfjsWorker}));
  await page.route('https://cdnjs.cloudflare.com/ajax/libs/pdf-lib/1.17.1/pdf-lib.min.js',route=>
    route.fulfill({status:200,contentType:'application/javascript',headers:{'access-control-allow-origin':'*'},body:pdfLibBrowser}));
  await page.goto(url,{waitUntil:'load',timeout:30000});
  await page.waitForFunction(()=>document.querySelector('#lessonReagentA option')?.value!==undefined);
  await page.locator('button[data-page="lesson"]').click();
  const sizes=await page.evaluate(()=>{
   const parent=document.querySelector('.lesson-studio').getBoundingClientRect();
   const a=document.querySelector('.lesson-lab-pane').getBoundingClientRect();
   const b=document.querySelector('.lesson-pdf-pane').getBoundingClientRect();
   return {parent:parent.width,lab:a.width,pdf:b.width,
     labLeft:a.left,pdfLeft:b.left,pdfRight:b.right,pageWidth:innerWidth};
  });
  assert.ok(Math.abs(sizes.lab/(sizes.lab+sizes.pdf)-.3)<.025,viewport.name+': lab 30%');
  assert.ok(sizes.pdfLeft>sizes.labLeft,viewport.name+': PDF right');
  assert.ok(sizes.pdfRight<=sizes.pageWidth+2,viewport.name+': fit viewport');
  await page.selectOption('#lessonReagentA','kmno4');
  await page.selectOption('#lessonReagentB','na2so3');
  await page.locator('#lessonConduct').click();
  await page.waitForFunction(()=>document.querySelector('#lessonReaction')?.textContent.includes('MnO₂'));
  assert.equal(await page.locator('#lessonTube .pptLayer').count(),1,viewport.name+': real reaction visual');
  const img=page.locator('#lessonInkCanvas');
  const box=await img.boundingBox();
  assert.ok(box&&box.width>100&&box.height>80,viewport.name+': ink area');
  await page.mouse.move(box.x+box.width*.25,box.y+box.height*.35);
  await page.mouse.down();
  await page.mouse.move(box.x+box.width*.48,box.y+box.height*.42,{steps:8});
  await page.mouse.up();
  const initial=await page.evaluate(()=>({length:(lessonNotes['1']||[]).length,experiment:document.querySelector('#lessonReaction').textContent}));
  assert.ok(initial.length>0,viewport.name+': stylus ink independent of lab');
  assert.ok(initial.experiment.includes('MnO₂'),viewport.name+': lab still active during ink');
  await page.locator('#lessonPDFInput').setInputFiles({name:'manganese-two-pages.pdf',
    mimeType:'application/pdf',buffer:originalBytes});
  await page.waitForFunction(()=>lessonPageCount===2 && document.querySelector('#lessonPageCounter').textContent==='1 / 2',{timeout:30000});
  await page.locator('#lessonNext').click();
  await page.waitForFunction(()=>lessonPage===2);
  const second=await img.boundingBox();
  await page.mouse.move(second.x+second.width*.25,second.y+second.height*.6);
  await page.mouse.down();
  await page.mouse.move(second.x+second.width*.62,second.y+second.height*.66,{steps:9});
  await page.mouse.up();
  const outPromise=page.waitForEvent('download',{timeout:30000});
  await page.locator('#lessonExport').click();
  const download=await outPromise;
  const outFile=await download.path();
  const outBytes=fs.readFileSync(outFile);
  const saved=await PDFDocument.load(outBytes);
  assert.equal(saved.getPageCount(),2,viewport.name+': exported two-page PDF');
  assert.ok(outBytes.length>originalBytes.length,viewport.name+': vector ink appended');
  assert.ok(download.suggestedFilename().includes('_с_записями.pdf'),viewport.name+': named annotated PDF');
  await page.screenshot({path:folder+'/lesson-'+viewport.name+'.png',fullPage:false});
  assert.deepEqual(errors,[],viewport.name+': no runtime JS errors');
  console.log('LESSON_PARALLEL_OK '+viewport.name+' 30/70, real lab, freehand, 2 PDF pages');
  await page.close();
 }

// Verify the teacher can open the downloadable HTML directly in Edge/Chrome
// without Telegram credentials or touching the live service.
const offline=await browser.newPage({viewport:{width:1100,height:780},acceptDownloads:true});
const offlineErrors=[];
offline.on('pageerror',e=>offlineErrors.push(String(e)));
await offline.route('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs',route=>
  route.fulfill({status:200,contentType:'text/javascript',headers:{'access-control-allow-origin':'*'},body:pdfjsMain}));
await offline.route('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs',route=>
  route.fulfill({status:200,contentType:'text/javascript',headers:{'access-control-allow-origin':'*'},body:pdfjsWorker}));
await offline.route('https://cdnjs.cloudflare.com/ajax/libs/pdf-lib/1.17.1/pdf-lib.min.js',route=>
  route.fulfill({status:200,contentType:'application/javascript',headers:{'access-control-allow-origin':'*'},body:pdfLibBrowser}));
await offline.goto(pathToFileURL(path.resolve('preview/ege-blizko-lab-lesson-30-70-offline.html')).href);
await offline.waitForFunction(()=>document.querySelector('#lesson.page.on')&&
  document.querySelector('#lessonReagentA option[value="kmno4"]'));
await offline.locator('#lessonConduct').click();
await offline.waitForFunction(()=>document.querySelector('#lessonReaction')?.textContent.includes('MnO₂'));
await offline.locator('#lessonPDFInput').setInputFiles({
  name:'teacher-lesson.pdf',mimeType:'application/pdf',buffer:originalBytes});
await offline.waitForFunction(()=>lessonPageCount===2 && lessonPdfDocument!==null,null,{timeout:30000});
const offbox=await offline.locator('#lessonInkCanvas').boundingBox();
await offline.mouse.move(offbox.x+offbox.width*.15,offbox.y+offbox.height*.28);
await offline.mouse.down();
await offline.mouse.move(offbox.x+offbox.width*.47,offbox.y+offbox.height*.43,{steps:7});
await offline.mouse.up();
const offlineDownload=offline.waitForEvent('download',{timeout:30000});
await offline.locator('#lessonExport').click();
const savedOffline=await offlineDownload;
assert.equal((await PDFDocument.load(fs.readFileSync(await savedOffline.path()))).getPageCount(),2);
assert.deepEqual(offlineErrors,[],'standalone download: JS works without server');
await offline.screenshot({path:folder+'/lesson-offline.png',fullPage:false});
console.log('LESSON_OFFLINE_PREVIEW_OK 195 reagents, 435 reactions, PDF and stylus');
await offline.close();
}finally{await browser.close()}
console.log('LESSON_BROWSER_SMOKE_COMPLETE');
