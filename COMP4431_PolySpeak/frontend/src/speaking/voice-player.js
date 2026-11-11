// One audio element is both the audible output and the source for mouth motion.
// The server retains hidden question text; only the resulting WAV reaches here.
function interrupted() {
  const error = new Error('Audio playback stopped.')
  error.name = 'AbortError'
  return error
}

export class VoicePlayer {
  constructor(audio, { onState = () => {}, onMouth = () => {} } = {}) {
    this.audio = audio
    this.onState = onState
    this.onMouth = onMouth
    this.generation = 0
    this.level = 0
    this.destroyed = false
    this.onPageHide = () => this.stop()
    window.addEventListener('pagehide', this.onPageHide)
  }

  // Call from the user's start/preview click before waiting for a network
  // request; browsers can then allow subsequent playback and analysis.
  async unlock() {
    if (this.destroyed) throw new Error('The audio player is closed.')
    if (!this.context) {
      const Context = window.AudioContext || window.webkitAudioContext
      if (!Context) throw new Error('Your browser does not support audio analysis. Use Chrome or Edge.')
      const context = new Context()
      try {
        const source = context.createMediaElementSource(this.audio)
        const analyser = context.createAnalyser()
        analyser.fftSize = 1024
        source.connect(analyser)
        analyser.connect(context.destination)
        this.context = context
        this.source = source
        this.analyser = analyser
        this.samples = new Uint8Array(analyser.fftSize)
      } catch (error) {
        context.close().catch(() => {})
        throw error
      }
    }
    if (this.context.state !== 'running') await this.context.resume()
  }

  playQuestion(sessionId, questionId) {
    return this.play(`/api/speaking/sessions/${encodeURIComponent(sessionId)}/question-audio`, { question_id: questionId })
  }

  preview(text) {
    return this.play('/api/speaking/voice/preview', { text, language: 'en' })
  }

  async play(path, payload) {
    if (this.destroyed) throw new Error('The audio player is closed.')
    this.stop()
    const generation = this.generation
    const controller = new AbortController()
    this.request = controller
    let timedOut = false
    const timeout = setTimeout(() => { timedOut = true; controller.abort() }, 120000)
    this.onState({ type: 'speech.loading' })
    try {
      const response = await fetch(path, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload), signal: controller.signal,
      })
      if (!response.ok) {
        let detail
        try { detail = (await response.json()).detail } catch { /* generic error below */ }
        throw new Error(typeof detail === 'string' ? detail : 'Voice generation failed. Please retry.')
      }
      const blob = await response.blob()
      clearTimeout(timeout)
      if (generation !== this.generation || controller.signal.aborted) throw interrupted()
      if (!blob.size) throw new Error('No audio was received. Please retry.')
      await this.unlock()
      if (generation !== this.generation || controller.signal.aborted) throw interrupted()
      this.objectUrl = URL.createObjectURL(blob)
      this.audio.src = this.objectUrl
      await this.playElement(generation)
    } catch (error) {
      if (timedOut && generation === this.generation) {
        const timeoutError = new Error('Voice generation timed out. Check your connection and retry.')
        this.onState({ type: 'speech.error', message: timeoutError.message })
        throw timeoutError
      }
      if (generation !== this.generation || controller.signal.aborted) throw interrupted()
      this.onState({ type: 'speech.error', message: error.message })
      throw error
    } finally {
      clearTimeout(timeout)
      if (this.request === controller) this.request = null
      if (generation === this.generation) this.clearAudio()
    }
  }

  playElement(generation) {
    return new Promise((resolve, reject) => {
      let started = false
      const start = () => {
        if (started || generation !== this.generation || !this.active) return
        started = true
        this.onState({ type: 'speech.start' })
        this.startMouth()
      }
      const finish = error => {
        if (!this.active || this.active.generation !== generation) return
        this.audio.removeEventListener('playing', start)
        this.audio.removeEventListener('ended', ended)
        this.audio.removeEventListener('error', failed)
        this.active = null
        this.stopMouth()
        if (error) reject(error)
        else { this.onState({ type: 'speech.end' }); resolve() }
      }
      const ended = () => finish()
      const failed = () => finish(new Error('Audio playback failed. Please retry.'))
      this.active = { generation, finish }
      this.audio.addEventListener('playing', start)
      this.audio.addEventListener('ended', ended)
      this.audio.addEventListener('error', failed)
      try {
        Promise.resolve(this.audio.play()).then(start).catch(finish)
      } catch (error) { finish(error) }
    })
  }

  startMouth() {
    this.stopMouth()
    let last = performance.now()
    const update = now => {
      if (!this.active || !this.analyser) return
      this.analyser.getByteTimeDomainData(this.samples)
      let sum = 0
      for (let i = 0; i < this.samples.length; i++) {
        const sample = (this.samples[i] - 128) / 128
        sum += sample * sample
      }
      const rms = Math.sqrt(sum / this.samples.length)
      const target = Math.max(0, Math.min(1, (rms - 0.012) * 7))
      const dt = Math.min(.1, Math.max(0, (now - last) / 1000))
      last = now
      const tau = target > this.level ? .045 : .14
      this.level += (target - this.level) * (1 - Math.exp(-dt / tau))
      this.onMouth(this.level)
      this.animation = requestAnimationFrame(update)
    }
    this.animation = requestAnimationFrame(update)
  }

  stopMouth() {
    if (this.animation != null) cancelAnimationFrame(this.animation)
    this.animation = null
    this.level = 0
    this.onMouth(0)
  }

  clearAudio() {
    this.audio.pause()
    this.audio.removeAttribute('src')
    this.audio.load()
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl)
    this.objectUrl = null
  }

  stop() {
    this.generation++
    if (this.request) this.request.abort()
    this.request = null
    if (this.active) this.active.finish(interrupted())
    else this.stopMouth()
    this.clearAudio()
  }

  async destroy() {
    if (this.destroyed) return
    this.destroyed = true
    window.removeEventListener('pagehide', this.onPageHide)
    this.stop()
    this.source?.disconnect()
    this.analyser?.disconnect()
    if (this.context && this.context.state !== 'closed') await this.context.close()
    this.context = this.source = this.analyser = null
  }
}
