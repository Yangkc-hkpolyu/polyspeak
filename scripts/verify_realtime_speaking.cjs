const assertEnglishUI = require('./assert_english_ui.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('../frontend/node_modules/playwright');

(async () => {
  const browser = await chromium.launch({headless:true,channel:'msedge',args:[
    '--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',
    '--use-file-for-fake-audio-capture='+path.resolve('speaking-runtime/qa/synthetic-input.wav'),
    '--autoplay-policy=no-user-gesture-required']});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1100},permissions:['microphone']});
    const errors=[],requests=[],asrEvents=[];
    let liveId,previewJobId;
    page.on('response',async response=>{
      if(response.url().endsWith('/live/offer')) liveId=(await response.json()).live_id;
      if(response.url().endsWith('/preview')) previewJobId=(await response.json()).id;
    });
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',request=>requests.push(request.url()));
    page.on('websocket',socket=>socket.on('framereceived',event=>{
      try {const value=JSON.parse(event.payload); if(value.type==='transcript') asrEvents.push(value);} catch {}
    }));
    await page.goto('http://127.0.0.1:8008/',{waitUntil:'networkidle'});
    const video=page.locator('[aria-label="Nora asking a question"]');
    await page.waitForFunction(()=>{const v=document.querySelector('[aria-label="Nora asking a question"]');return v?.srcObject instanceof MediaStream&&v.videoWidth>0&&v.currentTime>.2;},null,{timeout:60000});
    const idleTime=await video.evaluate(v=>v.currentTime);
    await page.getByRole('button',{name:'▷ Meet Nora',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.nameplate p')?.textContent.includes('Listen closely'),null,{timeout:30000});
    await assertEnglishUI(page, 'verify_realtime_speaking');
    await page.screenshot({path:'speaking-runtime/qa/realtime-avatar-ui.png',fullPage:true});
    await page.waitForFunction(()=>document.querySelector('.nameplate p')?.textContent.includes('Your turn'),null,{timeout:30000});
    assert(await video.evaluate(v=>v.currentTime)>idleTime);
    assert.equal(await video.evaluate(v=>v.currentSrc),'');
    await page.selectOption('#mode','coach');
    await page.selectOption('#section','part1');
    await page.getByRole('button',{name:/Enter the speaking room/}).click();
    await page.waitForFunction(()=>document.querySelector('.nameplate p')?.textContent.includes('Your turn'),null,{timeout:60000});
    await page.locator('#recordButton').click();
    await page.waitForFunction(()=>document.querySelector('#recordButton')?.textContent.includes('Stop recording'),null,{timeout:30000});
    await page.waitForFunction(()=>document.querySelector('#answerInput')?.value.length>5,null,{timeout:20000});
    assert(asrEvents.length>0);
    await assertEnglishUI(page, 'verify_realtime_speaking');
    await page.screenshot({path:'speaking-runtime/qa/realtime-asr-ui.png',fullPage:true});
    await page.locator('#recordButton').click();
    await page.waitForFunction(()=>!document.querySelector('#recordButton')?.disabled,null,{timeout:30000});
    const answer=await page.locator('#answerInput').inputValue();
    assert(answer.length>5);
    assert(!requests.some(url=>url.includes('/capture')));
    assert(!requests.some(url=>/\/media\/.+\.mp4/.test(url)));
    assert(!requests.some(url=>url.includes('/question-media')));
    await page.locator('#answerInput').fill('I study computer science because I enjoy solving practical problems. For example, I am building an English speaking practice application with my classmates.');
    await page.getByRole('button',{name:/Submit answer/}).click();
    await page.waitForFunction(()=>document.querySelector('.nameplate p')?.textContent.includes('Your turn'),null,{timeout:60000});
    const feedbackResponse = page.waitForResponse(response => response.url().endsWith('/finish') && response.request().method() === 'POST');
    await page.getByRole('button',{name:'Finish early and review',exact:true}).click();
    const feedbackState = await (await feedbackResponse).json();
    assert(feedbackState.report, feedbackState.report_error || 'The session did not produce a feedback report');
    await page.getByRole('button',{name:'13 features',exact:true}).waitFor({timeout:90000});
    await page.getByRole('button',{name:'13 features',exact:true}).click();
    assert.equal(await page.locator('.feature-table-row').count(),13);
    await assertEnglishUI(page, 'verify_realtime_speaking');
    await page.screenshot({path:'speaking-runtime/qa/layered-feedback-ui.png',fullPage:true});
    await page.getByRole('button',{name:'Answer review & revision',exact:true}).click();
    assert.equal(await page.locator('.polishing-columns').count(),1);
    await assertEnglishUI(page, 'verify_realtime_speaking');
    await page.screenshot({path:'speaking-runtime/qa/layered-answer-review.png',fullPage:true});
    const download=page.waitForEvent('download');
    await page.locator('#exportButton').click();
    await (await download).saveAs('speaking-runtime/qa/realtime-layered-report.json');
    const exported=JSON.parse(fs.readFileSync('speaking-runtime/qa/realtime-layered-report.json','utf8'));
    assert.equal(exported.report.layered.questions.length,1);
    assert(!/[\u3400-\u9fff]/u.test(JSON.stringify(exported)), 'Feedback export must be English');
    assert.equal(exported.report.layered.features_summary.eye_contact.score,null);
    assert.equal(exported.turns[0].pronunciation.status,'not_configured');
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.body.scrollWidth),390);
    await assertEnglishUI(page, 'verify_realtime_speaking');
    await page.screenshot({path:'speaking-runtime/qa/layered-feedback-mobile.png',fullPage:true});
    assert.deepEqual(errors,[]);
    const result={webrtc_media_stream_received:true,continuous_idle_after_speech:true,
      no_utterance_mp4_requests:true,realtime_transcript_before_stop:true,
      asr_events:asrEvents.length,transcript:answer,errors};
    result.layered_features=13;
    result.grounded_polishing_and_export_verified=true;
    fs.writeFileSync('speaking-runtime/qa/realtime-browser.json',JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
    await page.close();
    const response=await (await browser.newPage()).request.get(`http://127.0.0.1:8008/api/speaking/live/${liveId}/jobs/${previewJobId}`);
    assert.equal(response.status(),404);
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
