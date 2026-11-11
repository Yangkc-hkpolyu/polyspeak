// Real local UI + live APIs. Audio is SYNTHETIC, not a real test participant.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('../frontend/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const folder = path.join(root, 'speaking-runtime', 'qa');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:8008';
const noLive = process.env.SPEAKING_UI_ONLY === '1';

(async () => {
  fs.mkdirSync(folder, { recursive: true });
  const fixture = path.join(folder, 'synthetic-input.wav');
  const args = ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'];
  if (!noLive) { assert.ok(fs.existsSync(fixture)); args.push(`--use-file-for-fake-audio-capture=${fixture}`); }
  const browser = await chromium.launch({ headless: true, channel: 'msedge', args });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, permissions: ['microphone'], acceptDownloads: true });
  const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.screenshot({ path: path.join(folder, 'home-desktop.png'), fullPage: true });
  assert.equal(await page.evaluate(() => document.body.scrollWidth), 1440);
  await page.getByRole('button', { name: /题库与资料/ }).click();
  assert.equal(await page.locator('.source-card').count(), 7);
  for (const link of await page.locator('.source-card a.button').evaluateAll(nodes => nodes.map(x => x.href))) {
    const response = await page.request.get(link); assert.equal(response.status(), 200); assert.equal(response.headers()['content-type'], 'application/pdf');
  }
  await page.screenshot({ path: path.join(folder, 'official-library.png'), fullPage: true });
  await page.getByRole('button', { name: '口语练习', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(folder, 'home-mobile.png'), fullPage: true });
  assert.equal(await page.evaluate(() => document.body.scrollWidth), 390);
  await page.setViewportSize({ width: 1440, height: 1050 });
  if (noLive) {
    assert.deepEqual(errors, []); console.log('UI_LIBRARY_MOBILE_PASSED'); await browser.close(); return;
  }

  const readyToRecord = async () => {
    await page.waitForFunction(() => !!document.querySelector('.play-overlay') || document.querySelector('[aria-label="数字人提问视频"]').currentTime > .1, null, { timeout: 240000 });
    if (await page.locator('.play-overlay').isVisible()) await page.locator('.play-overlay').click();
    await page.waitForFunction(() => document.querySelector('[aria-label="数字人提问视频"]').currentTime > .2, null, { timeout: 30000 });
    await page.screenshot({ path: path.join(folder, 'live-neural-avatar.png'), fullPage: true });
    await page.waitForFunction(() => document.querySelector('#recordButton')?.textContent.includes('结束录音'), null, { timeout: 90000 });
  };

  // IELTS Part 2: reduced, explicitly labelled demo timing; real ASR and feedback.
  await page.selectOption('#section', 'part2');
  await page.check('#quickMode');
  await page.click('#startButton');
  await readyToRecord();
  await page.waitForTimeout(4800);
  await page.click('#recordButton');
  await page.waitForFunction(() => document.querySelector('.dialogue-heading')?.textContent.includes('QUESTION 2'), null, { timeout: 180000 });
  const sessionId = await page.evaluate(() => localStorage.getItem('polyspeak-session'));
  let session = await (await page.request.get(`${base}/api/speaking/sessions/${sessionId}`)).json();
  assert.equal(session.turns[0].stage, 'part2'); assert.ok(session.turns[0].audio_id); assert.match(session.turns[0].answer.toLowerCase(), /bread|aunt|learn/);
  console.log('IELTS_MICROPHONE_ASR_SAVED', session.turns[0].answer);
  await page.getByRole('button', { name: '提前结束并复盘' }).click();
  await page.waitForSelector('#reportPanel', { timeout: 120000 });
  session = await (await page.request.get(`${base}/api/speaking/sessions/${sessionId}`)).json();
  assert.equal(session.report.source, 'live_model'); assert.equal(session.report.dimensions.length, 4); assert.equal(session.report.overall_score, null);
  for (const example of session.report.examples) assert.ok(session.turns.find(x => x.id === example.turn_id).answer.includes(example.quote));
  assert.equal(session.turns[0].pronunciation.status, 'not_configured');
  await page.screenshot({ path: path.join(folder, 'live-feedback.png'), fullPage: true });
  const downloading = page.waitForEvent('download'); await page.click('#exportButton'); const download = await downloading;
  await download.saveAs(path.join(folder, 'live-feedback-export.json'));
  await page.reload({ waitUntil: 'networkidle' }); await page.waitForSelector('#reportPanel');
  await page.setViewportSize({ width: 390, height: 844 }); assert.equal(await page.evaluate(() => document.body.scrollWidth), 390);
  await page.screenshot({ path: path.join(folder, 'feedback-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1050 });

  // TOEFL: a short official repeat excerpt, submitted by the live microphone path.
  await page.getByRole('button', { name: /官方资料库/ }).click();
  await page.locator('.excerpt-card').filter({ hasText: '官方复述短题例 · 动物园' }).click();
  await page.click('#startButton');
  await page.waitForFunction(() => document.querySelector('.question-text')?.textContent.includes('Listen carefully'), null, { timeout: 30000 });
  assert.ok(!(await page.locator('.question-area').innerText()).includes('We have a variety of wildlife.'));
  await page.waitForFunction(() => document.querySelector('.play-overlay') || document.querySelector('[aria-label="数字人提问视频"]').currentTime > .2, null, { timeout: 180000 });
  if (await page.locator('.play-overlay').isVisible()) await page.locator('.play-overlay').click();
  await page.waitForFunction(() => !document.querySelector('#recordButton').disabled, null, { timeout: 60000 });
  await page.click('#recordButton'); await page.waitForTimeout(3500); await page.click('#recordButton');
  await page.waitForFunction(() => document.querySelector('#answerInput').value.length > 5, null, { timeout: 120000 });
  await page.click('#sendButton'); await page.waitForSelector('#reportPanel', { timeout: 120000 });
  assert.ok((await page.locator('#reportPanel').innerText()).includes('We have a variety of wildlife.'));
  // Real timer expiry: an 8-second mock repeat recording must submit itself.
  await page.getByRole('button', { name: '再练一次 ↗', exact: true }).click();
  await page.selectOption('#mode', 'mock');
  await page.selectOption('#practiceSet', 'toefl-makerspace');
  await page.selectOption('#section', 'repeat');
  await page.click('#startButton');
  await readyToRecord();
  await page.waitForFunction(() => document.querySelector('.dialogue-heading')?.textContent.includes('QUESTION 2'), null, { timeout: 150000 });
  const timedId = await page.evaluate(() => localStorage.getItem('polyspeak-session'));
  const timed = await (await page.request.get(`${base}/api/speaking/sessions/${timedId}`)).json();
  assert.ok(timed.turns[0].duration_seconds >= 6.5 && timed.turns[0].duration_seconds <= 9.5);
  await page.getByRole('button', { name: '提前结束并复盘' }).click();
  await page.waitForSelector('#reportPanel', { timeout: 120000 });
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(folder, 'browser-results.json'), JSON.stringify({ synthetic_microphone: true, library_pdfs: 7, neural_avatar_played: true, ielts_long_turn_microphone: true, transcript: session.turns[0].answer, live_feedback: true, grounded_quotes: true, no_fake_pronunciation: true, export: true, refresh_restore: true, mobile_no_overflow: true, toefl_repeat_hidden_then_revealed: true, errors }, null, 2));
  console.log('SPEAKING_LIVE_BROWSER_PASSED; MOCK_TIMER_AUTO_SUBMIT_PASSED');
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
