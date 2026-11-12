<template>
  <section class="layered-report feedback-section">
    <div class="layered-heading"><div><p class="eyebrow">FEATURES → ASPECTS → PROFICIENCY</p><h3>Explore the details of each answer.</h3></div><strong v-if="layer.proficiency.practice_score!==null">{{layer.proficiency.practice_score}}<small>/10 practice indicator</small></strong></div>
    <p class="fine-print">{{layer.proficiency.scope}}</p>
    <nav class="layered-tabs" aria-label="Feedback views"><button v-for="tab in tabs" :key="tab.id" :class="{active:active===tab.id}" @click="active=tab.id">{{tab.label}}</button></nav>
    <section class="layered-panel" v-show="active==='overview'">
      <div class="layered-steps"><span v-for="(step,index) in layer.pipeline" :key="step"><b>{{index+1}}</b>{{step}}</span></div>
      <p>{{layer.questions.length}} valid answers were reviewed individually. Scores are available for {{availableFeatures}} features; missing independent audio or video evidence is not scored as zero.</p>
      <p class="fine-print">Review the evidence for each answer, then use the aspect summaries to plan your next practice. Check language suggestions against the original recording.</p>
    </section>
    <section class="layered-panel" v-show="active==='features'">
      <div class="feature-table"><div class="feature-table-heading"><span>Assessment feature</span><span>Practice indicator</span><span>Valid answers</span></div><div v-for="(feature,key) in layer.features_summary" :key="key" class="feature-table-row"><span>{{feature.label}}</span><strong>{{feature.score===null?'Not assessed':feature.score+' / 10'}}</strong><span>{{feature.count}}</span></div></div>
      <p class="fine-print">Pronunciation, prosody and fluency use only independent audio assessment results. Gaze, facial expression, posture and gestures remain unassessed without candidate video. Transcription differences are not treated as pronunciation errors.</p>
    </section>
    <section class="layered-panel" v-show="active==='questions'">
      <button class="text-button" @click="expanded=!expanded">{{expanded?'Collapse answer details':'Expand all answer details'}}</button>
      <details v-for="(question,index) in layer.questions" :key="question.turn_id" :open="expanded||printing||index===0" class="question-review">
        <summary>{{index+1}}. {{question.question}}</summary>
        <div class="question-aspects"><article v-for="(aspect,key) in question.aspects" :key="key"><h4>{{aspectNames[key]}} <strong>{{aspect.score===null?'Insufficient evidence':aspect.score+'/10'}}</strong></h4><p>{{aspect.justification}}</p></article></div>
        <h4>Features and evidence from your answer</h4>
        <div v-for="(features,group) in question.assessment_criteria" :key="group" class="feature-group"><h5>{{groupNames[group]}}</h5><article v-for="(feature,key) in features" :key="key" class="feature-evidence"><div><strong>{{layer.feature_names[key]}}</strong><span>{{feature.score===null?'Not assessed':feature.score+'/10'}}</span></div><blockquote v-if="feature.quote">{{feature.quote}}</blockquote><p>{{feature.justification}}</p><p v-if="feature.suggestion" class="fine-print">{{feature.suggestion}}</p></article></div>
        <div class="answer-polishing"><h4>Refine your own words</h4><p class="fine-print">{{question.polishing.scope}}</p><div class="polishing-columns"><article><h5>Original answer</h5><p>{{question.polishing.original}}</p></article><article><h5>Revised answer</h5><p>{{question.polishing.polished_answer}}</p></article></div><ul v-if="question.polishing.corrections.length"><li v-for="(correction,n) in question.polishing.corrections" :key="n"><q>{{correction.original}}</q> → <q>{{correction.revised}}</q><p>{{correction.reason}}</p></li></ul><p v-else class="fine-print">No reliable wording changes were returned for this question. Your original answer is retained.</p></div>
      </details>
    </section>
  </section>
</template>

