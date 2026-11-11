<template>
  <main class="library-page">
    <div class="page-heading"><div><p class="eyebrow">MORE TOPICS. EVERY QUESTION HAS A SOURCE.</p><h1>找到想聊的话题，就从这一题开始。</h1><p>机构当季题库与考场回忆，按考试、年份和题型挑选。</p></div><span class="format-chip">核验于 {{library.verified_on}}</span></div>
    <div class="bank-stats"><div><strong>{{stats.by_exam.ielts||0}}</strong><span>雅思题目</span></div><div><strong>{{stats.by_exam.toefl||0}}</strong><span>新版托福题目</span></div><div><strong>{{stats.sources||0}}</strong><span>可核对的来源文章</span></div><div><strong>{{library.sources.length}}</strong><span>官方 PDF 资料</span></div></div>
    <div class="notice">{{library.notice}} 这里只收录题干节选；完整题卡与机构解析可通过每题的来源链接查看。</div>
    <section class="card bank-filter" aria-label="题目筛选">
      <label class="bank-search">搜索话题或英文题干<input id="bankSearch" v-model.trim="query" type="search" placeholder="例如：朋友、健康、books、technology"></label>
      <label>考试<select id="bankExam" v-model="exam"><option value="all">全部考试</option><option value="ielts">IELTS 雅思</option><option value="toefl">TOEFL 2026</option></select></label>
      <label>年份<select id="bankYear" v-model="year"><option value="2026">2026 年</option><option value="2025">2025 年旧题</option><option value="all">全部年份</option></select></label>
      <label>题型<select id="bankStage" v-model="stage"><option value="all">全部题型</option><option v-if="exam!=='toefl'" value="part1">IELTS Part 1</option><option v-if="exam!=='toefl'" value="part2">IELTS Part 2</option><option v-if="exam!=='toefl'" value="part3">IELTS Part 3</option><option v-if="exam!=='ielts'" value="interview">TOEFL 访谈</option></select></label>
      <label>来源机构<select id="bankPublisher" v-model="publisher"><option value="all">全部机构</option><option v-for="name in publishers" :key="name" :value="name">{{name}}</option></select></label>
      <label>题干形式<select id="bankWording" v-model="wording"><option value="all">全部形式</option><option value="excerpt">原文短摘／拼写校正</option><option value="reconstructed">英译／重述回忆题</option></select></label>
    </section>
    <div class="bank-results"><h2>可直接练习 <span>{{filtered.length}} 题</span></h2><button class="text-button" @click="clearFilters">清除筛选</button></div>
    <section class="bank-grid" aria-label="收集的口语题目">
      <article v-for="item in pageItems" :key="item.id" class="card bank-question">
        <div class="bank-question-meta"><span>{{stageLabel(item.stage)}}</span><span>{{seasonLabel(item.season)}}</span></div>
        <h3>{{item.topic}}</h3><p class="bank-prompt" lang="en">{{item.text}}</p>
        <p class="bank-attribution">{{item.source_kind==='institution_excerpt'?'机构当季题库':'机构整理考场回忆'}} · {{wordingLabel(item.wording)}}</p>
        <div class="bank-origin"><span>{{source(item).publisher}}<small>{{source(item).reported_exam_on?'回忆考试日期：'+source(item).reported_exam_on:'发布：'+source(item).published_on}}</small></span><a :href="source(item).url" target="_blank" rel="noopener">核对来源 ↗</a></div>
        <button class="button subtle full-width" @click="$emit('choose', {id:item.set_id, exam:item.exam})">练这一题 <span>→</span></button>
      </article>
    </section>
    <div v-if="!filtered.length" class="card empty-state"><h3>暂时没有符合条件的题目</h3><p>试试缩短关键词，或切换年份、考试和题型。</p></div>
    <div v-if="pageCount>1" class="bank-pagination"><button class="button subtle" :disabled="page===1" @click="page--">上一页</button><span>第 {{page}} / {{pageCount}} 页</span><button class="button subtle" :disabled="page===pageCount" @click="page++">下一页</button></div>

    <h2 class="library-heading">官方样题与考试说明</h2><p class="bank-section-note">5 份公开样题包含 58 个口语任务／问题，另附考试说明和评分标准。平台保留短题例，完整内容请打开原文件。</p>
    <section class="source-grid"><article v-for="item in library.sources" :key="item.id" class="card source-card"><span class="source-tag">{{item.exam.toUpperCase()}} · {{item.kind==='official_sample'?'官方公开样题':'官方参考资料'}}</span><h2>{{item.title}}</h2><p>{{item.description}}</p><small>{{item.pages}}</small><div><a :href="item.local_url||item.url" target="_blank" rel="noopener" class="button subtle">打开原文件 ↗</a><a :href="item.url" target="_blank" rel="noopener" class="text-button">官方来源</a></div></article></section>
    <section class="card link-card"><h2>考试规则与配套音频</h2><a v-for="item in library.format_sources" :key="item.url" :href="item.url" target="_blank" rel="noopener">{{item.title}} ↗</a></section>
    <h2 class="library-heading">官方短题例</h2><div class="excerpt-grid"><button v-for="item in officialSets" :key="item.id" class="card excerpt-card" @click="$emit('choose', item)"><span>{{item.exam.toUpperCase()}} · {{item.count}} 道短题例</span><strong>{{item.title}}</strong><small>进入分项陪练 →</small></button></div>
    <h2 class="library-heading">更多题库入口</h2><section class="bank-access"><article v-for="item in library.access_notes" :key="item.url" class="card"><span class="source-tag">{{item.kind==='prediction'?'预测资料 · 未计入题数':'题库入口 · 尚未导入'}}</span><h3>{{item.title}}</h3><p>{{item.description}}</p><a :href="item.url" target="_blank" rel="noopener">前往查看 ↗</a></article></section>
  </main>
