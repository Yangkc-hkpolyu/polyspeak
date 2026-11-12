<template>
  <main class="library-page">
    <div class="page-heading"><div><p class="eyebrow">MORE TOPICS. EVERY QUESTION HAS A SOURCE.</p><h1>Find a topic. Start a conversation.</h1><p>Explore provider question banks and recalled questions by exam, year and task.</p></div><span class="format-chip">Verified on {{library.verified_on}}</span></div>
    <div class="bank-stats"><div><strong>{{stats.by_exam.ielts||0}}</strong><span>IELTS questions</span></div><div><strong>{{stats.by_exam.toefl||0}}</strong><span>Updated TOEFL questions</span></div><div><strong>{{stats.sources||0}}</strong><span>Linked source articles</span></div><div><strong>{{library.sources.length}}</strong><span>Official PDFs</span></div></div>
    <div class="notice">{{library.notice}} This library includes question excerpts. Follow each source link for the full task and the provider commentary.</div>
    <section class="card bank-filter" aria-label="Question filters">
      <label class="bank-search">Search topics or questions<input id="bankSearch" v-model.trim="query" type="search" placeholder="e.g. friends, health, books, technology"></label>
      <label>Exam<select id="bankExam" v-model="exam"><option value="all">All exams</option><option value="ielts">IELTS</option><option value="toefl">TOEFL 2026</option></select></label>
      <label>Year<select id="bankYear" v-model="year"><option value="2026">2026</option><option value="2025">2025 archive</option><option value="all">All years</option></select></label>
      <label>Task<select id="bankStage" v-model="stage"><option value="all">All tasks</option><option v-if="exam!=='toefl'" value="part1">IELTS Part 1</option><option v-if="exam!=='toefl'" value="part2">IELTS Part 2</option><option v-if="exam!=='toefl'" value="part3">IELTS Part 3</option><option v-if="exam!=='ielts'" value="interview">TOEFL Interview</option></select></label>
      <label>Source provider<select id="bankPublisher" v-model="publisher"><option value="all">All providers</option><option v-for="name in publishers" :key="name" :value="name">{{name}}</option></select></label>
      <label>Question wording<select id="bankWording" v-model="wording"><option value="all">All wording</option><option value="excerpt">Excerpts / spelling corrections</option><option value="reconstructed">Translated / rephrased recalls</option></select></label>
    </section>
    <div class="bank-results"><h2>Ready to practise <span>{{filtered.length}} questions</span></h2><button class="text-button" @click="clearFilters">Clear filters</button></div>
    <section class="bank-grid" aria-label="Collected speaking questions">
      <article v-for="item in pageItems" :key="item.id" class="card bank-question">
        <div class="bank-question-meta"><span>{{stageLabel(item.stage)}}</span><span>{{seasonLabel(item.season)}}</span></div>
        <h3>{{item.topic}}</h3><p class="bank-prompt" lang="en">{{item.text}}</p>
        <p class="bank-attribution">{{item.source_kind==='institution_excerpt'?'Provider question bank':'Provider-collected recalled questions'}} · {{wordingLabel(item.wording)}}</p>
        <div class="bank-origin"><span>{{source(item).publisher}}<small>{{source(item).reported_exam_on?'Reported exam date: '+source(item).reported_exam_on:'Published: '+source(item).published_on}}</small></span><a :href="source(item).url" target="_blank" rel="noopener">View source ↗</a></div>
        <button class="button subtle full-width" @click="$emit('choose', {id:item.set_id, exam:item.exam})">Practise this question <span>→</span></button>
      </article>
    </section>
    <div v-if="!filtered.length" class="card empty-state"><h3>No matching questions</h3><p>Try a shorter search, or change the year, exam or task.</p></div>
    <div v-if="pageCount>1" class="bank-pagination"><button class="button subtle" :disabled="page===1" @click="page--">Previous</button><span>Page {{page}} of {{pageCount}}</span><button class="button subtle" :disabled="page===pageCount" @click="page++">Next</button></div>

    <h2 class="library-heading">Official samples and exam guides</h2><p class="bank-section-note">Five public sample documents contain 58 speaking tasks and questions, alongside exam guides and scoring criteria. Short examples are included here; open the original files for full details.</p>
    <section class="source-grid"><article v-for="item in library.sources" :key="item.id" class="card source-card"><span class="source-tag">{{item.exam.toUpperCase()}} · {{item.kind==='official_sample'?'Official public sample':'Official reference'}}</span><h2>{{item.title}}</h2><p>{{item.description}}</p><small>{{item.pages}}</small><div><a :href="item.local_url||item.url" target="_blank" rel="noopener" class="button subtle">Open original file ↗</a><a :href="item.url" target="_blank" rel="noopener" class="text-button">Official source</a></div></article></section>
    <section class="card link-card"><h2>Exam rules and companion audio</h2><a v-for="item in library.format_sources" :key="item.url" :href="item.url" target="_blank" rel="noopener">{{item.title}} ↗</a></section>
    <h2 class="library-heading">Official sample excerpts</h2><div class="excerpt-grid"><button v-for="item in officialSets" :key="item.id" class="card excerpt-card" @click="$emit('choose', item)"><span>{{item.exam.toUpperCase()}} · {{item.count}} sample excerpts</span><strong>{{item.title}}</strong><small>Start guided practice →</small></button></div>
    <h2 class="library-heading">More question banks</h2><section class="bank-access"><article v-for="item in library.access_notes" :key="item.url" class="card"><span class="source-tag">{{item.kind==='prediction'?'Prediction material · Not included in question count':'Question bank link · Not imported'}}</span><h3>{{item.title}}</h3><p>{{item.description}}</p><a :href="item.url" target="_blank" rel="noopener">Visit source ↗</a></article></section>
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
      const query = this.query.toLocaleLowerCase('en-GB');
      return (this.library.collected_questions || []).filter(q =>
        (this.exam === 'all' || q.exam === this.exam) &&
        (this.year === 'all' || q.season.startsWith(this.year)) &&
        (this.stage === 'all' || q.stage === this.stage) &&
        (this.publisher === 'all' || this.source(q).publisher === this.publisher) &&
        (this.wording === 'all' || (this.wording === 'excerpt') === ['verbatim_excerpt', 'edited_excerpt'].includes(q.wording)) &&
        (!query || `${q.topic} ${q.text} ${this.source(q).publisher}`.toLocaleLowerCase('en-GB').includes(query))
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
    seasonLabel(value) { return value.endsWith('09_12') ? `Sep–Dec ${value.slice(0, 4)}` : `${value}`; },
    wordingLabel(value) { return ({verbatim_excerpt:'Verbatim excerpt', edited_excerpt:'Excerpt · Spelling corrected', translated_recall:'Translated Chinese recall', rephrased_recall:'Rephrased recall'})[value] || value; },
    clearFilters() { Object.assign(this, {query:'', exam:'all', year:'all', stage:'all', publisher:'all', wording:'all', page:1}); },
  },
};
</script>
<style src="./question-library.css"></style>