<script>
export default {
  name: 'LayeredReport',
  props: { layer: { type: Object, required: true } },
  data: () => ({ active:'overview', expanded:false, printing:false,
    tabs:[{id:'overview',label:'Overview'},{id:'features',label:'13 features'},{id:'questions',label:'Answer review & revision'}],
    aspectNames:{coherence:'Coherence & cohesion',vocabulary:'Vocabulary',grammar:'Grammar',task_response:'Task response & development'},
    groupNames:{professional_performance:'Content & task response',way_of_expression:'Language & organisation',oral_expression:'Independent audio evidence',nonverbal:'Candidate video evidence'},
  }),
  computed:{ availableFeatures(){ return Object.values(this.layer.features_summary).filter(value=>value.score!==null).length } },
  mounted(){ this.beforePrint=()=>{this.printing=true};this.afterPrint=()=>{this.printing=false};window.addEventListener('beforeprint',this.beforePrint);window.addEventListener('afterprint',this.afterPrint) },
  beforeDestroy(){ window.removeEventListener('beforeprint',this.beforePrint);window.removeEventListener('afterprint',this.afterPrint) },
}
</script>

<style scoped>
.layered-report{margin-top:28px;padding-top:26px;border-top:1px solid #e2e7df}.layered-heading{display:flex;justify-content:space-between;gap:20px;align-items:center}.layered-heading>strong{font-size:30px;color:#285d52;white-space:nowrap}.layered-heading small{display:block;font-size:11px;font-weight:400}.layered-tabs{display:flex;gap:9px;margin:20px 0;flex-wrap:wrap}.layered-tabs button{padding:9px 15px;background:#f3f5ef;color:#52635a;border:1px solid #dce3d6;border-radius:8px;cursor:pointer}.layered-tabs button.active{background:#285d52;color:white}.layered-panel p{line-height:1.8;overflow-wrap:anywhere}.layered-steps{display:flex;gap:18px;flex-wrap:wrap;margin:20px 0}.layered-steps span{display:flex;gap:8px;align-items:center;font-size:13px}.layered-steps b{background:#e9efe2;border-radius:50%;padding:4px 8px;color:#426546}.feature-table{border:1px solid #dfe5da;border-radius:8px;overflow:hidden}.feature-table-heading,.feature-table-row{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;padding:11px 14px;font-size:13px}.feature-table-heading{background:#edf1e7;font-weight:600}.feature-table-row+div{border-top:1px solid #e7ebe2}.feature-table-row strong{font-size:12px;color:#456254}.question-review{border:1px solid #dce3d6;border-radius:10px;padding:16px;margin:14px 0}.question-review summary{cursor:pointer;font-size:15px;font-weight:600;line-height:1.7}.question-aspects{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}.question-aspects article{background:#f5f7f1;padding:12px;border-radius:8px}.question-aspects h4{font-size:13px;margin:0}.question-aspects p,.feature-evidence p{font-size:13px}.feature-group h5{margin:20px 0 9px;color:#426347}.feature-evidence{padding:12px 0;border-bottom:1px solid #e7ebe2}.feature-evidence>div{display:flex;justify-content:space-between;font-size:13px}.feature-evidence blockquote{font-size:13px;border-left:3px solid #a9bea0;padding:8px 12px;margin:10px 0;background:#f6f8f3}.answer-polishing{margin-top:24px}.polishing-columns{display:grid;grid-template-columns:1fr 1fr;gap:15px}.polishing-columns article{background:#f3f5ee;border-radius:8px;padding:13px}.polishing-columns h5{margin:0 0 8px}.polishing-columns p{font-size:13px;white-space:pre-wrap}.answer-polishing li{font-size:13px;line-height:1.8;margin:12px 0}
@media(max-width:650px){.question-aspects,.polishing-columns{grid-template-columns:1fr}.layered-heading{align-items:flex-start}.feature-table-heading,.feature-table-row{grid-template-columns:1.5fr 1fr .6fr;padding:10px 8px;gap:5px}.layered-heading>strong{font-size:25px}}
@media print{.layered-tabs,.text-button{display:none!important}.layered-panel{display:block!important}.question-review{break-inside:auto}.polishing-columns{grid-template-columns:1fr 1fr}}
</style>