</template>

<script>
export default {
  name: 'QuestionLibrary',
  props: { library: { type: Object, required: true } },
  data: () => ({ query: '', exam: 'all', year: '2026', stage: 'all', publisher: 'all', wording: 'all', page: 1 }),
  computed: {
    stats() { return this.library.collection_stats || { by_exam: {} }; },
    sourceMap() { return Object.fromEntries((this.library.web_sources || []).map(s => [s.id, s])); },
    publishers() { return [...new Set((this.library.web_sources || []).map(s => s.publisher))]; },
    officialSets() { return this.library.sets.filter(s => s.kind === 'official_excerpt'); },
    filtered() {
      const query = this.query.toLocaleLowerCase();
      return (this.library.collected_questions || []).filter(q =>
        (this.exam === 'all' || q.exam === this.exam) &&
        (this.year === 'all' || q.season.startsWith(this.year)) &&
        (this.stage === 'all' || q.stage === this.stage) &&
        (this.publisher === 'all' || this.source(q).publisher === this.publisher) &&
        (this.wording === 'all' || (this.wording === 'excerpt') === ['verbatim_excerpt', 'edited_excerpt'].includes(q.wording)) &&
        (!query || `${q.topic} ${q.text} ${this.source(q).publisher}`.toLocaleLowerCase().includes(query))
      );
    },
    pageCount() { return Math.max(1, Math.ceil(this.filtered.length / 12)); },
    pageItems() { return this.filtered.slice((this.page - 1) * 12, this.page * 12); },
  },
  watch: {
    filtered() { this.page = 1; },
    exam() { this.stage = 'all'; },
  },
  methods: {
    source(q) { return this.sourceMap[q.source_id] || {}; },
    stageLabel(value) { return ({part1:'IELTS · Part 1', part2:'IELTS · Part 2', part3:'IELTS · Part 3', interview:'TOEFL · Take an Interview'})[value] || value; },
    seasonLabel(value) { return value.endsWith('09_12') ? `${value.slice(0, 4)} 年 9–12 月` : `${value} 年`; },
    wordingLabel(value) { return ({verbatim_excerpt:'原文短摘', edited_excerpt:'短摘 · 已校正拼写', translated_recall:'中文回忆英译', rephrased_recall:'回忆题重述'})[value] || value; },
    clearFilters() { Object.assign(this, {query:'', exam:'all', year:'all', stage:'all', publisher:'all', wording:'all', page:1}); },
  },
};
</script>
<style src="./question-library.css"></style>
