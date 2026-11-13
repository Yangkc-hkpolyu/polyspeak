<template>
  <section class="voice-review" aria-label="Voice practice advice">
    <h5>Pace and pause review</h5>
    <p class="fine-print">Get advice on your pace and pauses.</p>
    <p v-if="!result && availability && !availability.ready" class="fine-print">{{availability.message}}</p>
    <button class="button subtle" :disabled="busy" @click="review">{{busy ? 'Reviewing your recording…' : result ? 'Review again' : 'Review pace and pauses'}}</button>
    <p v-if="error" role="alert">{{error}}</p>
    <div v-if="result" aria-live="polite">
      <dl class="voice-measurements">
        <div><dt>Estimated pace</dt><dd>{{number(result.metrics.words_per_minute, ' words/min')}}</dd></div>
        <div><dt>Pauses of at least 0.6 s</dt><dd>{{number(result.metrics.pause_count)}}</dd></div>
        <div><dt>Detected span</dt><dd>{{number(result.metrics.speaking_span_seconds, ' s')}}</dd></div>
      </dl>
      <p v-if="result.advice.status==='ok'"><strong>Fine-tuned voice advice</strong><br>{{result.advice.advice}}</p>
      <p v-else class="fine-print">{{result.advice.message}}</p>
      <details class="voice-method"><summary>About these estimates</summary><p class="fine-print">{{result.scope}}</p></details>
    </div>
  </section>
</template>

<script>
import { post } from './api'
export default {
  name: 'VoiceCoach',
  props: { sessionId: {type: String, required: true}, turn: {type: Object, required: true}, availability: {type: Object, default: null} },
  data() { return {result: this.turn.voice_coach || null, busy: false, error: ''} },
  methods: {
    number(value, suffix = '') { return Number.isFinite(value) ? `${Math.round(value * 10) / 10}${suffix}` : 'Not available' },
    async review() {
      this.busy = true; this.error = ''
      try { this.result = await post(`/api/speaking/sessions/${this.sessionId}/turns/${this.turn.id}/voice-coach`, {}) }
      catch (error) { this.error = error.message }
      finally { this.busy = false }
    },
  },
}
</script>

<style scoped>
.voice-review{margin:18px 0 8px;padding:16px;background:#f4f7f0;border-radius:10px;overflow-wrap:anywhere}
.voice-review h5{margin:0;font-size:15px}.voice-review p{line-height:1.7}
.voice-measurements{display:flex;flex-wrap:wrap;gap:18px;margin:18px 0}
.voice-measurements dt{font-size:12px;color:#52635a}.voice-measurements dd{margin:6px 0 0;font-weight:600}
.voice-method{font-size:12px;color:#52635a;margin-top:12px}.voice-method summary{cursor:pointer}
@media print{button{display:none}}
</style>
