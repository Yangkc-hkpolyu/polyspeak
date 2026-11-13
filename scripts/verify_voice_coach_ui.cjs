// Run against an isolated test server with synthetic ASR; never use real learner data.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { chromium } = require('../frontend/node_modules/playwright');
const assertEnglishUI = require('./assert_english_ui.cjs');
const origin = 'http://127.0.0.1:8009';
const realModel = process.argv.includes('--real-model');
const folder = path.join(__dirname, '../speaking-runtime/qa');
function wav() {
  const pcm = Buffer.alloc(16000 * 3 * 2);
  for (let i = 0; i < 48000; i++) {
    const t = i / 16000;
    const active = t >= .5 && t < 1 || t >= 1.8 && t < 2.5;
    pcm.writeInt16LE(active ? Math.round(Math.sin(i * 2 * Math.PI * 220 / 16000) * 6000) : 0, i * 2);
  }
  const h = Buffer.alloc(44);
  h.write('RIFF'); h.writeUInt32LE(36 + pcm.length, 4); h.write('WAVEfmt ', 8);
  h.writeUInt32LE(16,16); h.writeUInt16LE(1,20); h.writeUInt16LE(1,22);
  h.writeUInt32LE(16000,24); h.writeUInt32LE(32000,28); h.writeUInt16LE(2,32); h.writeUInt16LE(16,34);
  h.write('data',36); h.writeUInt32LE(pcm.length,40);
  return Buffer.concat([h,pcm]);
}
(async () => {
  const browser = await chromium.launch({headless: true, channel: 'msedge'});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [];
    let modelRequests = 0;
    page.on('request', request => { if(request.url().endsWith('/voice-coach')) modelRequests++; });
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/speaking/live/offer', route => route.fulfill({status:503, contentType:'application/json', body:JSON.stringify({detail:'Voice review QA: avatar disabled.'})}));
    let response = await page.request.post(origin + '/api/speaking/sessions', {data:{exam:'ielts',set_id:'ielts-learning',mode:'coach',section:'part1',execution:'demo'}});
    assert(response.ok()); let session = await response.json();
    const base = origin + '/api/speaking/sessions/' + session.id;
    response = await page.request.post(base + '/capture', {multipart:{question_id:session.pending_question_id,audio:{name:'synthetic.wav',mimeType:'audio/wav',buffer:wav()}}});
    assert(response.ok()); const recording = await response.json();
    response = await page.request.post(base + '/answers', {data:{question_id:session.pending_question_id,audio_id:recording.id,answer:recording.text}});
    assert(response.ok()); session = await response.json();
    response = await page.request.post(base + '/finish'); assert(response.ok());
    await page.goto(origin, {waitUntil:'networkidle'});
    await page.getByRole('button',{name:'Practice history',exact:true}).click();
    await page.locator('.history-item').first().click();
    if (!realModel) {
      assert.match(await page.locator('.voice-review.featured').innerText(), /adapter weights are missing/);
      assert.equal(modelRequests, 0);
      assert.deepEqual(errors, []);
      console.log('Unavailable model is shown honestly; no automatic fallback request.');
      return;
    }
    await page.locator('.voice-measurements').waitFor({timeout:150000});
    assert.equal(modelRequests, 1, 'Report must automatically invoke the trained model without a button click');
    assert.match(await page.locator('.voice-review').innerText(), realModel ? /Fine-tuned voice advice/ : /adapter weights are missing/);
    await assertEnglishUI(page, realModel ? 'voice review generated' : 'voice review unavailable');
    const saved = await (await page.request.get(base)).json();
    assert.equal(saved.turns[0].voice_coach.advice.status,realModel ? 'ok' : 'unavailable');
    assert.equal(saved.turns[0].voice_coach.metrics.pause_count,1);
    const exported = await (await page.request.get(base + '/export')).json();
    assert.deepEqual(exported.turns[0].voice_coach, saved.turns[0].voice_coach);
    fs.mkdirSync(folder,{recursive:true});
    await page.locator('.voice-review').screenshot({path:path.join(folder,'voice-coach-desktop.png')});
    if (!process.argv.includes('--desktop-only')) {
      await page.setViewportSize({width:390,height:844});
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.locator('.voice-review').screenshot({path:path.join(folder,'voice-coach-mobile.png')});
    }
    await page.reload({waitUntil:'networkidle'});
    await page.getByRole('button',{name:'Practice history',exact:true}).click();
    await page.locator('.history-item').first().click();
    await page.locator('.voice-measurements').waitFor();
    assert.equal(modelRequests, 1, 'Saved advice must be reused on reload');
    await assertEnglishUI(page, 'saved voice review');
    assert.deepEqual(errors,[]);
    console.log(`Voice review UI, persisted measurements, ${realModel ? 'real adapter inference' : 'unavailable-adapter message'}, export and English passed (${process.argv.includes('--desktop-only') ? 'desktop only' : 'desktop and mobile'}).`);
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
