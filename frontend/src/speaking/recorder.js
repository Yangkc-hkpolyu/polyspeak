export class VoiceRecorder {
  async authorize() {
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) throw new Error('请用 Chrome / Edge 打开本机平台，以使用实时录音。')
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    stream.getTracks().forEach(track => track.stop())
  }
  async start({ path, onTranscript }) {
    this.stopping = false
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 }, video: false })
      this.context = new AudioContext({ sampleRate: 16000 })
      if (this.context.sampleRate !== 16000) throw new Error('浏览器无法提供 16 kHz 实时录音，请使用 Chrome / Edge。')
      await this.context.audioWorklet.addModule('/speaking-assets/pcm-worklet.js')
      const socket = new WebSocket(location.origin.replace(/^http/, 'ws') + path)
      this.socket = socket
      let readyResolve, readyReject, savedResolve, savedReject, result
      const ready = new Promise((resolve, reject) => { readyResolve = resolve; readyReject = reject })
      this.completed = new Promise((resolve, reject) => { savedResolve = resolve; savedReject = reject })
      this.completed.catch(() => {})
      const timer = setTimeout(() => readyReject(new Error('实时识别连接超时。')), 22000)
      socket.onmessage = event => {
        let data
        try { data = JSON.parse(event.data) } catch { return }
        if (data.type === 'ready') { clearTimeout(timer); readyResolve() }
        if (data.type === 'transcript' && this.socket === socket) onTranscript(data.text, data.final)
        if (data.type === 'recording.saved') { result = data.recording; savedResolve(data.recording) }
        if (data.type === 'error') {
          const error = new Error(data.message || '实时识别未完成。')
          clearTimeout(timer); readyReject(error); savedReject(error)
        }
      }
      socket.onerror = () => { clearTimeout(timer); readyReject(new Error('实时识别连接失败。')); savedReject(new Error('实时识别连接失败。')) }
      socket.onclose = () => {
        clearTimeout(timer)
        if (!result) { readyReject(new Error('实时识别连接已断开。')); savedReject(new Error('实时识别连接已断开。')) }
      }
      await ready
      this.source = this.context.createMediaStreamSource(this.stream)
      this.processor = new AudioWorkletNode(this.context, 'speaking-pcm')
      this.processor.port.onmessage = event => { if (!this.stopping && socket.readyState === WebSocket.OPEN) socket.send(event.data) }
      this.silence = this.context.createGain()
      this.silence.gain.value = 0
      this.source.connect(this.processor)
      this.processor.connect(this.silence)
      this.silence.connect(this.context.destination)
      await this.context.resume()
    } catch (error) { this.abort(); throw error }
  }
  async stop() {
    if (!this.socket || !this.completed) throw new Error('没有正在进行的录音。')
    const socket = this.socket
    const completed = this.completed
    this.stopping = true
    this.release()
    if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'finish' }))
    try { return await completed } finally { socket.close() }
  }
  release() {
    this.processor?.disconnect()
    this.source?.disconnect()
    this.silence?.disconnect()
    this.stream?.getTracks().forEach(track => track.stop())
    if (this.context && this.context.state !== 'closed') this.context.close().catch(() => {})
  }
  abort() {
    this.stopping = true
    this.release()
    this.socket?.close()
  }
}
