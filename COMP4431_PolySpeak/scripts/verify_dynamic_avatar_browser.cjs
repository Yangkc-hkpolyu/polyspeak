// Historical MP4-renderer check; the current UI uses verify_realtime_speaking.cjs.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require('../frontend/node_modules/playwright');

(async () => {
  const browser = await chromium.launch({headless:true,channel:'msedge'});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1050}});
    const errors = []; page.on('pageerror',e=>errors.push(e.message));
    let job;
    page.on('response',async response=>{
      if (/\/api\/speaking\/media\/[a-f0-9]+$/.test(response.url())) {
        const data=await response.json().catch(()=>null);
        if (data?.status==='ready') job=data;
      }
    });
    await page.goto('http://127.0.0.1:8008',{waitUntil:'networkidle'});
    const status = await (await page.request.get('http://127.0.0.1:8008/api/speaking/status')).json();
    assert.equal(status.avatar_pipeline,'video_frames');
    await page.waitForFunction(()=>{const v=document.querySelector('[aria-label="数字人待机动作"]');return v&&!v.paused&&v.currentTime>.2;});
    const idle = page.locator('[aria-label="数字人待机动作"]');
    assert.equal(await idle.evaluate(v=>v.videoWidth),1276);
    await page.getByRole('button',{name:'▷ 认识 Nora',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.play-overlay') || (()=>{const v=document.querySelector('[aria-label="数字人提问视频"]');return v&&v.currentTime>.2&&!v.paused;})(),null,{timeout:180000});
    if(await page.locator('.play-overlay').isVisible())await page.locator('.play-overlay').click();
    await page.waitForFunction(()=>{const v=document.querySelector('[aria-label="数字人提问视频"]');return v&&!v.paused&&v.currentTime>.2;});
    const video = page.locator('[aria-label="数字人提问视频"]');
    assert.equal(await video.evaluate(v=>v.videoWidth),1276);
    assert.equal(await video.evaluate(v=>v.videoHeight),720);
    await page.screenshot({path:'speaking-runtime/qa/dynamic-avatar-ui.png',fullPage:true});
    await page.waitForFunction(()=>document.querySelector('[aria-label="数字人提问视频"]').ended,null,{timeout:30000});
    assert.equal(await idle.evaluate(v=>v.paused),false);
    assert.equal(await page.evaluate(()=>document.body.scrollWidth),1440);
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.body.scrollWidth),390);
    await page.screenshot({path:'speaking-runtime/qa/dynamic-avatar-mobile.png',fullPage:true});
    assert.deepEqual(errors,[]);
    const result={dynamic_idle_played:true,speech_video_played:true,returned_to_dynamic_idle:true,width:1276,height:720,avatar_source:job?.avatar_source,source_frames:job?.source_frames,render_version:job?.render_version,generation_seconds:job?.generation_seconds,mobile_no_overflow:true,errors};
    fs.writeFileSync('speaking-runtime/qa/dynamic-avatar-browser.json',JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
