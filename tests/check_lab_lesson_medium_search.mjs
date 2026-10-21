// Offline smoke test of the real 30/70 PDF + chemistry lesson.
import assert from "node:assert/strict";
import {pathToFileURL} from "node:url";
import {resolve} from "node:path";
import {chromium} from "playwright";

const pageUrl=pathToFileURL(resolve("preview/ege-blizko-lab-lesson-30-70-offline.html")).href;
const browser=await chromium.launch({headless:true});
try{
  for(const width of [920,1440]){
    const page=await browser.newPage({viewport:{width,height:880}});
    const errors=[];
    page.on("pageerror",error=>errors.push(error.message));
    await page.goto(pageUrl);
    await page.waitForFunction(()=>document.querySelector("#lessonReagentA")?.value==="KMnO₄");
    assert.equal(await page.locator(".lesson-studio").isVisible(),true);

    // Search accepts ASCII indices and compound names (not just a huge select).
    await page.locator("#lessonReagentA").fill("KMnO4");
    await page.locator("#lessonSuggestionsA button").first().waitFor();
    await page.locator("#lessonSuggestionsA button").first().click();
    assert.equal(await page.locator("#lessonReagentA").inputValue(),"KMnO₄");
    assert.equal(await page.locator("#lessonMediumField").isVisible(),true);

    await page.locator("#lessonReagentB").fill("сульфит натрия");
    await page.locator("#lessonSuggestionsB button").first().waitFor();
    await page.locator("#lessonSuggestionsB button").first().click();
    assert.equal(await page.locator("#lessonReagentB").inputValue(),"Na₂SO₃");

    // No hidden default medium is allowed.
    assert.equal(await page.locator("#lessonMedium").inputValue(),"");
    await page.locator("#lessonConduct").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/Выбери среду/);

    for(const [medium,formula,color] of [
      ["acid","MnSO₄","исчезает|обесцвеч"],
      ["neutral","MnO₂","бур"],
      ["alkaline","K₂MnO₄","зелён"]
    ]){
      await page.locator("#lessonMedium").selectOption(medium);
      await page.locator("#lessonConduct").click();
      const rendered=await page.locator("#lessonReaction").innerText();
      assert(rendered.includes(formula),medium+": missing product "+formula);
      assert(new RegExp(color,"i").test(rendered),medium+": wrong sign");
      assert.equal(await page.locator("#lessonTube .tube").count(),1);
    }

    // A second reductant exercises oxygen + precipitate combinations.
    await page.locator("#lessonReagentB").fill("H2O2");
    await page.locator("#lessonSuggestionsB button").first().click();
    assert.equal(await page.locator("#lessonReagentB").inputValue(),"H₂O₂");
    await page.locator("#lessonMedium").selectOption("neutral");
    await page.locator("#lessonConduct").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/MnO₂/);
    assert.match(await page.locator("#lessonReaction").innerText(),/O₂/);

    // An unsupported pair must not silently borrow another medium's products.
    await page.locator("#lessonReagentB").fill("KOH");
    await page.locator("#lessonSuggestionsB button").first().click();
    await page.locator("#lessonMedium").selectOption("acid");
    await page.locator("#lessonConduct").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/нет проверенной реакции/);

    // A regular reaction does not need the permanganate medium control.
    await page.locator("#lessonReagentA").fill("CuSO4");
    await page.locator("#lessonSuggestionsA button").first().click();
    await page.locator("#lessonReagentB").fill("NaOH");
    await page.locator("#lessonSuggestionsB button").first().click();
    assert.equal(await page.locator("#lessonMediumField").isVisible(),false);
    await page.locator("#lessonConduct").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/Cu\(OH\)₂/);

    // Chromium(VI) requires acidic conditions for the documented redox case.
    await page.locator("#lessonReagentA").fill("K2Cr2O7");
    await page.locator("#lessonSuggestionsA button").first().click();
    assert.equal(await page.locator("#lessonReagentA").inputValue(),"K₂Cr₂O₇");
    await page.locator("#lessonReagentB").fill("FeSO4");
    await page.locator("#lessonSuggestionsB button").first().click();
    assert.equal(await page.locator("#lessonMediumField").isVisible(),true);
    await page.locator("#lessonMedium").selectOption("acid");
    await page.locator("#lessonConduct").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/Cr₂\(SO₄\)₃/);
    assert.match(await page.locator("#lessonReaction").innerText(),/зелён/);

    // Chromate precipitation is ordinary exchange and needs no redox-medium menu.
    await page.locator("#lessonReagentA").fill("K2CrO4");
    await page.locator("#lessonSuggestionsA button").first().click();
    await page.locator("#lessonReagentB").fill("Pb(NO3)2");
    await page.locator("#lessonSuggestionsB button").first().click();
    assert.equal(await page.locator("#lessonMediumField").isVisible(),false);
    await page.locator("#lessonConduct").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/PbCrO₄/);
    assert.match(await page.locator("#lessonReaction").innerText(),/жёлт/i);

    // Batch 2: verify peroxide redox with dichromate and visible gas.
    await page.locator("#lessonReagentA").fill("K2Cr2O7");
    await page.locator("#lessonSuggestionsA button").first().click();
    await page.locator("#lessonReagentB").fill("H2O2");
    await page.locator("#lessonSuggestionsB button").first().click();
    assert.equal(await page.locator("#lessonMediumField").isVisible(),true);
    await page.locator("#lessonMedium").selectOption("acid");
    await page.locator("#lessonConduct").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/Cr₂\(SO₄\)₃/);
    assert.match(await page.locator("#lessonReaction").innerText(),/O₂/);

    // Batch 2: combined hydrolysis must show both precipitate and gas.
    await page.locator("#lessonReagentA").fill("AlCl3");
    await page.locator("#lessonSuggestionsA button").first().click();
    await page.locator("#lessonReagentB").fill("Na2CO3");
    await page.locator("#lessonSuggestionsB button").first().click();
    assert.equal(await page.locator("#lessonMediumField").isVisible(),false);
    await page.locator("#lessonConduct").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/Al\(OH\)₃/);
    assert.match(await page.locator("#lessonReaction").innerText(),/CO₂/);

    // Batch 3: Cr(III) hydroxo complex, oxidation to Cr(VI) only with alkali + heat.
    await page.locator("#lessonReagentA").fill("Cr(OH)3");
    await page.locator("#lessonSuggestionsA button").first().click();
    await page.locator("#lessonReagentB").fill("H2O2");
    await page.locator("#lessonSuggestionsB button").first().click();
    assert.equal(await page.locator("#lessonMediumField").isVisible(),true);
    assert((await page.locator("#lessonMediumField label").innerText()).includes("Cr(III)"));
    await page.locator("#lessonMedium").selectOption("alkaline");
    await page.locator("#lessonConduct").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/Нужен нагрев/);
    await page.locator("#lessonHeat").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/Na₂CrO₄/);
    assert.match(await page.locator("#lessonReaction").innerText(),/жёлт/i);

    // Batch 3: no reaction != unrecorded reaction.
    await page.locator("#lessonReagentA").fill("Br2");
    await page.locator("#lessonSuggestionsA button").first().click();
    await page.locator("#lessonReagentB").fill("KCl");
    await page.locator("#lessonSuggestionsB button").first().click();
    await page.locator("#lessonConduct").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/Реакция не идёт/);

    // New Cr(III) reagent is searchable and produces an amphoteric hydroxide.
    await page.locator("#lessonReagentA").fill("CrCl3");
    await page.locator("#lessonSuggestionsA button").first().click();
    await page.locator("#lessonReagentB").fill("NaOH");
    await page.locator("#lessonSuggestionsB button").first().click();
    assert.equal(await page.locator("#lessonMediumField").isVisible(),false);
    await page.locator("#lessonConduct").click();
    assert((await page.locator("#lessonReaction").innerText()).includes("Cr(OH)₃"));

    // Source PDF 32: neutral permanganate plus H2S forms two coloured solids.
    await page.locator("#lessonReagentA").fill("KMnO4");
    await page.locator("#lessonSuggestionsA button").first().click();
    await page.locator("#lessonReagentB").fill("H2S");
    await page.locator("#lessonSuggestionsB button").first().click();
    await page.locator("#lessonMedium").selectOption("neutral");
    await page.locator("#lessonConduct").click();
    const dualSolid=await page.locator("#lessonReaction").innerText();
    assert(dualSolid.includes("MnO₂") && dualSolid.includes("S↓"));
    assert.equal(await page.locator("#lessonTube .mixed-precipitates .particle").count(),64);
    const mixedColors=await page.locator("#lessonTube .mixed-precipitates .particle")
      .evaluateAll(nodes=>new Set(nodes.map(x=>x.style.getPropertyValue("--pc"))).size);
    assert.equal(mixedColors,2);


    // Source PDF 33: weakly alkaline chromium complex is a separate result.
    await page.locator("#lessonReagentA").fill("K2Cr2O7");
    await page.locator("#lessonSuggestionsA button").first().click();
    await page.locator("#lessonReagentB").fill("K2SO3");
    await page.locator("#lessonSuggestionsB button").first().click();
    await page.locator("#lessonMedium").selectOption("weak_alkaline");
    await page.locator("#lessonConduct").click();
    assert((await page.locator("#lessonReaction").innerText()).includes("K[Cr(OH)₄]"));

    // Examples held for chemical review must not be shown as verified.
    await page.locator("#lessonReagentA").fill("KMnO4");
    await page.locator("#lessonSuggestionsA button").first().click();
    await page.locator("#lessonReagentB").fill("KBr");
    await page.locator("#lessonSuggestionsB button").first().click();
    await page.locator("#lessonMedium").selectOption("alkaline");
    await page.locator("#lessonConduct").click();
    assert.match(await page.locator("#lessonReaction").innerText(),/нет проверенной реакции/);

    // Existing PDF-stylus functionality remains on the same screen.
    for(const selector of ["#lessonPDFInput","#lessonInkCanvas","#lessonExport","#lessonToolPen"]){
      assert.equal(await page.locator(selector).count(),1,selector+" missing");
    }
    assert.deepEqual(errors,[],width+"px JS errors");
    console.log("LESSON_MEDIUM_SEARCH_OK",width,"px");
    await page.close();
  }
}finally{
  await browser.close();
}
