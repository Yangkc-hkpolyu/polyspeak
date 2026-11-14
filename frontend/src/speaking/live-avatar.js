import { api, post } from './api'
import { VideoPlayout } from './video-playout'

export class LiveAvatar {
  constructor(video, state, { canvas, playoutDelayMs = 180 } = {}) {
    this.video = video
    this.state = state
    this.playout = canvas ? new VideoPlayout(video, canvas, playoutDelayMs) : null
    this.jobs = new Map()
    this.closed = false
    this.unload = () => { this.playout?.stop(); this.pc?.close(); if(this.id) navigator.sendBeacon(`/api/speaking/live/${this.id}/close`) }
    window.addEventListener('pagehide',this.unload)
  }
  async connect() {
    if (this.connecting) return this.connecting
    if (this.pc?.connectionState === 'connected' && this.channel?.readyState === 'open' &&
        this.video.srcObject?.getAudioTracks().length && this.video.srcObject?.getVideoTracks().length) return
    this.connecting = this.open()
    try { await this.connecting } catch (error) { await this.close(); throw error } finally { this.connecting = null }
  }
  async open() {
    if (this.pc) await this.close()
    this.closed = false
    window.addEventListener('pagehide',this.unload)
    const pc = new RTCPeerConnection({ iceServers: [] })
    this.pc = pc
    this.channel = pc.createDataChannel('dh-state')
    this.channel.onmessage = event => this.event(JSON.parse(event.data))
    const videoTransceiver = pc.addTransceiver('video', { direction: 'recvonly' })
    pc.addTransceiver('audio', { direction: 'recvonly' })
    // Advertise the same codec preference as the avatar sender, before SDP.
    const codecs = window.RTCRtpReceiver?.getCapabilities?.('video')?.codecs
    if (codecs && videoTransceiver.setCodecPreferences) {
      videoTransceiver.setCodecPreferences([
        ...codecs.filter(codec => codec.mimeType.toLowerCase() === 'video/h264'),
        ...codecs.filter(codec => codec.mimeType.toLowerCase() !== 'video/h264'),
      ])
    }
    // Match PolyInterview: attach a complete A/V stream once. Starting the
    // element with one track, or starting it muted, can initialise the audio
    // renderer later than the video renderer on the first utterance.
    this.tracks = new Map()
    pc.ontrack = event => {
      this.tracks.set(event.track.kind, event.track)
      if (!this.tracks.has('audio') || !this.tracks.has('video')) return
      const tracks = [this.tracks.get('video'), this.tracks.get('audio')]
      if (tracks.every(track => this.video.srcObject?.getTracks().includes(track))) return
      this.playout?.stop()
      this.video.srcObject = new MediaStream(tracks)
      this.play().catch(error => {
        if (!this.closed && error.name === 'NotAllowedError') this.state({ type: 'playback.blocked' })
      })
    }
    pc.onconnectionstatechange = () => {
      if (['failed', 'disconnected', 'closed'].includes(pc.connectionState) && !this.closed) {
        this.state({ type: 'connection.error', message: 'The live avatar connection was lost. Please reconnect.' })
        for (const waiter of this.jobs.values()) waiter.reject(new Error('The live avatar connection was lost.'))
        this.jobs.clear()
      }
    }
    await pc.setLocalDescription(await pc.createOffer())
    if (pc.iceGatheringState !== 'complete') await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('The avatar connection setup timed out.')), 12000)
      const listener = () => { if (pc.iceGatheringState === 'complete') { clearTimeout(timer); pc.removeEventListener('icegatheringstatechange', listener); resolve() } }
      pc.addEventListener('icegatheringstatechange', listener)
      listener()
    })
    const answer = await post('/api/speaking/live/offer', { type: 'offer', sdp: pc.localDescription.sdp })
    this.id = answer.live_id
    await pc.setRemoteDescription({ type: answer.type, sdp: answer.sdp })
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('The live avatar connection timed out. Check your network and try again.')), 20000)
      const ready = () => {
        if (this.channel.readyState === 'open' && pc.connectionState === 'connected' &&
            this.video.srcObject?.getAudioTracks().length && this.video.srcObject?.getVideoTracks().length) {
          clearTimeout(timer); pc.removeEventListener('track', ready); pc.removeEventListener('connectionstatechange', ready); resolve()
        }
      }
      this.channel.onopen = ready
      pc.addEventListener('track', ready)
      pc.addEventListener('connectionstatechange', ready)
      ready()
    })
    this.state({ type: 'connection.ready' })
  }
  event(event) {
    if (!event.job_id || event.job_id === this.currentJob) this.state(event)
    if (event.job_id === this.currentJob && ['speech.end', 'speech.error', 'speech.interrupted'].includes(event.type)) this.currentJob = null
    const waiter = this.jobs.get(event.job_id)
    if (waiter && event.type === 'speech.end') { this.jobs.delete(event.job_id); waiter.resolve() }
    if (waiter && ['speech.error', 'speech.interrupted'].includes(event.type)) {
      this.jobs.delete(event.job_id)
      waiter.reject(new Error(event.message || 'Speech playback stopped.'))
    }
  }
  async play() {
    // A resolved play() means playback has started, unlike connection.ready.
    // If autoplay is blocked, let the existing Play button provide the gesture;
    // never generate speech while only silent video is able to play.
    this.video.muted = false
    this.video.volume = 1
    await this.video.play()
    if (this.closed) throw new Error('The avatar connection is closed.')
    // Reveal the source element before waiting for its first video callback.
    this.state({ type: 'playback.ready' })
    await this.playout?.start()
    if (this.closed) throw new Error('The avatar connection is closed.')
  }
  async speak(create) {
    await this.connect()
    await this.interrupting
    await this.play()
    const job = await create(this.id)
    this.currentJob = job.id
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => { this.jobs.delete(job.id); reject(new Error('Live speech timed out. Please try again.')) }, 120000)
      this.jobs.set(job.id, {
        resolve: () => { clearTimeout(timeout); resolve() },
        reject: error => { clearTimeout(timeout); reject(error) },
      })
    })
  }
  async interrupt() {
    if (!this.id || this.closed || !this.currentJob) return
    if (this.interrupting) return this.interrupting
    this.interrupting = post(`/api/speaking/live/${this.id}/interrupt`, {}).catch(() => {})
    try { await this.interrupting } finally { this.interrupting = null }
  }
  async close() {
    this.closed = true
    this.playout?.stop()
    window.removeEventListener('pagehide',this.unload)
    for (const waiter of this.jobs.values()) waiter.reject(new Error('The avatar connection is closed.'))
    this.jobs.clear()
    this.pc?.close()
    this.video.srcObject?.getTracks().forEach(track => track.stop())
    this.video.srcObject = null
    if (this.id) await api(`/api/speaking/live/${this.id}`, { method: 'DELETE' }).catch(() => {})
    this.id = null
  }
}
