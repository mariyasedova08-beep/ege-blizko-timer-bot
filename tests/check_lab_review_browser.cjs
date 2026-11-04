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
   const page=await browser.newPage({viewport:size,deviceScaleFactor:2,acceptDownloads:true,...(process.env.LAB_PILOT_TEST_USER?{httpCredentials:{username:process.env.LAB_PILOT_TEST_USER,password:process.env.LAB_PILOT_TEST_PASSWORD}}:{})});
   const errors=[];page.on('pageerror',e=>errors.push(String(e)));
   await page.route('**/*',route=>{
    const u=route.request().url();
    if(process.env.LAB_SANDBOX_URL&&(u===url||u===url+'/api'||u===new URL('/healthz',url).href))return route.continue();
    if(u===new URL('/healthz',url).href)return route.fulfill({contentType:'application/json',body:JSON.stringify({sandbox:true,build:'0000000000000000'})});
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
   await page.evaluate(()=>{tubes[0]=['mno2','hcl'];selectedTube=0;renderTubes()});
   assert.ok(await page.locator('#heatHint').isVisible());
   assert.equal(await page.locator('#heat').getAttribute('aria-describedby'),'heatHint');
   await page.evaluate(()=>{tubeHeat[0]=true;renderTubes()});
   assert.ok(await page.locator('#heatHint').isHidden());
   await page.evaluate(()=>{tubes[0]=[];tubeHeat[0]=false;renderTubes()});
   // Independent DOM in the free laboratory: touching tube 2 cannot restart tube 1.
   await page.evaluate(()=>{
    tubes[0]=['cuso4','naoh'];selectedTube=0;renderTubes();
    window.freeTubeRef=document.querySelector('#tubes .tube-slot .tube');window.freePptRef=window.freeTubeRef.querySelector('.pptLayer');
    window.freeMutations=0;window.freeObserver=new MutationObserver(records=>window.freeMutations+=records.length);window.freeObserver.observe(window.freeTubeRef,{childList:true,subtree:true});
    selectedTube=1;tubes[1]=['fecl3','naoh'];renderTubes();tubeHeat[1]=true;renderTubes();selectedTube=0;renderTubes();
   });
   assert.ok(await page.evaluate(()=>document.querySelector('#tubes .tube-slot .tube')===window.freeTubeRef&&window.freeTubeRef.querySelector('.pptLayer')===window.freePptRef&&window.freePptRef!==null));
   assert.equal(await page.evaluate(()=>window.freeMutations),0);
   await page.evaluate(()=>{window.freeObserver.disconnect();tubes=[[],[],[],[]];tubeHeat=[false,false,false,false];tubeChain=[null,null,null,null];selectedTube=0;renderTubes()});
   await page.locator('[data-page="lesson"]').click();
   // Pilot help is explicit; feedback contains no uploaded lesson or handwritten data.
   assert.ok(await page.locator('#lessonPilotBar').isVisible());
   await page.locator('#lessonPilotHelp').click();
   assert.ok(await page.locator('#lessonPilotDialog').isVisible());
   assert.match(await page.locator('#lessonPilotGuide').innerText(),/Доска автоматически сохраняется локально/);
   await page.keyboard.press('Escape');
   assert.ok(await page.locator('#lessonPilotDialog').isHidden());
   await page.locator('#lessonPilotReport').click();
   await page.locator('#lessonPilotMessage').fill('Проверка сообщения');
   const reportDownload=page.waitForEvent('download');await page.locator('#lessonPilotDownload').click();
   const reportFile=await reportDownload;const report=JSON.parse(fs.readFileSync(await reportFile.path(),'utf8'));
   assert.equal(report.format,'ege-blizko-pilot-feedback');assert.equal(report.message,'Проверка сообщения');
   assert.match(report.build,/^[a-f0-9]{16}$/);
   assert.deepEqual(Object.keys(report).sort(),['format','version','createdAt','build','message','browser','viewport','workspace','tool','reaction'].sort());
   assert.deepEqual(Object.keys(report.reaction).sort(),['a','b','heated','medium']);
   await page.locator('#lessonPilotClose').click();
   const storage=await page.evaluate(()=>{
    lessonNotes={'1':[{color:'#171719',width:2,points:[{x:.1,y:.2},{x:.2,y:.3}]}]};lessonSaveLocal();
    lessonNotes={};lessonRestoreLocal();const restored=lessonNotes['1'][0].points.length;
    const descriptor=Object.getOwnPropertyDescriptor(Storage.prototype,'setItem');
    Object.defineProperty(Storage.prototype,'setItem',{configurable:true,value(){throw new DOMException('full','QuotaExceededError')}});
    try{lessonSaveLocal();return {restored,status:document.getElementById('lessonPilotSaveState').textContent};}
    finally{Object.defineProperty(Storage.prototype,'setItem',descriptor);lessonNotes={};lessonSaveLocal();}
   });
   assert.equal(storage.restored,2);assert.match(storage.status,/не сохранены/);
   // Eraser is explicitly labelled and visible, rather than an ambiguous delete glyph.
   assert.ok(await page.locator('#lessonToolEraser').isVisible());
   assert.ok(Number(await page.locator('#lessonToolEraser').evaluate(e=>getComputedStyle(e).fontSize.replace('px','')))>0);
   await page.locator('#lessonToolEraser').click();
   assert.equal(await page.evaluate(()=>lessonTool),'erase');
   await page.locator('#lessonToolPen').click();
   // Tool selection is direct: line -> marker/pen/eraser, without manually toggling off.
   await page.locator('#lessonStraightLine').click();
   assert.equal(await page.evaluate(()=>lessonLineMode),true);
   assert.equal(await page.locator('#lessonToolPen').getAttribute('aria-pressed'),'false');
   await page.locator('#lessonToolMarker').click();
   assert.equal(await page.evaluate(()=>lessonLineMode),false);
   assert.equal(await page.locator('#lessonStraightLine').getAttribute('aria-pressed'),'false');
   assert.equal(await page.locator('#lessonToolMarker').getAttribute('aria-pressed'),'true');
   await page.locator('#lessonStraightLine').click();await page.locator('#lessonToolEraser').click();
   assert.equal(await page.evaluate(()=>lessonLineMode),false);
   await page.locator('#lessonToolPen').click();
   // Lab handwriting does not block selection of another tube or chemistry buttons.
   await page.locator('#lessonLabPen').click();
   await page.locator('[data-lesson-tube="1"] > span').first().click();
   assert.equal(await page.evaluate(()=>lessonActiveTube),1);
   assert.equal(await page.evaluate(()=>lessonLabInkTool),'view');
   await page.locator('#lessonLabPen').click();await page.locator('#lessonReset').click();
   assert.equal(await page.evaluate(()=>lessonLabInkTool),'view');
   await page.locator('[data-lesson-tube="0"] > span').first().click();
   // Clicking another tool dismisses settings, while preserving separate colours.
   await page.locator('.lesson-extra-menu summary').click();
   assert.equal(await page.locator('.lesson-extra-menu').evaluate(e=>e.open),true);
   await page.locator('#lessonToolPen').click();
   assert.equal(await page.locator('.lesson-extra-menu').evaluate(e=>e.open),false);
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
    const target=await page.locator(selector).first().boundingBox();assert.ok(target.width>=32&&target.height>=32,selector+JSON.stringify(target));
   }
   const sampleQuality=await page.evaluate(()=>{
    const stroke={points:[{x:0,y:0}]};lessonBeautify=false;
    for(const x of [1,2,3,4,5])lessonAddStrokeSamples(stroke,{clientX:x,clientY:0},event=>({x:event.clientX,y:event.clientY}),{clientWidth:1,clientHeight:1});
    lessonBeautify=true;return stroke.points.map(point=>point.x);
   });
   assert.deepEqual(sampleQuality,[0,1,2,3,4,5]);
   const beautify=await page.evaluate(()=>{
    const points=Array.from({length:81},(_,i)=>({x:i,y:i===0||i===80?0:(i%2?.9:-.9)}));
    const stroke={points:structuredClone(points),opacity:1};lessonBeautify=true;lessonFinishStroke(stroke);
    const off={points:structuredClone(points),opacity:1};lessonBeautify=false;lessonFinishStroke(off);
    const line={points:structuredClone(points),opacity:1,straight:true};lessonBeautify=true;lessonFinishStroke(line);
    return {input:points,result:stroke.points,off:off.points,line:line.points};
   });
   assert.deepEqual(beautify.result[0],beautify.input[0]);assert.deepEqual(beautify.result.at(-1),beautify.input.at(-1));
   assert.ok(Math.max(...beautify.result.slice(5,-5).map(p=>Math.abs(p.y)))<.3);
   assert.deepEqual(beautify.off,beautify.input);assert.deepEqual(beautify.line,beautify.input);
   const liveInk=await page.evaluate(()=>{
    function trace(scale=1,extra={}){
     const stroke={points:[{x:0,y:0}],...extra};
     for(let i=1;i<=100;i++)lessonAddStrokeSamples(stroke,{timeStamp:i*8,clientX:i*.4,clientY:i%2?.8:-.8},e=>({x:e.clientX/scale,y:e.clientY/scale}),{clientWidth:scale,clientHeight:scale});
     lessonAddStrokeSamples(stroke,{type:'pointerup',timeStamp:808,clientX:40.4,clientY:0},e=>({x:e.clientX/scale,y:e.clientY/scale}),{clientWidth:scale,clientHeight:scale});
     return stroke.points.map(p=>({x:p.x*scale,y:p.y*scale}));
    }
    const fast={points:[{x:0,y:0}]};
    for(let i=1;i<=20;i++)lessonAddStrokeSamples(fast,{timeStamp:i*8,clientX:i*20,clientY:0},e=>({x:e.clientX,y:e.clientY}),{clientWidth:1,clientHeight:1});
    return {pen:trace(),zoom:trace(2),marker:trace(1,{opacity:.32}),line:trace(1,{straight:true}),fast:fast.points};
   });
   assert.ok(Math.max(...liveInk.pen.slice(10,-1).map(p=>Math.abs(p.y)))<.4);
   assert.deepEqual(liveInk.pen.at(-1),{x:40.4,y:0});
   assert.deepEqual(liveInk.pen,liveInk.zoom);
   for(let i=0;i<liveInk.pen.length-1;i++)assert.ok(Math.abs(liveInk.pen[i].x-i*.4)<=1.5);
   assert.ok(Math.max(...liveInk.marker.slice(10,-1).map(p=>Math.abs(p.y)))<.3);
   assert.equal(Math.max(...liveInk.line.map(p=>Math.abs(p.y))),.8);
   liveInk.fast.forEach((p,i)=>assert.ok(Math.abs(p.x-i*20)<=1.5));
   const natural=await page.evaluate(()=>{
    const points=[{x:.1,y:.1},{x:.15,y:.14},{x:.2,y:.1},{x:.15,y:.06},{x:.1,y:.1}];
    const curve=lessonStrokePoints({renderVersion:2,opacity:.32,points},600,300);
    const penCurve=lessonStrokePoints({renderVersion:2,opacity:1,points},600,300);
    const legacy=lessonStrokePoints({points},600,300);
    const live={renderVersion:2,opacity:1,points:[{x:0,y:0}]};
    for(let i=1;i<=8;i++)lessonAddStrokeSamples(live,{timeStamp:i*8,clientX:i,clientY:Math.sin(i)},e=>({x:e.clientX,y:e.clientY}),{clientWidth:1,clientHeight:1});
    const before=JSON.stringify(live.points);lessonFinishStroke(live);
    const duplicates=lessonStrokePoints({renderVersion:2,points:[points[0],points[0],points[1],points[2]]},600,300);
    return {points,curve,penCurve,legacy,old:lessonSmoothPoints(points),unchanged:before===JSON.stringify(live.points),duplicates};
   });
   assert.equal(natural.unchanged,false);assert.deepEqual(natural.penCurve,natural.old);assert.deepEqual(natural.legacy,natural.old);
   natural.points.forEach((p,i)=>{assert.ok(Math.hypot(p.x-natural.curve[i*8].x,p.y-natural.curve[i*8].y)<1e-9)});
   assert.ok(natural.duplicates.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
   // Heat guidance appears before conducting a known hot reaction; never for cold/unknown pairs.
   await page.evaluate(()=>{lessonClearActiveTube();lessonSetReagent('a','mno2');lessonSetReagent('b','hcl')});
   assert.ok(await page.locator('#lessonHeatHint').isVisible());
   assert.match(await page.locator('#lessonHeatHint').innerText(),/реакция есть в базе.*нужен нагрев/);
   assert.match(await page.locator('#lessonHeatHint').innerText(),/концентрированная HCl/);
   assert.equal(await page.locator('#lessonHeat').getAttribute('aria-describedby'),'lessonHeatHint');
   assert.equal(await page.evaluate(()=>lessonStarted),false);
   assert.equal(await page.locator('#lessonTube1 .bubbleLayer').count(),0);
   await page.locator('#lessonHeat').click();
   assert.ok(await page.locator('#lessonHeatHint').isHidden());
   await page.evaluate(()=>lessonConductStep());
   assert.equal(await page.locator('#lessonTube1 .bubbleLayer').count(),1);
   for(const pair of [['hcl','naoh'],['cuso4','nacl'],['br2','naoh']]){
    await page.evaluate(([a,b])=>{lessonClearActiveTube();lessonSetReagent('a',a);lessonSetReagent('b',b)},pair);
    assert.ok(await page.locator('#lessonHeatHint').isHidden());
    assert.equal(await page.locator('#lessonHeat').getAttribute('aria-describedby'),null);
   }
   await page.evaluate(()=>lessonClearActiveTube());
   // Oxidising acids: consume Cu(I) oxide, use the correct gas and heat gate.
   for(const [acid,gas,hot] of [['h2so4_conc','SO₂',true],['hno3_conc','NO₂',false],['hno3','NO',false],['h2so4','',false]]){
    await page.evaluate(a=>{lessonClearActiveTube();lessonSetReagent('a','cu2o');lessonSetReagent('b',a)},acid);
    if(hot){
     await page.locator('#lessonConduct').click();
     assert.equal(await page.locator('#lessonTube1 .bubbleLayer').count(),0);
     assert.ok(await page.locator('#lessonHeatHint').isVisible());
     await page.locator('#lessonHeat').click();
    }else await page.locator('#lessonConduct').click();
    assert.match(await page.locator('#lessonReaction').innerText(),/CuSO₄|Cu\(NO₃\)₂/);
    assert.equal(await page.locator('#lessonTube1 .bubbleLayer').count(),gas?1:0);
    assert.equal(await page.locator('#lessonTube1 .solidBed.dissolving-solid').count(),1);
    assert.equal(await page.locator('#lessonTube1 .pptLayer').count(),gas?0:1);
    if(gas==='NO₂')assert.equal(await page.locator('#lessonTube1 .gasPlume.no2').count(),1);
   }
   // Classroom feedback: direct acid reagent, real manganate(VI) media and visible chlorine.
   await page.evaluate(()=>{lessonClearActiveTube();lessonSetReagent('a','kmno4');lessonSetReagent('b','hcl')});
   assert.ok(await page.locator('#lessonMediumField').isHidden());
   await page.locator('#lessonConduct').click();
   assert.match(await page.locator('#lessonReaction').innerText(),/5Cl₂/);
   assert.equal(await page.locator('#lessonTube1 .gasPlume.cl2').count(),1);
   const gasStyle=await page.locator('#lessonTube1 .gasPlume.cl2').evaluate(e=>({name:getComputedStyle(e).animationName,color:e.style.getPropertyValue('--gasColor')}));
   assert.equal(gasStyle.name,'chlorinePlume');assert.match(gasStyle.color,/166,191,40/);
   for(const medium of ['acid','neutral','alkaline','weak_alkaline']){
    await page.evaluate(m=>{lessonClearActiveTube();lessonSetReagent('a','k2mno4');lessonSetReagent('b','k2so3');document.getElementById('lessonMedium').value=m;lessonConductStep()},medium);
    assert.ok(await page.locator('#lessonMediumField').isVisible());
    assert.match(await page.locator('#lessonReaction').innerText(),medium==='acid'?/MnSO₄/:/MnO₂/);
    assert.equal(await page.locator('#lessonTube1 .pptLayer').count(),medium==='acid'?0:1);
    assert.equal(await page.locator('#lessonTube1 .bubbleLayer').count(),0);
    const free=await page.evaluate(m=>{tubes[3]=['k2so3','k2mno4'];tubeMedium[3]=m;return tubeReaction(3)},medium);
    assert.ok(free);assert.match(free.sign,/Зелёная/);
   }
   await page.evaluate(()=>{lessonClearActiveTube();lessonSetReagent('a','k2mno4');lessonSetReagent('b','hcl')});
   assert.ok(await page.locator('#lessonMediumField').isHidden());
   assert.equal(await page.locator('#lessonPDFNavigation').count(),0);
   await page.evaluate(()=>{lessonClearActiveTube();tubes[3]=[];tubeMedium[3]=''});
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
   assert.equal(pouring.first.level,36);assert.equal(pouring.first.from,0);
   assert.equal(pouring.resumed.pourAge,.4);assert.equal(pouring.next.level,54);assert.equal(pouring.next.from,36);
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
   // Lesson workbenches retain actual nodes and running animations across unrelated actions.
   await page.evaluate(()=>{
    lessonClearActiveTube();lessonSetReagent('a','cuso4');lessonSetReagent('b','naoh');lessonConductStep();
    window.lessonTubeRef=document.querySelector('#lessonTube1 .tube');window.lessonPptRef=window.lessonTubeRef.querySelector('.pptLayer');
    window.lessonMutations=0;window.lessonObserver=new MutationObserver(records=>window.lessonMutations+=records.length);window.lessonObserver.observe(document.getElementById('lessonTube1'),{childList:true,subtree:true});
    window.originalAnimation=window.lessonPptRef.getAnimations({subtree:true})[0];
    lessonSelectTube(1);lessonClearActiveTube();lessonSetReagent('a','fecl3');lessonSetReagent('b','naoh');lessonConductStep();
    lessonHeated=true;lessonRenderExperiment();lessonSelectTube(0);
   });
   assert.ok(await page.evaluate(()=>document.querySelector('#lessonTube1 .tube')===window.lessonTubeRef&&window.lessonTubeRef.querySelector('.pptLayer')===window.lessonPptRef));
   assert.equal(await page.evaluate(()=>window.lessonMutations),0);
   assert.ok(await page.evaluate(()=>window.lessonPptRef.getAnimations({subtree:true}).includes(window.originalAnimation)));
   await page.evaluate(()=>window.lessonObserver.disconnect());
   // MnO2 is available by ordinary name and acts as oxidizer with both halide acids.
   assert.ok(await page.evaluate(()=>lessonSearchMatches('оксид марганца 4').some(([id])=>id==='mno2')));
   for(const acid of ['hcl','hbr']){
    await page.evaluate(value=>{lessonClearActiveTube();lessonSetReagent('a','mno2');lessonSetReagent('b',value);lessonConductStep()},acid);
    assert.match(await page.locator('#lessonReaction').innerText(),/Окислитель:.*MnO₂/);
    if(acid==='hcl'){
     assert.equal(await page.locator('#lessonTube1 .dissolving-solid').count(),0);
     assert.equal(await page.locator('#lessonTube1 .bubbleLayer').count(),0);
     await page.locator('#lessonHeat').click();
     assert.equal(await page.locator('#lessonTube1 .bubbleLayer').count(),1);
     assert.match(await page.locator('#lessonReaction').innerText(),/концентрированная HCl/);
    }else{
     assert.equal(await page.locator('#lessonTube1 .bubbleLayer').count(),0);
     assert.equal(await page.locator('#lessonTube1 .liq').evaluate(e=>e.style.background),'rgb(164, 104, 54)');
    }
    assert.equal(await page.locator('#lessonTube1 .dissolving-solid').count(),1);
    await page.locator('#lessonReaction .reaction-redox summary').click();
    assert.match(await page.locator('#lessonReaction').innerText(),/2e⁻/);
   }
   // A chromate-producing reaction retains the poured solution volume.
   await page.evaluate(()=>{lessonClearActiveTube();lessonSetReagent('a','croh3');lessonSetReagent('b','h2o2');document.getElementById('lessonMedium').value='alkaline';lessonHeated=true;lessonConductStep()});
   assert.match(await page.locator('#lessonReaction').innerText(),/Na₂CrO₄/);
   const chromateLevel=await page.locator('#lessonTube1 .liq').evaluate(e=>parseFloat(e.style.height));
   assert.ok(chromateLevel>=36);
   await page.evaluate(()=>lessonSelectTube(1));await page.evaluate(()=>lessonSelectTube(0));
   assert.equal(await page.locator('#lessonTube1 .liq').evaluate(e=>parseFloat(e.style.height)),chromateLevel);
   // Solution must occupy the actual rendered tube, including after proportional resizing.
   await page.waitForTimeout(600);
   const fillRatio=await page.locator('#lessonTube1 .liq').evaluate(e=>e.getBoundingClientRect().height/e.parentElement.clientHeight);
   assert.ok(fillRatio>=.35, 'Chromate solution must remain visibly filled');
   const oxideChromateLevel=await page.evaluate(()=>tubeMotionFor({},['cr2o3','cl2'],{eq:'Cr₂O₃ + 3Cl₂ + 10NaOH → 2Na₂CrO₄ + 6NaCl + 5H₂O',c:'Щелочная среда',sol:'#ffff00'}).level);
   assert.ok(oxideChromateLevel>=36);
   // Resize panel with keyboard.
   await page.locator('#lessonPanelDivider').focus();await page.keyboard.press('ArrowRight');
   assert.equal(await page.locator('#lessonPanelDivider').getAttribute('aria-valuenow'),'35');
   // PDF stays separate from board; annotate before switching.
   const pdf=await PDFDocument.create();pdf.addPage([600,400]);pdf.addPage([600,400]);
   const buffer=Buffer.from(await pdf.save());
   await page.locator('#lessonPDFInput').setInputFiles({name:'lesson-'+size.width+'.pdf',mimeType:'application/pdf',buffer});
   await page.waitForFunction(()=>lessonPageCount===2&&lessonPdfDocument!==null);
   await page.locator('#lessonNext').click();await page.waitForFunction(()=>lessonPage===2);
   await page.locator('#lessonPrevious').click();await page.waitForFunction(()=>lessonPage===1);
   // Presentation expands independently and always provides an exit.
   const labBeforeFull=await page.evaluate(()=>JSON.stringify(lessonTubeStates));
   assert.ok(await page.locator('#lessonPresentationFullscreen').evaluate(e=>e.clientWidth>=32&&e.scrollWidth<=e.clientWidth));
   await page.locator('#lessonPresentationFullscreen').click();
   assert.ok(await page.locator('.lesson-studio').evaluate(e=>e.classList.contains('presentation-fullscreen')));
   assert.ok(await page.locator('.lesson-lab-pane').isHidden());
   assert.ok(await page.locator('#lessonPresentationExit').isVisible());
   const fullBox=await page.locator('.lesson-pdf-pane').boundingBox();assert.ok(fullBox.width>=size.width-2);
   await page.locator('#lessonNext').click();await page.waitForFunction(()=>lessonPage===2);
   await page.locator('#lessonPrevious').click();await page.waitForFunction(()=>lessonPage===1);
   await page.locator('#lessonToolbarToggle').click();
   assert.ok(await page.locator('#lessonPresentationExit').isVisible());
   await page.locator('#lessonPresentationExit').click();
   assert.ok(await page.locator('.lesson-lab-pane').isVisible());
   await page.locator('#lessonToolbarToggle').click();
   await page.locator('#lessonPresentationFullscreen').click();await page.keyboard.press('Escape');
   assert.ok(await page.locator('#lessonPresentationExit').isHidden());
   assert.equal(await page.evaluate(()=>JSON.stringify(lessonTubeStates)),labBeforeFull);
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
   const markerPDF=await page.evaluate(async()=>{
    const savedNotes=lessonNotes,originalDownload=lessonDownload;let bytes;
    try{
     lessonNotes={'1':[{renderVersion:2,color:'#ff0000',width:18,opacity:.32,points:[{x:.1,y:.5},{x:.2,y:.5},{x:.3,y:.5},{x:.4,y:.5}]}]};
     let downloads=0;lessonDownload=value=>{bytes=value;downloads++;};
     const pending=lessonExportPDF();
     const feedback={disabled:document.getElementById('lessonExport').disabled,label:document.querySelector('#lessonExport span').textContent};
     await lessonExportPDF();await pending;
     const cacheCount=lessonPdfExportCache.pages.size;
     const realGetPage=lessonPdfDocument.getPage.bind(lessonPdfDocument);let renderedAgain=0;
     lessonPdfDocument.getPage=(...args)=>{renderedAgain++;return realGetPage(...args)};
     try{await lessonExportPDF();}finally{lessonPdfDocument.getPage=realGetPage;}
     if(!feedback.disabled||!feedback.label.includes('Сохраняю')||downloads!==2||cacheCount!==2||renderedAgain!==0)throw Error('export feedback/cache regression');
     const reader=await import('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs');
     const doc=await reader.getDocument({data:new Uint8Array(bytes),isEvalSupported:false}).promise;
     const sheet=await doc.getPage(1),viewport=sheet.getViewport({scale:1});
     const canvas=document.createElement('canvas');canvas.width=viewport.width;canvas.height=viewport.height;
     const context=canvas.getContext('2d');await sheet.render({canvasContext:context,viewport}).promise;
     const samples=[90,120,150,180,210].map(x=>Array.from(context.getImageData(x,200,1,1).data));
     await doc.destroy();return samples;
    }finally{lessonDownload=originalDownload;lessonNotes=savedNotes;lessonRedrawInk();}
   });
   markerPDF.forEach(pixel=>{assert.equal(pixel[0],255);assert.ok(Math.abs(pixel[1]-173)<3,JSON.stringify(markerPDF));assert.ok(Math.abs(pixel[2]-173)<3)});
   assert.equal(await page.locator('#lessonPresentationTab').innerText(),'Презентация');
   await page.locator('#lessonPresentationTab').click();
   assert.equal(await page.evaluate(()=>lessonBoardMode),false);
   await page.locator('#lessonBoardToggle').click();
   await page.locator('#lessonBoardToggle').click();
   assert.equal(await page.evaluate(()=>lessonBoardMode),true);
   assert.equal(await page.locator('#lessonPresentationTab').getAttribute('aria-pressed'),'false');
   await page.locator('#lessonBoardLine').click();
   assert.equal(await page.locator('#lessonBoardLine').getAttribute('aria-pressed'),'true');
   await page.locator('#lessonBoardMarker').click();
   assert.equal(await page.evaluate(()=>lessonLineMode),false);
   assert.equal(await page.locator('#lessonBoardLine').getAttribute('aria-pressed'),'false');
   await page.locator('#lessonBoardPan').click();await page.locator('#lessonBoardPen').click();
   assert.equal(await page.evaluate(()=>lessonBoardTool),'pen');
   assert.equal(await page.locator('#lessonBoardPan').getAttribute('aria-pressed'),'false');
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
   download=page.waitForEvent('download');await page.locator('#lessonBoardMore summary').click();await page.locator('#lessonBoardExport').click();await page.locator('#lessonBoardMore').evaluate(e=>e.open=false);
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
   await page.locator('#lessonPresentationTab').scrollIntoViewIfNeeded();
   await page.screenshot({path:'lab-visual-preview/review-presentation-'+size.width+'.png'});
   // Persist a complete multi-page scene, reload the tab and explicitly restore.
   await page.waitForFunction(()=>lessonBoardRecoveryDB!==null);
   await page.waitForFunction(()=>!lessonBoardRecoveryBusy);
   await page.evaluate(async()=>{lessonBoardRecoveryDirty=true;await lessonBoardFlushRecovery();});
   await page.waitForFunction(()=>!lessonBoardRecoveryBusy);
   const recoveryBefore=await page.evaluate(()=>lessonBoardSerializeProject());
   assert.match(await page.locator('#lessonBoardSaveState').innerText(),/сохранена/);
   await page.reload();await page.waitForFunction(()=>lessonReady);
   await page.locator('[data-page="lesson"]').click();
   await page.locator('#lessonBoardRecover').waitFor({state:'visible'});
   page.once('dialog',dialog=>dialog.accept());await page.locator('#lessonBoardRecover').click();
   await page.waitForFunction(()=>!lessonBoardRecoveryPending);
   assert.deepEqual(JSON.parse(await page.evaluate(()=>lessonBoardSerializeProject())),JSON.parse(recoveryBefore));
   // A quota/storage failure is visible and does not report success.
   await page.waitForFunction(()=>!lessonBoardRecoveryBusy);
   const recoveryFailure=await page.evaluate(async()=>{
    const db=lessonBoardRecoveryDB;lessonBoardRecoveryDB={transaction(){throw Error('quota')}};
    try{lessonBoardView.x+=1;lessonBoardRecoveryDirty=true;await lessonBoardFlushRecovery();return document.getElementById('lessonBoardSaveState').textContent;}
    finally{lessonBoardRecoveryDB=db;}
   });
   assert.match(recoveryFailure,/не сохранена/);
   // Another tab's revision cannot be silently overwritten.
   const conflict=await page.evaluate(async()=>{
    await new Promise((resolve,reject)=>{const tx=lessonBoardRecoveryDB.transaction('boards','readwrite'),store=tx.objectStore('boards');
     const req=store.get(lessonBoardRecoveryKey());req.onsuccess=()=>store.put({...req.result,revision:req.result.revision+1},lessonBoardRecoveryKey());tx.oncomplete=resolve;tx.onerror=reject;});
    lessonBoardRecoveryDirty=true;await lessonBoardFlushRecovery();return document.getElementById('lessonBoardSaveState').textContent;
   });
   assert.match(conflict,/другой вкладке/);
   // The comparison screen is isolated from lesson ink, board and selected tools.
   const lessonBeforeBench=await page.evaluate(()=>JSON.stringify({notes:lessonNotes,board:lessonBoardSerializeProject(),tool:lessonTool,pen:lessonPenColorValue,marker:lessonMarkerColorValue}));
   await page.locator('#penCompareOpen').click();await page.locator('#penCompare').waitFor({state:'visible'});
   const benchBox=await page.locator('#penCompareCanvas').boundingBox(),benchPen=await page.context().newCDPSession(page);
   await page.evaluate(()=>document.getElementById('penCompareCanvas').addEventListener('pointerdown',e=>window.benchPointerId=e.pointerId,{once:true}));
   await benchPen.send('Input.dispatchMouseEvent',{type:'mousePressed',x:benchBox.x+30,y:benchBox.y+70,button:'left',buttons:1,pointerType:'pen',force:.2});
   // Replay Safari's duplicated coalesced/parent sample without private user ink.
   await page.evaluate(()=>{
    const c=document.getElementById('penCompareCanvas'),r=c.getBoundingClientRect();
    const e=new PointerEvent('pointermove',{pointerId:window.benchPointerId,pointerType:'pen',clientX:r.left+35,clientY:r.top+72,buttons:1,pressure:.25,bubbles:true});
    Object.defineProperty(e,'getCoalescedEvents',{value:()=>[e]});c.dispatchEvent(e);
   });
   for(let i=1;i<=20;i++)await benchPen.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:benchBox.x+30+i*9,y:benchBox.y+70+Math.sin(i/3)*15,button:'left',buttons:1,pointerType:'pen',force:.2+i/50});
   await benchPen.send('Input.dispatchMouseEvent',{type:'mouseReleased',x:benchBox.x+215,y:benchBox.y+75,button:'left',buttons:0,pointerType:'pen',force:0});
   await benchPen.detach();
   await page.waitForFunction(()=>document.getElementById('penCompare').dataset.strokeCount==='1'&&document.getElementById('penCompare').dataset.pressureSource==='pen');
   const firstBenchDownload=page.waitForEvent('download');await page.locator('#penCompareExport').click();
   const benchRaw=JSON.parse(fs.readFileSync(await (await firstBenchDownload).path(),'utf8'));
   const currentBenchImage=await page.locator('#penCompareCanvas').evaluate(c=>c.toDataURL());
   await page.locator('[data-pc-profile="smooth"]').click();await page.waitForTimeout(40);
   const smoothBenchImage=await page.locator('#penCompareCanvas').evaluate(c=>c.toDataURL());assert.notEqual(smoothBenchImage,currentBenchImage);
   await page.locator('[data-pc-profile="natural"]').click();await page.locator('#penCompareChoose').click();
   await page.locator('#penCompareSideBySide').click();assert.ok(await page.locator('#penComparePreviews').isVisible());
   await page.waitForTimeout(40);assert.equal(await page.locator('#penComparePreviews canvas').count(),3);
   const lastBenchDownload=page.waitForEvent('download');await page.locator('#penCompareExport').click();
   const benchNatural=JSON.parse(fs.readFileSync(await (await lastBenchDownload).path(),'utf8'));
   assert.equal(benchNatural.engine.version,'1.2.3');assert.equal(benchNatural.preferred,'natural');
   assert.deepEqual(benchRaw.strokes,benchNatural.strokes);assert.ok(benchNatural.diagnostics.pressure.distinctValues>5);
   assert.ok(benchNatural.diagnostics.duplicatesRemoved>=1);
   const rawBenchPoints=benchNatural.strokes[0].raw;
   for(let i=1;i<rawBenchPoints.length;i++)assert.ok(['x','y','t','pressure'].some(k=>rawBenchPoints[i][k]!==rawBenchPoints[i-1][k]));
   assert.ok(benchNatural.strokes[0].raw.some(p=>p.pressure>.2&&p.pressure<.6));
   assert.equal(benchNatural.strokes[0].pointerType,'pen');assert.equal('notes' in benchNatural,false);
   await page.locator('#penCompareClose').click();assert.ok(await page.locator('#penCompare').isHidden());
   assert.equal(await page.evaluate(()=>JSON.stringify({notes:lessonNotes,board:lessonBoardSerializeProject(),tool:lessonTool,pen:lessonPenColorValue,marker:lessonMarkerColorValue})),lessonBeforeBench);
   await page.locator('#penCompareOpen').click();assert.equal(await page.locator('#penCompare').getAttribute('data-stroke-count'),'1');
   await page.locator('#penCompareUndo').click();await page.waitForFunction(()=>document.getElementById('penCompare').dataset.strokeCount==='0');
   // Ordinary mouse input remains usable, with explicit simulated-pressure fallback.
   const mouseBench=await page.locator('#penCompareCanvas').boundingBox();
   await page.mouse.move(mouseBench.x+20,mouseBench.y+40);await page.mouse.down();await page.mouse.move(mouseBench.x+130,mouseBench.y+65,{steps:12});await page.mouse.up();
   await page.waitForFunction(()=>document.getElementById('penCompare').dataset.strokeCount==='1'&&document.getElementById('penCompare').dataset.pressureSource==='simulated');
   await page.locator('#penCompareClear').click();await page.waitForFunction(()=>document.getElementById('penCompare').dataset.strokeCount==='0');
   await page.keyboard.press('Escape');assert.ok(await page.locator('#penCompare').isHidden());
   assert.deepEqual(errors,[]);
   console.log('REVIEW_BROWSER_OK' ,size.width,size.height,'chemistry, tubes, PDF, world coordinates, zoom, projects v1/v2, eraser, undo, export, fullscreen');
   await page.close();
  }
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
