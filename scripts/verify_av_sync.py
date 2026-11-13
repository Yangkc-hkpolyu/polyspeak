"""Compare decoded mouth onset with audible PCM after six queue interruptions.
Uses the installed Nora reference images and a synthetic English greeting.
This checks media timestamps, not physical speaker/display latency.
"""
import asyncio, json, sys, time, wave
from pathlib import Path
import av, cv2, httpx, numpy as np
from aiortc import RTCPeerConnection, RTCConfiguration, RTCSessionDescription

ROOT=Path(__file__).resolve().parents[1]

async def main():
    label=sys.argv[1] if len(sys.argv)>1 else 'sync-check'
    folder=ROOT/'speaking-runtime/qa'
    manifest=json.loads((ROOT/'speaking-models/avatars/nora/avatar.json').read_text())
    refs=[cv2.imread(str(ROOT/'speaking-models/avatars/nora'/r['full']))[130:345,665:830].copy() for r in manifest['frames']]
    tops=np.stack([r[:105].astype(np.float32) for r in refs])
    pc=RTCPeerConnection(RTCConfiguration(iceServers=[]))
    pc.addTransceiver('audio',direction='recvonly');pc.addTransceiver('video',direction='recvonly')
    channel=pc.createDataChannel('dh-state')
    ready,ended=asyncio.Event(),asyncio.Event()
    events=[];audios=[];videos=[];tasks=[];samples=[]
    started=time.perf_counter()
    converter=av.AudioResampler(format='s16',layout='mono',rate=16000)
    @channel.on('open')
    def opened():ready.set()
    @channel.on('message')
    def message(data):
        item=json.loads(data)
        if item.get('type','').startswith('speech.'):
            events.append({'wall':time.perf_counter()-started,**item})
        if item.get('type') in ('speech.end','speech.error'):ended.set()
    @pc.on('track')
    def track_ready(track):
        async def receive():
            try:
                while True:
                    frame=await track.recv()
                    pts=float(frame.pts*frame.time_base)
                    wall=time.perf_counter()-started
                    if track.kind=='audio':
                        pcm=frame.to_ndarray().astype(np.float32)/32768
                        audios.append({'pts':pts,'wall':wall,'rms':float(np.sqrt(np.mean(pcm**2)))})
                        samples.extend(f.to_ndarray().reshape(-1).copy() for f in converter.resample(frame))
                    else:
                        crop=frame.to_ndarray(format='bgr24')[130:345,665:830].copy()
                        videos.append({'pts':pts,'wall':wall,'crop':crop})
            except Exception: pass
        tasks.append(asyncio.create_task(receive()))
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            await pc.setLocalDescription(await pc.createOffer())
            response=await client.post('http://127.0.0.1:8008/api/speaking/live/offer',json={'sdp':pc.localDescription.sdp,'type':'offer'})
            response.raise_for_status();offer=response.json()
            await pc.setRemoteDescription(RTCSessionDescription(sdp=offer['sdp'],type=offer['type']))
            await asyncio.wait_for(ready.wait(),30)
            await asyncio.sleep(2)
            for _ in range(6):
                await client.post(f"http://127.0.0.1:8008/api/speaking/live/{offer['live_id']}/interrupt",json={})
                await asyncio.sleep(.6)
            response=await client.post(f"http://127.0.0.1:8008/api/speaking/live/{offer['live_id']}/preview",json={'text':'Hello, I am Nora, your English speaking partner. Tell me about a place you enjoy visiting, and explain why it is special to you.','language':'en'})
            response.raise_for_status();job=response.json()
            await asyncio.wait_for(ended.wait(),45)
            await asyncio.sleep(.5)
            metrics=(await client.get(f"http://127.0.0.1:8008/api/speaking/live/{offer['live_id']}/jobs/{job['id']}")).json()
        finally:
            await pc.close()
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
    onset=next(a for a in audios if a['rms']>.001)
    tiles=[];measured=[]
    for v in videos:
        crop=v.pop('crop')
        if onset['pts']-.8<=v['pts']<=onset['pts']+.48:
            match=int(np.argmin(np.mean((tops-crop[:105].astype(np.float32))**2,axis=(1,2,3))))
            mouth=crop[130:185,35:130].astype(np.float32)
            mae=float(np.mean(np.abs(mouth-refs[match][130:185,35:130])))
            v['reference']=match;v['mouth_mae']=mae
            measured.append(v)
            canvas=np.zeros((255,165,3),np.uint8);canvas[:215]=crop
            cv2.putText(canvas,f"{(v['pts']-onset['pts'])*1000:+.0f} ms",(5,230),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,255,0),1)
            cv2.putText(canvas,f"diff {mae:.1f}",(5,248),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,255,0),1)
            tiles.append(canvas)
    while len(tiles)%6:tiles.append(np.zeros_like(tiles[0]))
    image=np.concatenate([np.concatenate(tiles[i:i+6],axis=1) for i in range(0,len(tiles),6)])
    cv2.imwrite(str(folder/f'av-onset-{label}.jpg'),image)
    with wave.open(str(folder/f'av-onset-{label}.wav'),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(np.concatenate(samples).astype('<i2').tobytes())
    result={'audio_onset':onset,'events':events,'job':metrics,'onset_video':measured,'audio':audios}
    (folder/f'av-onset-{label}.json').write_text(json.dumps(result,indent=2))
    mouth=next(v for v in measured if v['mouth_mae']>8)
    lead_ms=round((onset['pts']-mouth['pts'])*1000,1)
    print(json.dumps({'audio_onset_seconds':onset['pts'],'mouth_onset_seconds':mouth['pts'],'mouth_lead_ms':lead_ms,'interruptions':6,'job_status':metrics['status']}))
    assert -60 <= lead_ms <= 60, 'Lip onset and audio onset drifted apart after interruptions'

asyncio.run(main())
