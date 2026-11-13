const assertEnglishUI = require('./assert_english_ui.cjs');
// Real local browser checks for source browsing. No speech/model API calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('../frontend/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const folder = path.join(root, 'speaking-runtime', 'qa');
const origin = process.env.POLYSPEAK_TEST_URL || 'http://127.0.0.1:8008';

(async () => {
  const browser = await chromium.launch({headless:true, channel:'msedge'});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1050}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    // Question playback already has a separate live verification. This check
    // intentionally does not consume speech API quota or render an avatar.
    await page.route('**/api/speaking/live/offer', route => route.fulfill({status:503, contentType:'application/json', body:JSON.stringify({detail:'Question library check: speech playback is disabled.'})}));
    await page.goto(origin, {waitUntil:'networkidle'});
    const library = await (await page.request.get(origin + '/api/speaking/library')).json();
    const count = async n => { await page.waitForFunction(n => document.querySelector('.bank-results h2')?.textContent.includes(`${n} questions`), n); };
    await assertEnglishUI(page, 'welcome');
    await page.locator('.service-badge').click();
    await assertEnglishUI(page, 'service settings');
    await page.getByRole('button', {name: 'Close ×', exact: true}).click();
    await page.getByRole('button', {name: 'Practice history', exact: true}).click();
    await page.locator('.history-page').waitFor();
    await assertEnglishUI(page, 'practice history');
    await page.getByRole('button', {name:/Question library/}).click();
    await count(library.collected_questions.filter(q => q.season.startsWith('2026')).length);
    assert.equal(await page.locator('.bank-question').count(), 12);
    const first = await page.locator('.bank-prompt').first().textContent();
    await page.getByRole('button', {name:'Next',exact:true}).click();
    assert.notEqual(await page.locator('.bank-prompt').first().textContent(), first);
    await page.getByRole('button', {name:'Clear filters',exact:true}).click();
    await count(library.collected_questions.length);
    await page.locator('#bankExam').selectOption('ielts');
    await page.locator('.bank-more-filters > summary').click();
    await page.locator('#bankYear').selectOption('2026');
    await page.locator('#bankStage').selectOption('part2');
    await count(library.collected_questions.filter(q => q.exam==='ielts' && q.season.startsWith('2026') && q.stage==='part2').length);
    const topic = library.collected_questions.find(q => q.exam==='ielts' && q.season.startsWith('2026') && q.stage==='part2').topic;
    await page.locator('#bankSearch').fill(topic);
    assert.ok(await page.locator('.bank-question').count() > 0);
    const matchingPrompts = new Set(library.collected_questions.filter(q => q.topic.toLowerCase().includes(topic.toLowerCase()) || q.text.toLowerCase().includes(topic.toLowerCase())).map(q => q.text));
    assert.ok((await page.locator('.bank-question h3').allTextContents()).every(x => matchingPrompts.has(x)));
    await page.locator('#bankSearch').fill('zero-matching-prompt-20261024');
    await count(0); assert.ok(await page.getByText('No questions match your filters').isVisible());
    await page.getByRole('button', {name:'Clear filters',exact:true}).click();
    await page.locator('#bankExam').selectOption('toefl');
    await page.locator('#bankPublisher').selectOption('New Oriental');
    await count(3);
    await page.locator('#bankPublisher').selectOption('all');
    await page.locator('#bankYear').selectOption('2025');
    await count(0);
    await page.locator('#bankYear').selectOption('2026');
    await page.locator('#bankWording').selectOption('reconstructed');
    await count(66);
    await page.locator('.bank-source-details > summary').first().click();
    const sourceLink = page.locator('.bank-origin a').first();
    assert.ok((await sourceLink.getAttribute('href')).startsWith('https://www.testdaily.cn/'));
    await page.evaluate(() => window.scrollTo({top:0,behavior:'instant'}));
    await assertEnglishUI(page, 'verify_question_bank');
    await page.screenshot({path:path.join(folder,'question-bank-desktop.png'),fullPage:false});
    assert.equal(await page.evaluate(() => document.body.scrollWidth),1440);
    if (!process.argv.includes('--desktop-only')) {
      await page.setViewportSize({width:390,height:844});
      assert.equal(await page.evaluate(() => document.body.scrollWidth),390);
      await assertEnglishUI(page, 'verify_question_bank');
      await page.screenshot({path:path.join(folder,'question-bank-mobile.png'),fullPage:false});
    }
    await page.setViewportSize({width:1440,height:1050});
    await page.locator('.bank-question').first().getByRole('button',{name:/Practice this question/}).click();
    assert.equal(await page.locator('#mode').inputValue(),'coach');
    const selected = await page.locator('#practiceSet').inputValue();
    assert.ok(selected.startsWith('bank-td-'));
    await page.locator('.advanced-options > summary').click();
    await page.locator('#offlineMode').check();
    await page.locator('#startButton').click();
    await page.locator('.source-details > summary').click();
    await page.waitForSelector('.question-source a');
    assert.ok(await page.getByText('Translated from a Chinese recall; not the original English wording',{exact:false}).isVisible());
    assert.ok((await page.locator('.question-source a').getAttribute('href')).startsWith('https://www.testdaily.cn/'));
    assert.equal(await page.locator('.stage-list li').count(),1);
    await page.evaluate(() => window.scrollTo({top:0,behavior:'instant'}));
    await assertEnglishUI(page, 'verify_question_bank');
    await page.screenshot({path:path.join(folder,'question-bank-practice.png'),fullPage:false});
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(folder,'question-bank-browser.json'),JSON.stringify({questions:library.collected_questions.length,source_articles:library.web_sources.length,filters:true,pagination:true,empty_state:true,single_practice:true,provenance_display:true,mobile_no_overflow:process.argv.includes('--desktop-only') ? 'not_checked' : true,external_api_calls:false,errors},null,2));
    console.log('QUESTION_BANK_BROWSER_PASSED');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode=1; });
