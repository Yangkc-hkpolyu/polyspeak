// Test delayed track arrival and autoplay with the real LiveAvatar controller.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const path = require('node:path')

const tick = () => new Promise(resolve => setImmediate(resolve))
function harness() {
  const requests = [], bindings = [], plays = [], states = []
  class Stream {
    constructor(tracks = []) { this.tracks = Array.from(tracks) }
    getTracks() { return this.tracks }
    getAudioTracks() { return this.tracks.filter(t => t.kind === 'audio') }
    getVideoTracks() { return this.tracks.filter(t => t.kind === 'video') }
  }
  class Peer extends EventTarget {
    constructor() { super(); this.connectionState = 'new'; this.iceGatheringState = 'complete' }
    createDataChannel() { return this.channel = { readyState: 'connecting' } }
    addTransceiver() { return {} }
    async createOffer() { return { type: 'offer', sdp: 'offer' } }
    async setLocalDescription(sdp) { this.localDescription = sdp }
    async setRemoteDescription() {
      this.connectionState = 'connected'; this.channel.readyState = 'open'
    }
    track(kind) {
      const event = new Event('track')
      event.track = { kind, stop() {} }
      this.ontrack(event); this.dispatchEvent(event)
    }
    close() { this.connectionState = 'closed' }
  }
  let stream = null
  const video = {
    muted: false, volume: 1,
    get srcObject() { return stream },
    set srcObject(value) { stream = value; if (value) bindings.push(value) },
    async play() {
      plays.push({ tracks: stream.getTracks().map(t => t.kind), muted: this.muted })
      if (this.blocked) throw Object.assign(new Error('Autoplay blocked'), { name: 'NotAllowedError' })
      if (this.waitForPlayback) await this.waitForPlayback
    },
  }
  const context = vm.createContext({
    window: { addEventListener() {}, removeEventListener() {} }, navigator: {},
    RTCPeerConnection: Peer, MediaStream: Stream, setTimeout, clearTimeout,
    api: async () => ({}),
    post: async url => { requests.push(url); return { type: 'answer', sdp: 'answer', live_id: 'test' } },
  })
  const source = fs.readFileSync(path.join(__dirname, '../frontend/src/speaking/live-avatar.js'), 'utf8')
    .replace(/^import .*\r?\n/, '').replace('export class LiveAvatar', 'class LiveAvatar')
  const Avatar = vm.runInContext(source + '\nLiveAvatar', context)
  return { avatar: new Avatar(video, e => states.push(e)), video, requests, bindings, plays, states }
}

async function run() {
  for (const order of [['audio', 'video'], ['video', 'audio']]) {
    const h = harness()
    let connected = false
    const connect = h.avatar.connect().then(() => { connected = true })
    await tick()
    h.avatar.pc.track(order[0]); await tick()
    let secondConnected = false
    const reconnect = h.avatar.connect().then(() => { secondConnected = true })
    await tick()
    assert.equal(h.bindings.length, 0, 'Do not attach or play a one-track stream')
    assert.equal(h.plays.length, 0)
    assert.equal(connected, false, 'Transport alone must not mark complete media ready')
    assert.equal(secondConnected, false, 'Concurrent callers must wait for the same complete stream')
    h.avatar.pc.track(order[1]); await Promise.all([connect, reconnect])
    assert.equal(h.bindings.length, 1)
    assert.deepEqual(h.plays[0], { tracks: ['video', 'audio'], muted: false })
    const before = h.requests.length
    await h.avatar.interrupt()
    assert.equal(h.requests.length, before, 'Idle playback must not flush the media clock')

    h.video.blocked = true
    let generated = 0
    await assert.rejects(h.avatar.speak(async () => { generated++; return { id: 'blocked' } }), { name: 'NotAllowedError' })
    assert.equal(generated, 0, 'Blocked audio playback must not start avatar speech')
    h.video.blocked = false
    let started
    h.video.waitForPlayback = new Promise(resolve => { started = resolve })
    const speech = h.avatar.speak(async () => { generated++; return { id: 'speech' } })
    await tick(); assert.equal(generated, 0, 'Wait for actual playback start before requesting speech')
    started(); await tick()
    assert.equal(generated, 1)
    h.avatar.event({ type: 'speech.end', job_id: 'speech' }); await speech
    assert.equal(h.avatar.currentJob, null)
    assert.equal(h.bindings.length, 1, 'Speaking must reuse the existing complete stream')
    assert(h.plays.every(p => !p.muted && p.tracks.length === 2))
    await h.avatar.close()
  }
  console.log('PASS: both track arrival orders, one-time binding, unmuted playback readiness, blocked autoplay, idle interruption')
}
run().catch(error => { console.error(error); process.exitCode = 1 })
