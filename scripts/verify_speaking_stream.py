"""Measure live WebRTC continuity using a synthetic greeting, without microphone input."""
import asyncio, json, time, sys, wave
from pathlib import Path
import httpx, numpy as np, av
from aiortc import RTCPeerConnection, RTCConfiguration, RTCSessionDescription

async def main():
    folder=Path(__file__).resolve().parents[1]/'speaking-runtime/qa'
    folder.mkdir(exist_ok=True)
    label=sys.argv[1] if len(sys.argv)>1 else 'current'
    pc=RTCPeerConnection(RTCConfiguration(iceServers=[]))
    pc.addTransceiver('audio',direction='recvonly')
    pc.addTransceiver('video',direction='recvonly')
    dc=pc.createDataChannel('dh-state')
    ready=asyncio.Event(); ended=asyncio.Event()
    records={'audio':[], 'video':[], 'events':[]}
    samples=[]; tasks=[]; t0=time.perf_counter()
    converter=av.AudioResampler(format='s16',layout='mono',rate=16000)
    @dc.on('open')
    def on_open(): ready.set()
    @dc.on('message')
    def on_message(data):
        event=json.loads(data)
        if event.get('type','').startswith('speech.'):
            records['events'].append({'time':time.perf_counter()-t0,**event})
        if event.get('type') in ('speech.end','speech.error'): ended.set()
    @pc.on('track')
    def on_track(track):
        async def receive():
            try:
                while True:
                    frame=await track.recv()
                    entry={'wall':time.perf_counter()-t0,'pts':float(frame.pts*frame.time_base)}
                    if track.kind=='audio':
                        for f in converter.resample(frame): samples.append(f.to_ndarray().reshape(-1).copy())
                    records[track.kind].append(entry)
            except Exception: pass
        tasks.append(asyncio.create_task(receive()))
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            status_response=await client.get('http://127.0.0.1:8008/api/speaking/status')
            status_response.raise_for_status()
            records['service']=status_response.json()
            await pc.setLocalDescription(await pc.createOffer())
            r=await client.post('http://127.0.0.1:8008/api/speaking/live/offer',json={'sdp':pc.localDescription.sdp,'type':pc.localDescription.type})
            r.raise_for_status(); offer=r.json()
            await pc.setRemoteDescription(RTCSessionDescription(sdp=offer['sdp'],type=offer['type']))
            await asyncio.wait_for(ready.wait(),30)
            await asyncio.sleep(2)
            r=await client.post(f"http://127.0.0.1:8008/api/speaking/live/{offer['live_id']}/preview", json={'text':'Hello, I am Nora, your English speaking partner. Tell me about a place you enjoy visiting, and explain why it is special to you.','language':'en'})
            r.raise_for_status()
            job_id=r.json()['id']
            await asyncio.wait_for(ended.wait(),45)
            await asyncio.sleep(1)
            records['job']=(await client.get(f"http://127.0.0.1:8008/api/speaking/live/{offer['live_id']}/jobs/{job_id}")).json()
        finally:
            await pc.close()
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
    speech_start=next((e['time'] for e in records['events'] if e['type']=='speech.start'),0)
    speech_end=next((e['time'] for e in records['events'] if e['type']=='speech.end'),time.perf_counter()-t0)
    summary={'events':records['events'], 'job':records.get('job')}
    for kind in ('audio','video'):
        frames=[f for f in records[kind] if speech_start-0.3<=f['wall']<=speech_end+0.3]
        gaps=np.diff([f['wall'] for f in frames])
        summary[kind]={'frames':len(frames),'max_gap_ms':round(float(gaps.max()*1000),1) if len(gaps) else None,'gaps_over_100ms':int((gaps>.1).sum()),'gaps_over_200ms':int((gaps>.2).sum()),'wall_span':round(frames[-1]['wall']-frames[0]['wall'],3) if frames else None,'media_span':round(frames[-1]['pts']-frames[0]['pts'],3) if frames else None}
    if samples:
        with wave.open(str(folder/f'avatar-audio-{label}.wav'),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(np.concatenate(samples).astype('<i2').tobytes())
    (folder/f'stream-timing-{label}.json').write_text(json.dumps({'summary':summary,'records':records},indent=2),encoding='utf-8')
    print(json.dumps(summary))
    metrics=summary['job']['stream_metrics']
    assert summary['job']['status']=='completed', 'The speech job did not finish'
    assert metrics['tts']['synthesis_complete']
    assert metrics['tts']['provider']==records['service']['speech_provider']
    assert metrics['tts']['voice']==records['service']['speech_voice']
    assert metrics['tts']['language']=='en'
    assert metrics['render']['source_underrun_frames']==0, 'Silence was inserted during speech'
    assert metrics['audio_dropped_frames']==metrics['video_dropped_frames']==0, 'Media frames were dropped'
    assert summary['audio']['gaps_over_200ms']==summary['video']['gaps_over_200ms']==0, 'Live delivery stalled'
    assert abs(speech_end-speech_start-metrics['tts']['audio_samples']/16000)<.2, 'Playback duration differs from source audio'

asyncio.run(main())
