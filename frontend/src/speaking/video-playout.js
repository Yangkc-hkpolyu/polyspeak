// Keep native WebRTC audio intact; compensate the measured output-device lag
// in presentation only. A bounded queue prevents latency growing over time.
export class VideoPlayout {
  constructor(video, canvas, delayMs = 180, onPresent = () => {}) {
    this.video = video
    this.canvas = canvas
    this.delayMs = Math.min(500, Math.max(0, Number(delayMs) || 0))
    this.onPresent = onPresent
    this.queue = []
    this.pool = []
    this.generation = 0
    this.limit = Math.ceil(this.delayMs / 40) + 3
  }

  start() {
    if (this.running) return this.ready
    if (!this.canvas || !this.video.requestVideoFrameCallback || !this.delayMs) return Promise.resolve(false)
    this.running = true
    const generation = ++this.generation
    this.ready = new Promise(resolve => { this.resolveReady = resolve })
    const capture = (now, metadata) => {
      if (!this.running || generation !== this.generation) return
      // Reuse full-resolution canvases. Do not encode/rescale the face again.
      if (this.queue.length >= this.limit) this.pool.push(this.queue.shift().frame)
      const frame = this.pool.pop() || document.createElement('canvas')
      if (frame.width !== this.video.videoWidth || frame.height !== this.video.videoHeight) {
        frame.width = this.video.videoWidth
        frame.height = this.video.videoHeight
      }
      frame.getContext('2d', { alpha: false }).drawImage(this.video, 0, 0)
      this.queue.push({ frame, due: metadata.expectedDisplayTime + this.delayMs, metadata })
      this.frameRequest = this.video.requestVideoFrameCallback(capture)
    }
    const present = now => {
      if (!this.running || generation !== this.generation) return
      let selected
      while (this.queue.length && this.queue[0].due <= now) {
        if (selected) this.pool.push(selected.frame)
        selected = this.queue.shift()
      }
      if (selected) {
        const { frame, metadata } = selected
        if (this.canvas.width !== frame.width || this.canvas.height !== frame.height) {
          this.canvas.width = frame.width
          this.canvas.height = frame.height
        }
        this.canvas.getContext('2d', { alpha: false }).drawImage(frame, 0, 0)
        this.canvas.style.visibility = 'visible'
        this.onPresent(now, metadata)
        this.pool.push(frame)
        this.resolveReady?.(true)
        this.resolveReady = null
      }
      this.animationRequest = requestAnimationFrame(present)
    }
    this.frameRequest = this.video.requestVideoFrameCallback(capture)
    this.animationRequest = requestAnimationFrame(present)
    return this.ready
  }

  stop() {
    this.running = false
    this.generation++
    if (this.frameRequest !== undefined) this.video.cancelVideoFrameCallback(this.frameRequest)
    if (this.animationRequest !== undefined) cancelAnimationFrame(this.animationRequest)
    this.queue.length = 0
    this.pool.length = 0
    if (this.canvas) this.canvas.style.visibility = 'hidden'
    this.resolveReady?.(false)
    this.resolveReady = null
  }
}
