<template>
  <section class="layered-report feedback-section">
    <div class="layered-heading"><div><p class="eyebrow">FEATURES → ASPECTS → PROFICIENCY</p><h3>从每一道回答，看见表达的细节。</h3></div><strong v-if="layer.proficiency.practice_score!==null">{{layer.proficiency.practice_score}}<small>/10 练习指标</small></strong></div>
    <p class="fine-print">{{layer.proficiency.scope}}</p>
    <nav class="layered-tabs" aria-label="反馈层级"><button v-for="tab in tabs" :key="tab.id" :class="{active:active===tab.id}" @click="active=tab.id">{{tab.label}}</button></nav>
    <section class="layered-panel" v-show="active==='overview'">
      <div class="layered-steps"><span v-for="(step,index) in layer.pipeline" :key="step"><b>{{index+1}}</b>{{step}}</span></div>
      <p>本次 {{layer.questions.length}} 道有效回答完成逐题分层评价。{{availableFeatures}} 项特征有可用分数；缺少独立音频或视频证据的项目没有计为零分。</p>
      <p class="fine-print">先查看逐题证据，再结合维度总结安排下一次练习。表达建议请与原始录音一起核对。</p>
    </section>
    <section class="layered-panel" v-show="active==='features'">
      <div class="feature-table"><div class="feature-table-heading"><span>评价特征</span><span>练习指标</span><span>有效题数</span></div><div v-for="(feature,key) in layer.features_summary" :key="key" class="feature-table-row"><span>{{feature.label}}</span><strong>{{feature.score===null?'未评估':feature.score+' / 10'}}</strong><span>{{feature.count}}</span></div></div>
      <p class="fine-print">发音、韵律和流利度只使用独立音频接口结果；目光、表情、姿态和手势在未采集考生视频时保持未评估。这里不把词汇识别差异当作发音错误。</p>
    </section>
    <section class="layered-panel" v-show="active==='questions'">
      <button class="text-button" @click="expanded=!expanded">{{expanded?'收起逐题详情':'全部展开逐题详情'}}</button>
      <details v-for="(question,index) in layer.questions" :key="question.turn_id" :open="expanded||printing||index===0" class="question-review">
        <summary>{{index+1}}. {{question.question}}</summary>
        <div class="question-aspects"><article v-for="(aspect,key) in question.aspects" :key="key"><h4>{{aspectNames[key]}} <strong>{{aspect.score===null?'证据不足':aspect.score+'/10'}}</strong></h4><p>{{aspect.justification}}</p></article></div>
        <h4>逐题特征与原话证据</h4>
        <div v-for="(features,group) in question.assessment_criteria" :key="group" class="feature-group"><h5>{{groupNames[group]}}</h5><article v-for="(feature,key) in features" :key="key" class="feature-evidence"><div><strong>{{layer.feature_names[key]}}</strong><span>{{feature.score===null?'未评估':feature.score+'/10'}}</span></div><blockquote v-if="feature.quote">{{feature.quote}}</blockquote><p>{{feature.justification}}</p><p v-if="feature.suggestion" class="fine-print">{{feature.suggestion}}</p></article></div>
        <div class="answer-polishing"><h4>在你的原话上修订</h4><p class="fine-print">{{question.polishing.scope}}</p><div class="polishing-columns"><article><h5>原始回答</h5><p>{{question.polishing.original}}</p></article><article><h5>表达修订稿</h5><p>{{question.polishing.polished_answer}}</p></article></div><ul v-if="question.polishing.corrections.length"><li v-for="(correction,n) in question.polishing.corrections" :key="n"><q>{{correction.original}}</q> → <q>{{correction.revised}}</q><p>{{correction.reason}}</p></li></ul><p v-else class="fine-print">本题没有返回可安全应用的表达替换，保留原回答。</p></div>
      </details>
    </section>
  </section>
</template>

<script>
export default {
  name: 'LayeredReport',
  props: { layer: { type: Object, required: true } },
  data: () => ({ active:'overview', expanded:false, printing:false,
    tabs:[{id:'overview',label:'综合概览'},{id:'features',label:'13 项特征'},{id:'questions',label:'逐题复盘与修订'}],
    aspectNames:{coherence:'内容组织与衔接',vocabulary:'词汇使用',grammar:'语法表达',task_response:'问题回应与展开'},
    groupNames:{professional_performance:'内容与任务回应',way_of_expression:'语言与组织',oral_expression:'独立音频证据',nonverbal:'考生视频证据'},
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
