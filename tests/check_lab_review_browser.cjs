// All HTTP routes are fixtures. No Telegram, VPS, databases or production access.
const fs=require('node:fs'), assert=require('node:assert/strict');
const {chromium}=require('playwright');
const {PDFDocument}=require('pdf-lib');
const path=require('node:path');
const root=path.dirname(require.resolve('pdfjs-dist/package.json'));
const url=process.env.LAB_SANDBOX_URL||'https://isolated-lab.invalid/lab-app';
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.LAB_CHROMIUM_PATH?{executablePath:process.env.LAB_CHROMIUM_PATH,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']}: {})});
 try{
  for(const size of [{width:1440,height:1000},{width:820,height:1180}]){
   const page=await browser.newPage({viewport:size,deviceScaleFactor:2,acceptDownloads:true});
   const errors=[];page.on('pageerror',e=>errors.push(String(e)));
   await page.route('**/*',route=>{
    const u=route.request().url();
    if(process.env.LAB_SANDBOX_URL&&(u===url||u===url+'/api'))return route.continue();
    if(u===url)return route.fulfill({contentType:'text/html',body:fs.readFileSync('lab-visual-preview/review.html','utf8')});
    if(u===url+'/api')return route.fulfill({contentType:'application/json',body:fs.readFileSync('lab-visual-preview/review.json','utf8')});
    if(u.includes('telegram-web-app'))return route.fulfill({contentType:'text/javascript',body:'window.Telegram={WebApp:{ready(){},expand(){},initData:"",initDataUnsafe:{}}}'});
    const file=u.includes('pdf.worker.min.mjs')?path.join(root,'build/pdf.worker.min.mjs'):
     u.includes('pdf.min.mjs')?path.join(root,'build/pdf.min.mjs'):
     u.includes('pdf-lib.min.js')?path.join(path.dirname(require.resolve('pdf-lib/package.json')),'dist/pdf-lib.min.js'):null;
    if(file)return route.fulfill({contentType:'text/javascript',headers:{'access-control-allow-origin':'*'},body:fs.readFileSync(file)});
    return route.abort();
   });
   await page.goto(url);
   await page.waitForFunction(()=>lessonReady);
   await page.locator('[data-page="lesson"]').click();
   // Eraser is explicitly labelled and visible, rather than an ambiguous delete glyph.
   assert.ok(await page.locator('#lessonToolEraser').isVisible());
   assert.ok(Number(await page.locator('#lessonToolEraser').evaluate(e=>getComputedStyle(e).fontSize.replace('px','')))>0);
   await page.locator('#lessonToolEraser').click();
   assert.equal(await page.evaluate(()=>lessonTool),'erase');
   await page.locator('#lessonToolPen').click();
   // Each tool keeps its own colour and width, including after erase and reload.
   await page.locator('#lessonQuickColors [data-ink="#171719"]').click();
   await page.evaluate(()=>{const width=document.getElementById('lessonPenWidth');width.value='2';width.dispatchEvent(new Event('input'))});
   await page.locator('#lessonToolMarker').click();
   await page.locator('#lessonQuickColors [data-ink="#ffce00"]').click();
   await page.evaluate(()=>{const width=document.getElementById('lessonPenWidth');width.value='6';width.dispatchEvent(new Event('input'))});
   await page.locator('#lessonToolPen').click();
   assert.equal(await page.locator('#lessonPenColor').inputValue(),'#171719');
   assert.equal(await page.locator('#lessonPenWidth').inputValue(),'2');
   await page.locator('#lessonToolEraser').click();await page.locator('#lessonToolMarker').click();
   assert.equal(await page.locator('#lessonPenColor').inputValue(),'#ffce00');
   assert.equal(await page.locator('#lessonPenWidth').inputValue(),'6');
   await page.evaluate(()=>{lessonPenColorValue='#ffffff';lessonMarkerColorValue='#ffffff';lessonTool='pen';lessonRestoreInkTools();lessonSetTool('pen')});
   assert.equal(await page.evaluate(()=>lessonPenColorValue),'#171719');
   assert.equal(await page.evaluate(()=>lessonMarkerColorValue),'#ffce00');
   for(const selector of ['#lessonToolPen','#lessonToolMarker','#lessonToolEraser','#lessonQuickColors button']){
    const target=await page.locator(selector).first().boundingBox();assert.ok(target.width>=44&&target.height>=44,selector+JSON.stringify(target));
   }
   const sampleQuality=await page.evaluate(()=>{
    const stroke={points:[{x:0,y:0}]};
    for(const x of [1,2,3,4,5])lessonAddStrokeSamples(stroke,{clientX:x,clientY:0},event=>({x:event.clientX,y:event.clientY}),{clientWidth:1,clientHeight:1});
    return stroke.points.map(point=>point.x);
   });
   assert.deepEqual(sampleQuality,[0,1,2,3,4,5]);
   // Actual chemistry and separate tubes.
   await page.evaluate(()=>{lessonSetReagent('a','nahco3');lessonSetReagent('b','koh');lessonConductStep()});
   await page.waitForFunction(()=>document.getElementById('lessonReaction').textContent.includes('Na₂CO₃ + K₂CO₃'));
   await page.evaluate(()=>lessonSelectTube(1));
   assert.equal(await page.evaluate(()=>lessonChain),null);
   await page.evaluate(()=>lessonSelectTube(0));
   assert.match(await page.locator('#lessonReaction').innerText(),/Na₂CO₃/);
   // Dissolution completes in the original tube after switching away.
   await page.evaluate(()=>{lessonClearActiveTube();lessonSetReagent('a','alcl3');lessonSetReagent('b','naoh');lessonConductStep()});
   await page.locator('#lessonExcess').click();
   await page.evaluate(()=>lessonSelectTube(1));
   await page.waitForFunction(()=>lessonTubeStates[0].dissolving===false&&lessonTubeStates[0].chain.steps[0].reaction.excess==='naoh');
   await page.evaluate(()=>lessonSelectTube(0));
   assert.equal(await page.evaluate(()=>lessonDissolving),false);
   const pouring=await page.evaluate(()=>{
    const state={},original=Date.now;let now=100000;Date.now=()=>now;
    try{
     const first=tubeMotionFor(state,['naoh'],null);now+=400;
     const resumed=tubeMotionFor(state,['naoh'],null);
     const next=tubeMotionFor(state,['naoh','hcl'],null);
     return {first,resumed,next};
    }finally{Date.now=original;}
   });
   assert.equal(pouring.first.level,22);assert.equal(pouring.first.from,0);
   assert.equal(pouring.resumed.pourAge,.4);assert.equal(pouring.next.level,44);assert.equal(pouring.next.from,22);
   // Solids remain visible while liquid pours, then dissolve only under valid conditions.
   for(const alkali of ['naoh','koh']){
    await page.evaluate(base=>{lessonClearActiveTube();lessonSetReagent('a','beo');lessonSetReagent('b',base);lessonConductStep()},alkali);
    assert.equal(await page.locator('#lessonTube1 .pourStream').count(),1);
    assert.equal(await page.locator('#lessonTube1 .dissolving-solid').count(),0);
    assert.equal(await page.locator('#lessonTube1 .solidBed').count(),1);
    await page.locator('#lessonHeat').click();
    assert.equal(await page.locator('#lessonTube1 .dissolving-solid').count(),1);
    assert.match(await page.locator('#lessonReaction').innerText(),/Be\(OH\)₄/);
    const eventClock=await page.evaluate(()=>lessonMotion.solidAt);
    await page.evaluate(()=>lessonSelectTube(1));await page.evaluate(()=>lessonSelectTube(0));
    assert.equal(await page.evaluate(()=>lessonMotion.solidAt),eventClock);
    await page.waitForFunction(()=>Number(getComputedStyle(document.querySelector('#lessonTube1 .solidBed')).opacity)<.05);
    await page.evaluate(()=>lessonSelectTube(1));await page.evaluate(()=>lessonSelectTube(0));
    assert.ok(await page.locator('#lessonTube1 .solidBed').evaluate(e=>Number(getComputedStyle(e).opacity)<.05));
   }
   // Product substitution must not remove the starting solid before the animation.
   await page.evaluate(()=>{lessonClearActiveTube();lessonSetReagent('a','cuo');lessonSetReagent('b','hcl');lessonConductStep()});
   assert.equal(await page.locator('#lessonTube1 .dissolving-solid').count(),1);
   assert.ok(await page.evaluate(()=>lessonChain!==null));
   assert.ok(await page.locator('#lessonTube1 .liq').evaluate(e=>parseFloat(e.style.height)>0));
   const solidClock=await page.evaluate(()=>lessonMotion.solidAt);
   await page.evaluate(()=>lessonRenderExperiment());
   assert.equal(await page.evaluate(()=>lessonMotion.solidAt),solidClock);
   // A dry mixture with no reaction must not become liquid or consume its solid.
   const inert=await page.evaluate(()=>tubeHTML(['beo','cuo'],0,false,false,'',{t:'z',eq:'',sign:''}));
   assert.ok(!inert.includes('dissolving-solid'));assert.ok(inert.includes('height:0%'));
   // Resize panel with keyboard.
   await page.locator('#lessonPanelDivider').focus();await page.keyboard.press('ArrowRight');
   assert.equal(await page.locator('#lessonPanelDivider').getAttribute('aria-valuenow'),'35');
   // PDF stays separate from board; annotate before switching.
   const pdf=await PDFDocument.create();pdf.addPage([600,400]);pdf.addPage([600,400]);
   const buffer=Buffer.from(await pdf.save());
   await page.locator('#lessonPDFInput').setInputFiles({name:'lesson.pdf',mimeType:'application/pdf',buffer});
   await page.waitForFunction(()=>lessonPageCount===2&&lessonPdfDocument!==null);
   await page.selectOption('#lessonPDFNavigation','2');await page.waitForFunction(()=>lessonPage===2);
   await page.selectOption('#lessonPDFNavigation','1');await page.waitForFunction(()=>lessonPage===1);
   // Real pen events with zero pressure still write; board state is untouched by PDF input.
   await page.locator('#lessonInkCanvas').scrollIntoViewIfNeeded();
   const inkBox=await page.locator('#lessonInkCanvas').boundingBox(),pen=await page.context().newCDPSession(page);
   await pen.send('Input.dispatchMouseEvent',{type:'mousePressed',x:inkBox.x+20,y:inkBox.y+20,button:'left',buttons:1,pointerType:'pen',force:0});
   for(let n=1;n<=10;n++)await pen.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:inkBox.x+20+n*3,y:inkBox.y+20+n,button:'left',buttons:1,pointerType:'pen',force:0});
   await pen.send('Input.dispatchMouseEvent',{type:'mouseReleased',x:inkBox.x+55,y:inkBox.y+32,button:'left',buttons:0,pointerType:'pen',force:0});
   assert.ok(await page.evaluate(()=>lessonCurrentStrokes().at(-1).points.length>=10));
   assert.equal(await page.evaluate(()=>lessonBoardStrokes.length),0);
   await pen.detach();
   await page.evaluate(()=>{lessonNotes['1']=[{color:'#171719',width:3,opacity:1,points:[{x:.1,y:.1},{x:.2,y:.2}]}];lessonRedrawInk()});
   assert.equal(await page.locator('#lessonPresentationTab').innerText(),'Презентация');
   await page.locator('#lessonPresentationTab').click();
   assert.equal(await page.evaluate(()=>lessonBoardMode),false);
   await page.locator('#lessonBoardToggle').click();
   await page.locator('#lessonBoardToggle').click();
   assert.equal(await page.evaluate(()=>lessonBoardMode),true);
   assert.equal(await page.locator('#lessonPresentationTab').getAttribute('aria-pressed'),'false');
   const draw=async()=>{
    const box=await page.locator('#lessonBoardCanvas').boundingBox();
    assert.ok(box.width>100&&box.height>100);
    await page.mouse.move(box.x+60,box.y+60);await page.mouse.down();
    await page.mouse.move(box.x+140,box.y+110,{steps:6});await page.mouse.up();
   };
   await page.evaluate(()=>{window.boardPaintCalls=0;window.originalBoardPaint=lessonBoardPaint;lessonBoardPaint=(...args)=>{window.boardPaintCalls++;return window.originalBoardPaint(...args)}});
   await draw();
   await page.waitForTimeout(50);
   assert.ok(await page.evaluate(()=>window.boardPaintCalls<=4));
   await page.evaluate(()=>{lessonBoardPaint=window.originalBoardPaint});
   assert.ok(await page.evaluate(()=>document.getElementById('lessonBoardCanvas').width>=document.getElementById('lessonBoardSpace').clientWidth));
   assert.equal(await page.evaluate(()=>lessonBoardStrokes.length),1);
   // Pan beyond old 2400x1600 bounds and draw there, zoom keeps scene anchor.
   await page.evaluate(()=>{lessonBoardView={x:6000,y:-3000,zoom:.5};lessonBoardDraw()});
   await draw();
   assert.ok(await page.evaluate(()=>lessonBoardStrokes[1].points[0].x>6000&&lessonBoardStrokes[1].points[0].y<0));
   const box=await page.locator('#lessonBoardCanvas').boundingBox();
   await page.mouse.move(box.x+100,box.y+100);
   const zoomAnchor=await page.evaluate(()=>lessonBoardPoint({clientX:document.getElementById('lessonBoardCanvas').getBoundingClientRect().left+100,clientY:document.getElementById('lessonBoardCanvas').getBoundingClientRect().top+100}).x);
   await page.keyboard.down('Control');await page.mouse.wheel(0,-200);await page.keyboard.up('Control');
   await page.waitForFunction(()=>lessonBoardView.zoom>.5);
   assert.ok(await page.evaluate(anchor=>Math.abs(lessonBoardPoint({clientX:document.getElementById('lessonBoardCanvas').getBoundingClientRect().left+100,clientY:document.getElementById('lessonBoardCanvas').getBoundingClientRect().top+100}).x-anchor)<2,zoomAnchor));
   // Import, move and resize an actual image at world coordinates.
   const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=80;c.height=40;c.getContext('2d').fillRect(0,0,80,40);return c.toDataURL().split(',')[1]});
   await page.locator('#lessonBoardImageInput').setInputFiles({name:'image.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')});
   await page.waitForFunction(()=>lessonBoardItems.length===1);
   const imageBefore=await page.evaluate(()=>({...lessonBoardItems[0],image:null}));
   assert.ok(imageBefore.x>6000);
   await page.evaluate(()=>{lessonBoardSnapshot();document.getElementById('lessonBoardImageSize').value='600';document.getElementById('lessonBoardImageSize').dispatchEvent(new Event('input'))});
   assert.equal(await page.evaluate(()=>lessonBoardItems[0].w),600);
   assert.equal(await page.evaluate(()=>lessonBoardItems[0].h),300);
   await page.locator('#lessonBoardUndo').click();
   assert.equal(await page.evaluate(()=>lessonBoardItems[0].w),imageBefore.w);
   await page.locator('#lessonBoardPen').click();
   // Save and reopen world coordinates and camera; reject malformed project atomically.
   let download=page.waitForEvent('download');await page.locator('#lessonBoardSaveProject').click();
   let file=await download;const project=fs.readFileSync(await file.path());
   const parsed=JSON.parse(project);assert.equal(parsed.version,2);assert.equal(parsed.pages[0].strokes.length,2);
   await page.evaluate(async content=>{await lessonBoardOpenProject(new File([content],'board.json'))},project.toString());
   assert.equal(await page.evaluate(()=>lessonBoardStrokes.length),2);
   const before=await page.evaluate(()=>JSON.stringify(lessonBoardStrokes,(key,value)=>key==='straight'?undefined:value));
   await page.evaluate(async()=>{await lessonBoardOpenProject(new File(['{"format":"wrong"}'],'bad.json'))});
   assert.equal(await page.evaluate(()=>JSON.stringify(lessonBoardStrokes,(key,value)=>key==='straight'?undefined:value)),before);
   // Old format is still readable.
   const legacy={format:'ege-blizko-board',version:1,width:2400,height:1600,activePage:0,pages:[{name:'Old',items:[],strokes:[]}]};
   await page.evaluate(async content=>lessonBoardOpenProject(new File([content],'old.json')),JSON.stringify(legacy));
   assert.equal(await page.evaluate(()=>lessonBoardPages[0].name),'Old');
   await page.evaluate(async content=>lessonBoardOpenProject(new File([content],'board.json')),project.toString());
   // Export includes offscreen scene and preserves editable project.
   download=page.waitForEvent('download');await page.locator('#lessonBoardExport').click();
   file=await download;assert.equal((await PDFDocument.load(fs.readFileSync(await file.path()))).getPageCount(),1);
   assert.equal(await page.evaluate(()=>lessonBoardStrokes.length),2);
   // Board eraser remains directly accessible when the main toolbar is collapsed.
   await page.locator('#lessonToolbarToggle').click();
   assert.ok(await page.locator('#lessonBoardEraser').isVisible());
   assert.ok(await page.locator('#lessonPresentationTab').isVisible());
   assert.ok(await page.locator('#lessonBoardToggle').isVisible());
   await page.locator('#lessonBoardEraser').click();
   assert.equal(await page.evaluate(()=>lessonTool),'erase');
   assert.equal(await page.locator('#lessonBoardEraser').getAttribute('aria-pressed'),'true');
   await page.locator('#lessonBoardPen').click();
   assert.equal(await page.evaluate(()=>lessonTool),'pen');
   assert.equal(await page.locator('#lessonBoardEraser').getAttribute('aria-pressed'),'false');
   await page.locator('#lessonToolbarToggle').click();
   // Eraser removes a stroke, undo restores it.
   await page.evaluate(()=>{lessonBoardSnapshot();lessonBoardErase(lessonBoardStrokes[1].points[1]);lessonBoardDraw()});
   assert.equal(await page.evaluate(()=>lessonBoardStrokes.length),1);
   await page.locator('#lessonBoardUndo').click();assert.equal(await page.evaluate(()=>lessonBoardStrokes.length),2);
   // PDF import to board adds pages, keeps presentation notes.
   await page.locator('#lessonBoardPDFInput').setInputFiles({name:'slides.pdf',mimeType:'application/pdf',buffer});
   await page.waitForFunction(()=>lessonBoardPages.length===3);
   assert.equal(await page.evaluate(()=>lessonNotes['1'].length),1);
   // PDF has a visible page navigator, starts fitted, and zoom never mutates ink or page geometry.
   assert.equal(await page.locator('#lessonBoardPageCounter').innerText(),'1 / 2');
   assert.equal(await page.locator('#lessonBoardPrevious').isDisabled(),true);
   assert.equal(await page.locator('#lessonBoardDocumentName').innerText(),'slides.pdf');
   await page.waitForFunction(()=>{const i=lessonBoardItems[0],v=lessonBoardView,s=document.getElementById('lessonBoardSpace');return (i.y+i.h-v.y)*v.zoom<=s.clientHeight-20});
   const fitted=await page.evaluate(()=>{const item=lessonBoardItems[0],v=lessonBoardView,space=document.getElementById('lessonBoardSpace');return {left:(item.x-v.x)*v.zoom,top:(item.y-v.y)*v.zoom,right:(item.x+item.w-v.x)*v.zoom,bottom:(item.y+item.h-v.y)*v.zoom,width:space.clientWidth,height:space.clientHeight};});
   assert.ok(fitted.left>=20&&fitted.top>=20&&fitted.right<=fitted.width-20&&fitted.bottom<=fitted.height-20,JSON.stringify(fitted));
   await page.locator('#lessonBoardPen').click();await draw();
   const pageInk=await page.evaluate(()=>JSON.stringify(lessonBoardStrokes,(key,value)=>key==='straight'?undefined:value));
   const geometry=await page.evaluate(()=>JSON.stringify(lessonBoardItems.map(i=>({x:i.x,y:i.y,w:i.w,h:i.h}))));
   const zoomBefore=await page.evaluate(()=>lessonBoardView.zoom);
   await page.locator('#lessonBoardZoomIn').click();
   assert.ok(await page.evaluate(z=>lessonBoardView.zoom>z,zoomBefore));
   await page.locator('#lessonBoardZoomOut').click();
   assert.ok(await page.evaluate(z=>Math.abs(lessonBoardView.zoom-z)<.00001,zoomBefore));
   assert.equal(await page.evaluate(()=>JSON.stringify(lessonBoardStrokes,(key,value)=>key==='straight'?undefined:value)),pageInk);
   assert.equal(await page.evaluate(()=>JSON.stringify(lessonBoardItems.map(i=>({x:i.x,y:i.y,w:i.w,h:i.h})))),geometry);
   // A real two-finger gesture changes camera, cancels its initial one-finger mark.
   await page.locator('#lessonBoardCanvas').scrollIntoViewIfNeeded();
   const cdp=await page.context().newCDPSession(page),touchBox=await page.locator('#lessonBoardCanvas').boundingBox();
   const cx=touchBox.x+touchBox.width/2,cy=touchBox.y+touchBox.height/2;
   await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:cx-35,y:cy,id:1}]});
   await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:cx-35,y:cy,id:1},{x:cx+35,y:cy,id:2}]});
   await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:cx-65,y:cy,id:1},{x:cx+65,y:cy,id:2}]});
   await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
   assert.ok(await page.evaluate(z=>lessonBoardView.zoom>z,zoomBefore));
   assert.equal(await page.evaluate(()=>JSON.stringify(lessonBoardStrokes,(key,value)=>key==='straight'?undefined:value)),pageInk);
   await cdp.detach();
   await page.locator('#lessonBoardNext').click();
   assert.equal(await page.locator('#lessonBoardPageCounter').innerText(),'2 / 2');
   assert.equal(await page.locator('#lessonBoardNext').isDisabled(),true);
   assert.equal(await page.evaluate(()=>lessonBoardStrokes.length),0);
   await page.locator('#lessonBoardPrevious').click();
   assert.equal(await page.evaluate(()=>JSON.stringify(lessonBoardStrokes,(key,value)=>key==='straight'?undefined:value)),pageInk);
   await page.evaluate(()=>{lessonBoardView.x=100000;lessonBoardView.y=-100000;lessonBoardDraw()});
   await page.locator('#lessonBoardDocument').click();
   assert.ok(await page.evaluate(()=>Math.abs(lessonBoardView.x)<10000&&Math.abs(lessonBoardView.y)<10000));
   await page.locator('#lessonBoardFit').click();
   assert.equal(await page.evaluate(()=>JSON.stringify(lessonBoardStrokes,(key,value)=>key==='straight'?undefined:value)),pageInk);
   // Document grouping, locked background, camera and per-page notes survive saved projects.
   download=page.waitForEvent('download');await page.locator('#lessonBoardSaveProject').click();file=await download;
   const pdfProject=fs.readFileSync(await file.path());
   await page.evaluate(async content=>lessonBoardOpenProject(new File([content],'pdf-board.json')),pdfProject.toString());
   assert.equal(await page.locator('#lessonBoardPageCounter').innerText(),'1 / 2');
   assert.equal(await page.evaluate(()=>lessonBoardItems[0].locked),true);
   assert.equal(await page.evaluate(()=>JSON.stringify(lessonBoardStrokes,(key,value)=>key==='straight'?undefined:value)),pageInk);
   await page.locator('#lessonBoardNext').click();await page.locator('#lessonBoardPrevious').click();
   assert.equal(await page.evaluate(()=>JSON.stringify(lessonBoardStrokes,(key,value)=>key==='straight'?undefined:value)),pageInk);
   await page.locator('#lessonBoardFullscreen').click();
   assert.equal(await page.locator('body').evaluate(e=>e.classList.contains('lesson-board-fullscreen')),true);
   await page.keyboard.press('Escape');
   assert.equal(await page.locator('body').evaluate(e=>e.classList.contains('lesson-board-fullscreen')),false);
   await page.screenshot({path:'lab-visual-preview/review-'+size.width+'.png'});
   await page.locator('#lessonPresentationTab').click();
   assert.equal(await page.locator('#lessonPresentationTab').getAttribute('aria-pressed'),'true');
   assert.equal(await page.locator('#lessonBoardToggle').innerText(),'Доска');
   assert.equal(await page.evaluate(()=>lessonPageCount),2);
   assert.equal(await page.evaluate(()=>lessonNotes['1'].length),1);
   assert.deepEqual(errors,[]);
   console.log('REVIEW_BROWSER_OK',size.width,size.height,'chemistry, tubes, PDF, world coordinates, zoom, projects v1/v2, eraser, undo, export, fullscreen');
   await page.close();
  }
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
