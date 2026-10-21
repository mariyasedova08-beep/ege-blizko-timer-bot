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
      return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(response)});
    }
    if(url.includes("/lab-app")){
      return route.fulfill({status:200,contentType:"text/html; charset=utf-8",body:html});
    }
    return route.abort();
  });
  await page.goto("http://lab-local.test/lab-app?page=lesson");
  await page.waitForFunction(()=>document.querySelector("#lessonReagentA")?.value==="kmno4");
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
    await page.locator("#lessonReagentB").selectOption(reductant);
    await page.locator("#lessonMedium").selectOption("neutral");
    await page.locator("#lessonConduct").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/нет подтверждённой реакции/);
  }
  await page.locator("#lessonReagentA").selectOption("k2cr2o7");
  await page.locator("#lessonReagentB").selectOption("k2so3");
  await page.locator("#lessonMedium").selectOption("weak_alkaline");
  await page.locator("#lessonConduct").click();
  assert((await page.locator("#lessonReaction").innerText()).includes("K[Cr(OH)₄]"));
  await page.locator("#lessonReagentA").selectOption("croh3");
  await page.locator("#lessonReagentB").selectOption("h2o2");
  await page.locator("#lessonMedium").selectOption("alkaline");
  await page.locator("#lessonConduct").click();
  assert.match(await page.locator("#lessonReaction").innerText(),/Нужен нагрев/);
  await page.locator("#lessonHeat").click();
  assert((await page.locator("#lessonReaction").innerText()).includes("Na₂CrO₄"));
  await page.locator("#lessonReagentA").selectOption("cuso4");
  await page.locator("#lessonReagentB").selectOption("naoh");
  assert.equal(await page.locator("#lessonMediumField").isVisible(),false);
  await page.locator("#lessonConduct").click();
  assert((await page.locator("#lessonReaction").innerText()).includes("Cu(OH)₂"));
  for(const selector of ["#lessonPDFInput","#lessonInkCanvas","#lessonExport","#lessonToolPen"]){
    assert.equal(await page.locator(selector).count(),1);
  }
  assert.deepEqual(errors,[],width+"px page errors");
  console.log("LIVE_MN_CR_MEDIUM_OK",width);
  await page.close();
 }
}finally{await browser.close()}
