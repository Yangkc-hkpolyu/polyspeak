// Exercise the real microphone worklet with a delayed / failed ASR connection.
// A fake microphone and WebSocket avoid sending anyone's voice to a provider.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('../frontend/node_modules/playwright');
const url = process.env.POLYSPEAK_TEST_URL || 'http://127.0.0.1:8009';

(async () => {
  const browser = await chromium.launch({headless:true, channel:'msedge', args:[
    '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
  ]});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}, permissions:['microphone']});
    const errors=[]; page.on('pageerror', error => errors.push(error.message));
    const response = await page.request.post(url+'/api/speaking/sessions', {data:{
      exam:'ielts',set_id:'ielts-learning',mode:'mock',section:'part1',execution:'demo',pace:'standard',
    }});
    assert.equal(response.status(),200);
    const session = await response.json();
    await page.addInitScript(id => localStorage.setItem('polyspeak-session',id), session.id);
    await page.route('**/api/speaking/live/offer', r => r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Avatar paused for timer regression check.'})}));
    let attempts=0, firstPCM=0, finished=0;
    await page.routeWebSocket('**/stt?*', socket => {
      attempts++;
      if(attempts===1){setTimeout(()=>socket.send(JSON.stringify({type:'error',message:'Simulated ASR connection failure.'})),1500);return;}
      setTimeout(()=>socket.send(JSON.stringify({type:'ready'})),3500);
      socket.onMessage(data => {
        if(typeof data !== 'string'){firstPCM ||= Date.now();return;}
        if(JSON.parse(data).type==='finish') {
          finished=Date.now();
          socket.send(JSON.stringify({type:'error',message:'Synthetic timer check complete; no personal recording was saved.'}));
        }
      });
    });
    await page.goto(url,{waitUntil:'networkidle'});
    await page.locator('#replayButton').click();
    await page.getByRole('button',{name:'Read and start',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.toast')?.textContent.includes('Simulated ASR'));
    const snapshot=async()=> (await (await page.request.get(`${url}/api/speaking/sessions/${session.id}`)).json()).current_question;
    assert.equal((await snapshot()).answer_until,null,'Failed ASR setup must not start the clock');
    assert.equal((await page.locator('#countdown').innerText()).replace(/\s/g,''),'00:30');
    await page.locator('#recordButton').click();
    await page.waitForTimeout(2000);
    assert.equal(firstPCM,0,'No microphone frames are sent before ASR is ready');
    assert.equal((await snapshot()).answer_until,null,'Setup delay must not consume answer time');
    assert.equal((await page.locator('#countdown').innerText()).replace(/\s/g,''),'00:30');
    await page.screenshot({path:'speaking-runtime/qa/timer-connecting.png'});
    await page.waitForFunction(()=>document.querySelector('#recordButton')?.textContent.includes('Stop recording'));
    assert.equal((await page.locator('#countdown').innerText()).replace(/\s/g,''),'00:30');
    const begun=await snapshot();
    assert(begun.answer_until >= firstPCM/1000+29.5);
    await page.screenshot({path:'speaking-runtime/qa/timer-recording.png'});
    await page.waitForFunction(()=>document.querySelector('.toast')?.textContent.includes('Synthetic timer'),null,{timeout:34000});
    assert(finished-firstPCM>=29700 && finished-firstPCM<31000,`Recording lasted ${finished-firstPCM} ms`);
    assert.deepEqual(errors,[]);
    const result={connection_failure_did_not_start_timer:true,setup_delay_ms:3500,answer_seconds:30,recording_ms:finished-firstPCM,errors};
    fs.writeFileSync('speaking-runtime/qa/recording-timer.json',JSON.stringify(result,null,2));
    console.log(result);
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
