import { api, post } from './api'

export class LiveAvatar {
  constructor(video, state) {
    this.video = video
    this.state = state
    this.jobs = new Map()
    this.closed = false
    this.unload = () => { this.pc?.close(); if(this.id) navigator.sendBeacon(`/api/speaking/live/${this.id}/close`) }
    window.addEventListener('pagehide',this.unload)
  }
  async connect() {
    if (this.pc?.connectionState === 'connected' && this.channel?.readyState === 'open') return
    if (this.connecting) return this.connecting
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
    pc.addTransceiver('audio', { direction: 'recvonly' })
    pc.addTransceiver('video', { direction: 'recvonly' })
    const stream = new MediaStream()
    pc.ontrack = event => {
      stream.addTrack(event.track)
      this.video.srcObject = stream
      this.video.muted = true
      this.video.play().catch(() => {})
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
        if (this.channel.readyState === 'open' && pc.connectionState === 'connected') { clearTimeout(timer); resolve() }
      }
      this.channel.onopen = ready
      pc.addEventListener('connectionstatechange', ready)
      ready()
    })
    this.state({ type: 'connection.ready' })
  }
  event(event) {
    if (!event.job_id || event.job_id === this.currentJob) this.state(event)
    const waiter = this.jobs.get(event.job_id)
    if (waiter && event.type === 'speech.end') { this.jobs.delete(event.job_id); waiter.resolve() }
    if (waiter && ['speech.error', 'speech.interrupted'].includes(event.type)) {
      this.jobs.delete(event.job_id)
      waiter.reject(new Error(event.message || 'Speech playback stopped.'))
    }
  }
  async speak(create) {
    await this.connect()
    await this.interrupting
    this.video.muted = false
    await this.video.play()
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
    if (!this.id || this.closed) return
    if (this.interrupting) return this.interrupting
    this.interrupting = post(`/api/speaking/live/${this.id}/interrupt`, {}).catch(() => {})
    try { await this.interrupting } finally { this.interrupting = null }
  }
  async close() {
    this.closed = true
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
