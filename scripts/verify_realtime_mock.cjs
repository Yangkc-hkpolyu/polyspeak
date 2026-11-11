const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('../frontend/node_modules/playwright');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge',args:[
    '--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',
    '--use-file-for-fake-audio-capture='+path.resolve('speaking-runtime/qa/synthetic-input.wav'),
    '--autoplay-policy=no-user-gesture-required']});
  try{
    const page=await browser.newPage({permissions:['microphone'],viewport:{width:1440,height:1050}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    let sessionId;
    page.on('response',async response=>{if(response.url().endsWith('/api/speaking/sessions')&&response.request().method()==='POST') sessionId=(await response.json()).id;});
    await page.goto('http://127.0.0.1:8008/',{waitUntil:'networkidle'});
    await page.getByRole('button',{name:/TOEFL 2026 新版/}).click();
    await page.selectOption('#section','repeat');
    await page.locator('#quickMode').check();
    await page.getByRole('button',{name:/进入口语练习室/}).click();
    await page.waitForFunction(()=>document.querySelector('#recordButton')?.textContent.includes('结束'),null,{timeout:60000});
    const during=await (await page.request.get(`http://127.0.0.1:8008/api/speaking/sessions/${sessionId}`)).json();
    assert.equal(during.completed_questions,0);
    assert.equal(during.current_question.text,'Listen carefully, then repeat the sentence once.');
    await page.waitForFunction(()=>document.querySelector('.progress-heading strong')?.textContent.trim().startsWith('1 /'),null,{timeout:30000});
    const after=await (await page.request.get(`http://127.0.0.1:8008/api/speaking/sessions/${sessionId}`)).json();
    assert.equal(after.completed_questions,1);
    assert(after.turns[0].audio_id);
    assert(after.turns[0].repetition.target.length>5);
    assert.equal(after.current_question.text,'Listen carefully, then repeat the sentence once.');
    assert.deepEqual(errors,[]);
    await page.screenshot({path:'speaking-runtime/qa/realtime-mock-ui.png',fullPage:true});
    const result={mock_automatic_recording:true,mock_timed_submission:true,repeat_hidden_before_submit:true,
      submitted_original_server_transcript:true,recording_seconds:after.turns[0].duration_seconds,errors};
    fs.writeFileSync('speaking-runtime/qa/realtime-mock.json',JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
    await page.close();
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
