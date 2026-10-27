const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '..', 'ege_november_theme.js'), 'utf8');
const boundary = Date.parse('2026-10-31T21:00:00Z');

function page(role, initial) {
 let clock = initial, nextId = 1, banners = 0, observations = 0;
 const attributes = {}, classes = new Set(), timers = new Map();
 const documentEvents = new Map(), windowEvents = new Map();
 const top = {nextElementSibling: null, insertAdjacentElement(position, element) {
  assert.equal(position, 'afterend'); banners++;
  this.nextElementSibling = {classList:{contains(name){return element.className===name;}}};
 }};
 const document = {
  currentScript:{getAttribute(){return role;}},
  body:{getAttribute(name){return attributes[name];},setAttribute(name,value){attributes[name]=value;},classList:{add(name){classes.add(name);}}},
  getElementById(){return {querySelector(){return top;}};},
  createElement(){return {setAttribute(){},className:'',innerHTML:''};},
  addEventListener(name,fn){documentEvents.set(name,fn);},
  removeEventListener(name){documentEvents.delete(name);}
 };
 class Clock extends Date {static now(){return clock;}}
 const window = {
  setTimeout(fn,delay){const id=nextId++;timers.set(id,{fn,delay});return id;},
  clearTimeout(id){timers.delete(id);},
  addEventListener(name,fn){windowEvents.set(name,fn);},
  removeEventListener(name){windowEvents.delete(name);}
 };
 const context = vm.createContext({Date:Clock,document,window,
  MutationObserver:class {observe(){observations++;}disconnect(){}},
  requestAnimationFrame(fn){fn();}
 });
 vm.runInContext(code,context);
 return {classes,timers,documentEvents,windowEvents,context,
  setClock(value){clock=value;},get banners(){return banners;},get observations(){return observations;},
  tick(){const entry=timers.entries().next().value;assert.ok(entry);timers.delete(entry[0]);entry[1].fn();}
 };
}

for (const role of ['teacher','student']) {
 const p = page(role,boundary-1);
 assert.equal(p.classes.size,0,'Current theme must remain active through October 31');
 assert.equal(p.banners,0);
 assert.equal(p.observations,0,'No decorative observer before November');
 assert.equal([...p.timers.values()][0].delay,1);
 p.setClock(boundary);p.tick();
 assert.ok(p.classes.has('ege-november'));
 assert.equal(p.banners,1);
 assert.equal(p.timers.size,0);
 vm.runInContext(code,p.context);
 assert.equal(p.banners,1,'Repeated execution must not duplicate the banner');
 assert.equal(page(role,boundary+1000).banners,1,'Fresh November page activates immediately');
 const resumed=page(role,boundary-86400000);
 assert.equal([...resumed.timers.values()][0].delay,60000);
 resumed.setClock(boundary+300000);
 resumed.documentEvents.get('visibilitychange')();
 assert.equal(resumed.banners,1,'Resuming a background tab activates the theme');
 const restored=page(role,boundary-1000);
 restored.setClock(boundary+1000);restored.windowEvents.get('pageshow')();
 assert.equal(restored.banners,1,'Restored page activates without refreshing data');
 const adjusted=page(role,boundary-1);
 adjusted.setClock(boundary-120000);adjusted.tick();
 assert.equal(adjusted.banners,0,'Backward clock adjustment must not activate early');
 assert.equal([...adjusted.timers.values()][0].delay,60000);
}
assert.equal(page('unknown',boundary+1).timers.size,0);
console.log('NOVEMBER_CLOCK_OK: both roles, Moscow boundary, resume, repeat, clock adjustment');
