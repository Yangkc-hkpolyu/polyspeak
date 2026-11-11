// Microphone PCM16 chunks for the original PolyInterview 16 kHz WebSocket ASR.
class SpeakingPCM extends AudioWorkletProcessor {
  constructor() {
    super()
    this.buffer = new Int16Array(320)
    this.index = 0
  }
  process(inputs) {
    const mono = inputs[0]?.[0]
    if (mono) for (const sample of mono) {
      const value = Math.max(-1, Math.min(1, sample))
      this.buffer[this.index++] = value < 0 ? value * 32768 : value * 32767
      if (this.index === 320) {
        this.port.postMessage(this.buffer.buffer, [this.buffer.buffer])
        this.buffer = new Int16Array(320)
        this.index = 0
      }
    }
    return true
  }
}
registerProcessor('speaking-pcm', SpeakingPCM)
