<template>
  <section class="voice-review" :class="{featured}" aria-label="Voice practice advice">
    <h5>{{featured ? 'Your speaking feedback' : 'Pace and pause review'}}</h5>
    <p class="fine-print">{{featured ? 'Our fine-tuned model · Your latest recorded answer' : 'Get advice on your pace and pauses.'}}</p>
    <p v-if="featured" class="review-question">{{turn.question}}</p>
    <p v-if="busy" role="status">Our fine-tuned model is reviewing your recording. This may take about a minute.</p>
    <p v-if="!result && availability && !availability.ready" class="fine-print">{{availability.message}}</p>
    <button v-if="!autoReview || (!busy && (!result || result.advice.status!=='ok'))" class="button subtle" :disabled="busy || availability && !availability.ready" @click="review">{{busy ? 'Reviewing your recording…' : autoReview ? 'Retry feedback' : result ? 'Review again' : 'Review pace and pauses'}}</button>
    <p v-if="error" role="alert">{{error}}</p>
    <div v-if="result" aria-live="polite">
      <p v-if="result.advice.status==='ok'" class="model-advice"><strong>Fine-tuned voice advice</strong><br>{{result.advice.advice}}</p>
      <p v-else class="fine-print">{{result.advice.message}}</p>
      <dl class="voice-measurements">
        <div><dt>Estimated pace</dt><dd>{{number(result.metrics.words_per_minute, ' words/min')}}</dd></div>
        <div><dt>Pauses of at least 0.6 s</dt><dd>{{number(result.metrics.pause_count)}}</dd></div>
        <div><dt>Detected span</dt><dd>{{number(result.metrics.speaking_span_seconds, ' s')}}</dd></div>
      </dl>
      <details class="voice-method"><summary>About these estimates</summary><p class="fine-print">{{result.scope}}</p></details>
    </div>
  </section>
</template>

<script>
import { post } from './api'
export default {
  name: 'VoiceCoach',
  props: { sessionId: {type: String, required: true}, turn: {type: Object, required: true}, availability: {type: Object, default: null}, autoReview: Boolean, featured: Boolean },
  data() { return {result: this.turn.voice_coach || null, busy: false, error: ''} },
  mounted() { if (this.autoReview && this.availability?.ready && this.result?.advice?.status !== 'ok') this.review() },
  methods: {
    number(value, suffix = '') { return Number.isFinite(value) ? `${Math.round(value * 10) / 10}${suffix}` : 'Not available' },
    async review() {
      if (this.busy) return
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
.voice-review.featured{padding:24px;border:1px solid #c8d8c7;margin:24px 0}.featured h5{font-size:21px;color:#34463f}.review-question{font-size:14px;color:#56685f}.model-advice{font-size:16px;color:#34463f}
.voice-measurements{display:flex;flex-wrap:wrap;gap:18px;margin:18px 0}
.voice-measurements dt{font-size:12px;color:#52635a}.voice-measurements dd{margin:6px 0 0;font-weight:600}
.voice-method{font-size:12px;color:#52635a;margin-top:12px}.voice-method summary{cursor:pointer}
@media print{button{display:none}}
</style>
