import { VoiceRecorder } from './recorder'
import { LiveAvatar } from './live-avatar'
import { api, post } from './api'
import QuestionLibrary from './QuestionLibrary.vue'
import LayeredReport from './LayeredReport.vue'

const recorder = new VoiceRecorder();
const stages = { part1: 'Part 1 · Introduction & interview', part2: 'Part 2 · Individual long turn', rounding: 'Part 2 · Rounding off', part3: 'Part 3 · Two-way discussion', repeat: 'Listen and Repeat', interview: 'Take an Interview' };
const sections = { ielts: [{ value: 'full', label: 'Full test · Parts 1–3' }, { value: 'part1', label: 'Part 1 · Introduction & interview' }, { value: 'part2', label: 'Part 2 · Individual long turn' }, { value: 'part3', label: 'Part 3 · Two-way discussion' }], toefl: [{ value: 'full', label: 'Full test · 7 repetitions + 4 interview questions' }, { value: 'repeat', label: 'Listen and Repeat' }, { value: 'interview', label: 'Take an Interview' }] };


export default {
  name: 'SpeakingApp',
  components: { QuestionLibrary, LayeredReport },
  data: () => ({
    view: 'practice', status: {}, library: { sets: [], sources: [], format_sources: [] }, history: [], session: null,
    form: { exam: 'ielts', set_id: 'ielts-learning', mode: 'mock', section: 'full', candidate_name: '' },
    offlineMode: false, quickMode: false, busy: false, busyLabel: '', draft: '', notes: '', recordingResult: null,
    recording: false, startingRecording: false, transcribing: false, recordStarted: 0, recordTimer: null,
    mediaBusy: false, mediaToken: 0, mediaProgress: 0, mediaLabel: '', videoVisible: false, playBlocked: false,
    playing: false, mediaQuestionId: null, mediaFailed: false, avatarCaption: 'Ready when you are.',
    liveConnected: false, liveConnecting: false,
    now: Date.now(), serverOffset: 0, ticker: null, toastMessage: '', toastTimer: null, settingsOpen: false, testingConnection: false,
    showTranscript: false, dimensionName: { coherence: 'Coherence & cohesion', vocabulary: 'Vocabulary', grammar: 'Grammar', task_response: 'Task response & development' },
  }),
  computed: {
    navigationLocked() { return this.busy || this.recording || this.transcribing || this.mediaBusy || this.playing || this.startingRecording || this.isMock && !!this.currentQuestion; },
    currentQuestion() { return this.session?.current_question || null; },
    availableSets() { return this.library.sets.filter(x => x.exam === this.form.exam && (this.form.mode === 'coach' || x.mock_allowed) && (!x.from_collection || x.id === this.form.set_id)); },
    officialSets() { return this.library.sets.filter(x => x.kind === 'official_excerpt'); },
    selectedSet() { return this.library.sets.find(x => x.id === this.form.set_id); },
    currentQuestionSource() { return this.currentQuestion?.provenance; },
    sections() { const selected = this.selectedSet; return sections[this.form.exam].filter(x => x.value === 'full' || !selected || selected.sections.includes(x.value)).map(x => x.value === 'full' && selected && !selected.mock_allowed ? {...x, label:'Selected questions · Guided practice'} : x); },
    isMock() { return !!this.session && this.session.setup.mode === 'mock'; },
    progress() { return this.session ? this.session.completed_questions / this.session.total_questions * 100 : 0; },
    sessionStages() {
      const selected = this.library.sets.find(x => x.id === this.session?.setup.set_id);
      const items = this.session?.setup.exam === 'toefl' ? [{ value: 'repeat', includes: ['repeat'], title: 'Listen and Repeat', description: selected?.mock_allowed ? '7 sentences · Listen, then repeat once' : 'Short repetition examples' }, { value: 'interview', includes: ['interview'], title: 'Take an Interview', description: selected?.mock_allowed ? '4 questions · 45 seconds per answer' : 'Interview question · One follow-up available' }] : [{ value: 'part1', includes: ['part1'], title: 'Introduction & interview', description: 'Everyday questions on familiar topics' }, { value: 'part2', includes: ['part2', 'rounding'], title: 'Individual long turn', description: '1 minute to prepare · Up to 2 minutes to speak' }, { value: 'part3', includes: ['part3'], title: 'Two-way discussion', description: 'Analyse, compare and discuss the topic' }];
      return selected?.mock_allowed ? items : items.filter(x => selected?.sections.some(s => x.includes.includes(s)));
    },
    secondsLeft() {
      const q = this.currentQuestion; if (!q || !q.answer_until) return null;
      const deadline = q.phase === 'preparing' ? q.prepare_until : q.answer_until;
      return Math.max(0, Math.ceil(deadline - this.now / 1000));
    },
    timerDisplay() { const value = this.secondsLeft; return value === null ? '— : —' : `${String(Math.floor(value / 60)).padStart(2, '0')} : ${String(value % 60).padStart(2, '0')}`; },
    timerPhase() { return !this.currentQuestion ? 'YOUR MOMENT' : !this.isMock ? 'Practice timer' : this.currentQuestion.phase === 'listening' ? 'Listen first' : this.currentQuestion.phase === 'preparing' ? 'Preparation time' : this.recording ? 'Time remaining' : 'Answer time'; },
    timerHint() { const q = this.currentQuestion; return !q ? 'Start with what you want to say.' : !this.isMock ? 'Use the timer as a guide. Each recording can last up to two minutes.' : q.phase === 'listening' ? 'The timer starts after the question finishes playing.' : q.phase === 'preparing' ? 'Take notes, then start speaking when preparation time ends.' : 'Your recording stops and submits automatically when time runs out.'; },
    composerHint() { return !this.currentQuestion ? 'Choose a practice session to begin' : this.currentQuestion.phase === 'listening' ? 'Listen to Nora first' : this.currentQuestion.phase === 'preparing' ? 'Preparation time: organise your ideas' : this.isMock ? 'Mock test recordings submit automatically' : 'Your turn to speak'; },
    canRecord() { return this.recording || (!!this.currentQuestion && !this.busy && !this.mediaBusy && !this.playing && !this.startingRecording && !this.transcribing && (!this.isMock || this.currentQuestion.phase === 'answering' && this.secondsLeft > 0)); },
    canSend() { return !!this.currentQuestion && !this.busy && !this.recording && !this.transcribing && !this.startingRecording && (this.draft.trim().length > 1 || !!this.recordingResult); },
    canReplay() { return !!this.currentQuestion && !this.busy && !this.recording && !this.transcribing && !this.startingRecording && !this.mediaBusy && !this.playing && (!this.isMock || this.currentQuestion.phase === 'listening'); },
  },
  watch: {
    view(value) { if (value !== 'practice') this.disconnectAvatar(); else this.$nextTick(this.connectAvatar); },
    'form.set_id'() { if (!this.sections.some(x => x.value === this.form.section)) this.form.section = 'full'; },
    videoVisible(value) { const idle = this.$refs.idleVideo; if (!idle) return; if (value) idle.pause(); else idle.play().catch(() => {}); },
  },
  async mounted() {
    this.ticker = setInterval(this.tick, 200);
    try {
      [this.status, this.library] = await Promise.all([api('/api/speaking/status'), api('/api/speaking/library')]);
      if (!this.status.api_configured) { this.offlineMode = true; this.form.mode = 'coach'; }
      const saved = localStorage.getItem('polyspeak-session');
      if (saved) { try { await this.restore(saved, false); } catch { localStorage.removeItem('polyspeak-session'); } }
      this.$nextTick(this.connectAvatar);
    } catch (error) { this.toast(error.message); }
  },
  beforeDestroy() { clearInterval(this.ticker); clearTimeout(this.recordTimer); clearTimeout(this.toastTimer); this.stopMedia(); this.disconnectAvatar(); recorder.abort(); },
  methods: {
    async connectAvatar() {
      const video = this.$refs.avatarVideo;
      if (!video || this.view !== 'practice' || this.session?.report) return;
      this.liveConnecting = true;
      try {
        if (!this.live || this.live.video !== video || this.live.closed) {
          if (this.live) await this.live.close();
          this.live = new LiveAvatar(video, this.liveEvent);
        }
        await this.live.connect();
      } catch (error) { this.liveConnected = false; this.videoVisible = false; this.avatarCaption = error.message; }
      finally { this.liveConnecting = false; }
    },
    disconnectAvatar() { this.liveConnected = false; this.videoVisible = false; if (this.live) this.live.close(); },
    liveEvent(event) {
      if (event.type === 'connection.ready') { this.liveConnected = true; this.videoVisible = true; this.avatarCaption = 'Connected and ready to listen.'; }
      if (event.type === 'connection.error') { this.liveConnected = false; this.videoVisible = false; this.avatarCaption = event.message; }
      if (event.type === 'speech.start') { this.playing = true; this.mediaBusy = false; this.avatarCaption = 'Listen closely. Your turn is next.'; }
      if (event.type === 'speech.end') this.playing = false;
    },
    stageName(value) { return stages[value] || value; },
    sourceLabel(value) { return ({ official_excerpt: 'Official sample excerpt', original_practice: 'Original practice questions', institution_excerpt: 'Provider question bank excerpt', recalled_excerpt: 'Provider-collected recalled questions', ai_generated: 'Follow-up based on your answer' })[value] || ''; },
    wordingLabel(value) { return ({verbatim_excerpt:'Verbatim excerpt', edited_excerpt:'Spelling corrected', translated_recall:'Translated from a Chinese recall; not the original English wording', rephrased_recall:'Rephrased recall; not the original English wording'})[value] || ''; },
    toast(text) { this.toastMessage = text; clearTimeout(this.toastTimer); this.toastTimer = setTimeout(() => { this.toastMessage = ''; }, 6500); },
    path(suffix = '') { return `/api/speaking/sessions/${this.session.id}${suffix}`; },
    changeExam(exam) { this.form.exam = exam; this.form.section = 'full'; this.validateSelection(); },
    validateSelection() { if (!this.availableSets.some(x => x.id === this.form.set_id)) this.form.set_id = this.availableSets[0]?.id || ''; },
    takeSession(value) {
      const changed = this.currentQuestion?.id !== value.current_question?.id;
      this.session = value; this.serverOffset = value.server_time * 1000 - Date.now(); this.now = Date.now() + this.serverOffset;
      localStorage.setItem('polyspeak-session', value.id);
      if (changed) { this.draft = ''; this.notes = ''; this.recordingResult = null; this.mediaFailed = false; }
      if (value.report) { this.stopMedia(); this.disconnectAvatar(); }
    },
    async startSession() {
      if (this.busy) return; this.busy = true; this.busyLabel = 'Preparing your speaking practice'; this.stopMedia();
      try {
        if (this.form.mode === 'mock') await recorder.authorize();
        const value = await post('/api/speaking/sessions', { ...this.form, pace: this.quickMode ? 'demo' : 'standard', execution: this.offlineMode ? 'demo' : 'live' });
        this.takeSession(value); this.busy = false; this.$nextTick(this.playQuestion);
      } catch (error) { this.toast(error.name === 'NotAllowedError' ? 'Mock tests require microphone access. Allow recording in your browser, or choose guided practice to type an answer.' : error.message); }
      finally { this.busy = false; }
    },
    async restore(id, play = false) {
      this.stopMedia(); this.view = 'practice'; this.takeSession(await api(`/api/speaking/sessions/${id}`));
      if (this.currentQuestion?.phase === 'listening' && play) this.$nextTick(this.playQuestion);
      else if (this.isMock && this.currentQuestion?.phase === 'answering' && this.secondsLeft > 0) this.toast('The timer has resumed. Select Start recording to continue this question.');
    },
    async openHistory() { this.view = 'history'; try { this.history = await api('/api/speaking/sessions'); } catch (error) { this.toast(error.message); } },
    resetPractice() { this.stopMedia(); this.session = null; this.draft = ''; this.notes = ''; this.recordingResult = null; this.showTranscript = false; localStorage.removeItem('polyspeak-session'); this.view = 'practice'; this.$nextTick(this.connectAvatar); window.scrollTo({ top: 0, behavior: 'smooth' }); },
    chooseExcerpt(item) { if (this.recording || this.transcribing || this.busy) return; this.resetPractice(); this.form.exam = item.exam; this.form.mode = 'coach'; this.form.section = 'full'; this.form.set_id = item.id; },
    stopMedia() {
      this.mediaToken++; this.mediaBusy = false; this.playing = false; this.videoVisible = this.liveConnected; this.playBlocked = false; this.mediaQuestionId = null;
      return this.live?.interrupt();
    },
    async playQuestion() {
      if (!this.currentQuestion || !this.canReplay) return;
      const questionId = this.currentQuestion.id;
      await this.playMedia(liveId => post(`/api/speaking/live/${liveId}/question/${this.session.id}`, { question_id: questionId }), questionId);
    },
    async previewNora() { await this.playMedia(liveId => post(`/api/speaking/live/${liveId}/preview`, { text: "Hi, I'm Nora. Let's practise English together, one question at a time. Listen, speak, and discover what you can improve.", language: 'en' }), null); },
    async playMedia(create, questionId) {
      await this.stopMedia(); const token = this.mediaToken; this.mediaQuestionId = questionId; this.mediaBusy = true; this.mediaFailed = false; this.mediaProgress = 10; this.mediaLabel = 'Connecting to live speech…';
      try {
        await this.connectAvatar();
        if (!this.liveConnected) throw new Error('The live avatar is not connected yet. Select Reconnect Nora.');
        this.mediaLabel = 'Waiting for live speech…';
        await this.live.speak(create);
        if (token === this.mediaToken) { await new Promise(resolve => setTimeout(resolve, 180)); if (token === this.mediaToken) await this.mediaEnded(questionId); }
      } catch (error) { if (token === this.mediaToken) { this.mediaFailed = true; this.playing = false; this.playBlocked = error.name === 'NotAllowedError'; this.avatarCaption = 'Live speech did not finish. Please try again.'; this.toast(error.message); } }
      finally { if (token === this.mediaToken) this.mediaBusy = false; }
    },
    async resumeVideo() { try { this.$refs.avatarVideo.muted = false; await this.$refs.avatarVideo.play(); this.playBlocked = false; if (this.currentQuestion) this.playQuestion(); else this.previewNora(); } catch { this.toast('Could not play the live video. Please try again.'); } },
    async mediaEnded(questionId = this.mediaQuestionId) {
      this.videoVisible = this.liveConnected; this.playing = false; this.avatarCaption = 'Your turn. I am listening.';
      if (questionId && this.currentQuestion?.id === questionId && this.currentQuestion.phase === 'listening') await this.questionReady();
    },
    async questionReady() {
      try {
        this.takeSession(await post(this.path('/ready'), { question_id: this.currentQuestion.id }));
        if (this.isMock && this.currentQuestion.phase === 'answering') await this.beginRecording();
      } catch (error) { this.toast(error.message); }
    },
    tick() {
      this.now = Date.now() + this.serverOffset;
      const q = this.currentQuestion; if (!q || this.busy || this.transcribing || this.startingRecording) return;
      if (this.isMock && q.phase === 'preparing' && this.secondsLeft === 0) this.beginRecording();
      else if (this.isMock && q.phase === 'answering' && this.secondsLeft === 0 && this.recording) this.stopRecording();
    },
    async beginRecording() {
      if (!this.currentQuestion || this.recording || this.startingRecording || this.transcribing || this.busy) return;
      this.startingRecording = true;
      try {
        this.takeSession(await post(this.path('/begin-answer'), { question_id: this.currentQuestion.id }));
        if (this.isMock && this.secondsLeft <= 0) throw new Error('Time is up for this question. Skip it to continue.');
        await recorder.start({ path: this.path(`/stt?question_id=${encodeURIComponent(this.currentQuestion.id)}`), onTranscript: text => { this.draft = text; } }); this.recording = true; this.recordStarted = Date.now();
        this.recordingResult = null; this.draft = '';
        const duration = this.isMock ? Math.max(0.3, this.currentQuestion.answer_until - (Date.now() + this.serverOffset) / 1000) : 120;
        this.recordTimer = setTimeout(this.stopRecording, duration * 1000);
      } catch (error) { this.toast(error.name === 'NotAllowedError' ? 'Microphone access was denied. Allow recording in your browser.' : error.message); }
      finally { this.startingRecording = false; }
    },
    async stopRecording() {
      if (!this.recording) return;
      this.recording = false; this.transcribing = true; clearTimeout(this.recordTimer); let submit = false;
      try {
        this.recordingResult = await recorder.stop();
        this.draft = this.recordingResult.text || ''; submit = this.isMock;
        if (this.recordingResult.transcription_error) this.toast('Your recording was saved, but transcription did not finish. This answer will be marked as having insufficient text evidence.');
      } catch (error) { this.toast(error.message); }
      finally { this.transcribing = false; }
      if (submit) await this.sendAnswer();
    },
    async sendAnswer(skipped = false) {
      if (!this.currentQuestion || this.busy || this.recording || this.transcribing) return;
      this.stopMedia(); this.busy = true; this.busyLabel = skipped ? 'Saving this question and preparing the next' : 'Saving your answer and preparing the next question';
      try {
        this.takeSession(await post(this.path('/answers'), { question_id: this.currentQuestion.id, answer: this.draft, audio_id: this.recordingResult?.id || null, skipped }));
        this.busy = false;
        if (this.currentQuestion) this.$nextTick(this.playQuestion);
        if (this.session.report_error) this.toast('Your answer was saved. Feedback is not ready yet; please try again.');
      } catch (error) { this.toast(error.message); if (error.status === 409) this.takeSession(await api(this.path())); }
      finally { this.busy = false; }
    },
    skipQuestion() { this.sendAnswer(true); },
    async finishSession() {
      if (this.busy || this.recording || this.transcribing) return;
      this.stopMedia(); this.busy = true; this.busyLabel = 'Preparing feedback from your answers';
      try { this.takeSession(await post(this.path('/finish'), {})); } catch (error) { this.toast(error.message); }
      finally { this.busy = false; }
    },
    recordingUrl(id) { return this.path(`/recordings/${id}`); },
    async playWord(turn, word) {
      const ref = this.$refs['audio-' + turn.id], player = Array.isArray(ref) ? ref[0] : ref;
      if (!player) return;
      try { player.currentTime = Math.max(0, word.offset_seconds - .15); await player.play(); } catch { this.toast('Load the audio using the recording player, then select a word to replay it.'); }
    },
    exportReport() { window.location.href = this.path('/export'); },
    printReport() { window.print(); },
    dateLabel(value) { return new Date(value).toLocaleString('en-GB'); },
    async testConnection() {
      this.testingConnection = true;
      try { await post('/api/speaking/check-connection', {}); this.toast('The conversation service is connected. Speech and pronunciation services need separate checks.'); } catch (error) { this.toast(error.message); }
      finally { this.testingConnection = false; }
    },
  },
}
