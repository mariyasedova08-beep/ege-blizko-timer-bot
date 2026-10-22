// Verify medium-aware chemistry on the REAL lab HTML, not the independent preview.
import assert from "node:assert/strict";
import fs from "node:fs";
import {chromium} from "playwright";
const html=fs.readFileSync("/tmp/ege-live-lesson-smoke.html","utf8");
const response=JSON.parse(fs.readFileSync("/tmp/ege-live-lesson-smoke.json","utf8"));
const browser=await chromium.launch({headless:true});
try{
 for(const width of [920,1440]){
  const page=await browser.newPage({viewport:{width,height:890}});
  const errors=[];
  page.on("pageerror",x=>errors.push(x.message));
  await page.addInitScript(()=>{
    window.Telegram={WebApp:{
      ready(){}, expand(){}, initData:"", initDataUnsafe:{},
      colorScheme:"light", platform:"web",
      BackButton:{show(){},hide(){},onClick(){}}
    }};
  });
  await page.route("**/*",async route=>{
    const url=route.request().url();
    if(url.includes("/lab-app/api")){
      const request=route.request().postDataJSON();
      const result=request.action==="event"?{ok:true,stats:response.data.stats}:response;
      return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(result)});
    }
    if(url.includes("/lab-app")){
      return route.fulfill({status:200,contentType:"text/html; charset=utf-8",body:html});
    }
    return route.abort();
  });
  await page.goto("http://lab-local.test/lab-app?page=lesson");
  await page.waitForFunction(()=>document.querySelector("#lessonReagentA")?.value==="KMnO₄");
  // Keyboard input in the real PDF lesson must resolve a catalogue item.
  async function pick(slot,id,query){
    const field=page.locator("#lessonReagent"+slot);
    const original=response.data.reagents[id];
    assert(original,"Missing fixture reagent "+id);
    await field.fill(query??original[0]);
    await page.locator("#lessonSuggestions"+slot+" [role=option]").first().waitFor();
    await field.press("Enter");
    assert.equal(await field.inputValue(),original[0]);
    assert.equal(await page.locator("#lessonSuggestions"+slot).isVisible(),false);
  }
  await pick("A","kmno4","KMnO4");
  await pick("B","na2so3","сульфит натрия");
  await page.locator("#lessonReagentB").fill("ABSENT_DOES_NOT_EXIST");
  assert.match(await page.locator("#lessonSuggestionsB").innerText(),/не найдено/);
  await page.locator("#lessonConduct").click();
  assert.match(await page.locator("#lessonReaction").innerText(),/Выбери оба реактива/);
  await pick("B","na2so3","Na2SO3");
  assert.equal(await page.locator("#lessonMediumField").isVisible(),true);
  assert.equal(await page.locator("#lessonMedium").inputValue(),"");
  await page.locator("#lessonConduct").click();
  assert.match(await page.locator("#lessonReaction").innerText(),/Выбери среду/);
  for(const [medium,product] of [["acid","MnSO₄"],["neutral","MnO₂"],["alkaline","K₂MnO₄"]]){
    await page.locator("#lessonMedium").selectOption(medium);
    await page.locator("#lessonConduct").click();
    assert((await page.locator("#lessonReaction").innerText()).includes(product),medium+": "+product);
  }
  for(const reductant of ["ki","nabr"]){
    await pick("B",reductant);
    await page.locator("#lessonMedium").selectOption("neutral");
    await page.locator("#lessonConduct").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/нет подтверждённой реакции/);
  }
  await pick("A","k2cr2o7");
  await pick("B","k2so3");
  await page.locator("#lessonMedium").selectOption("weak_alkaline");
  await page.locator("#lessonConduct").click();
  assert((await page.locator("#lessonReaction").innerText()).includes("K[Cr(OH)₄]"));
  await pick("A","croh3");
  await pick("B","h2o2");
  await page.locator("#lessonMedium").selectOption("alkaline");
  await page.locator("#lessonConduct").click();
  assert.match(await page.locator("#lessonReaction").innerText(),/Нужен нагрев/);
  await page.locator("#lessonHeat").click();
  assert((await page.locator("#lessonReaction").innerText()).includes("Na₂CrO₄"));
  await pick("A","cuso4");
  await pick("B","naoh");
  assert.equal(await page.locator("#lessonMediumField").isVisible(),false);
  await page.locator("#lessonConduct").click();
  assert((await page.locator("#lessonReaction").innerText()).includes("Cu(OH)₂"));
  // Existing four-tube main laboratory must also use medium-specific registry
  // without exposing unsupported neutral halide oxidation.
  await page.locator('[data-page="free"]').first().click();
  await page.evaluate(()=>{add("kmno4");add("na2so3");});
  assert.equal(await page.locator("#tubeMediumField").isVisible(),true);
  assert.match(await page.locator("#tubes .active-slot .tube-callout").innerText(),/Выбери среду/);
  await page.locator("#tubeMedium").selectOption("acid");
  assert((await page.locator("#tubes .active-slot .tube-callout").innerText()).includes("MnSO₄"));
  await page.locator("#tubeMedium").selectOption("neutral");
  assert((await page.locator("#tubes .active-slot .tube-callout").innerText()).includes("MnO₂"));
  await page.locator("#clear").click();
  await page.evaluate(()=>{add("kmno4");add("ki");});
  await page.locator("#tubeMedium").selectOption("neutral");
  assert.match(await page.locator("#tubes .active-slot .tube-callout").innerText(),/нет подтверждённой реакции/);
  await page.locator("#clear").click();
  await page.evaluate(()=>{add("croh3");add("h2o2");});
  await page.locator("#tubeMedium").selectOption("alkaline");
  assert.match(await page.locator("#tubes .active-slot .tube-callout").innerText(),/Нужен нагрев/);
  await page.locator("#heat").click();
  assert((await page.locator("#tubes .active-slot .tube-callout").innerText()).includes("Na₂CrO₄"));
  await page.locator("#clear").click();
  await page.evaluate(()=>{add("cuso4");add("naoh");});
  assert.equal(await page.locator("#tubeMediumField").isVisible(),false);
  assert((await page.locator("#tubes .active-slot .tube-callout").innerText()).includes("Cu(OH)₂"));

  for(const selector of ["#lessonPDFInput","#lessonInkCanvas","#lessonExport","#lessonToolPen"]){
    assert.equal(await page.locator(selector).count(),1);
  }
  assert.deepEqual(errors,[],width+"px page errors");
  console.log("LIVE_MN_CR_MEDIUM_OK",width);
  await page.close();
 }
}finally{await browser.close()}
