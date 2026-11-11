import { VoiceRecorder } from './recorder'
import { VoicePlayer } from './voice-player'
import Live2DAvatar from './Live2DAvatar.vue'
import { api, post } from './api'
import QuestionLibrary from './QuestionLibrary.vue'
import LayeredReport from './LayeredReport.vue'

const recorder = new VoiceRecorder();
const stages = { part1: 'Part 1 · Introduction & interview', part2: 'Part 2 · Individual long turn', rounding: 'Part 2 · Rounding off', part3: 'Part 3 · Two-way discussion', repeat: 'Listen and Repeat', interview: 'Take an Interview' };
const sections = { ielts: [{ value: 'full', label: 'Full practice · Part 1–3' }, { value: 'part1', label: 'Part 1 · Everyday questions' }, { value: 'part2', label: 'Part 2 · Individual long turn' }, { value: 'part3', label: 'Part 3 · Discussion' }], toefl: [{ value: 'full', label: 'Full practice · 7 repetitions + 4 interview questions' }, { value: 'repeat', label: 'Listen and Repeat · Listen and repeat' }, { value: 'interview', label: 'Take an Interview · Interview' }] };


export default {
  name: 'SpeakingApp',
  components: { QuestionLibrary, LayeredReport, 'live2d-avatar': Live2DAvatar },
  data: () => ({
    view: 'practice', status: {}, library: { sets: [], sources: [], format_sources: [] }, history: [], session: null,
    form: { exam: 'ielts', set_id: 'ielts-learning', mode: 'mock', section: 'full', candidate_name: '' },
    offlineMode: false, quickMode: false, busy: false, busyLabel: '', draft: '', notes: '', recordingResult: null,
    recording: false, startingRecording: false, transcribing: false, recordStarted: 0, recordTimer: null,
    mediaBusy: false, mediaToken: 0, mediaProgress: 0, mediaLabel: '', playBlocked: false,
    playing: false, mediaQuestionId: null, mediaFailed: false, avatarCaption: 'Ready when you are.',
    liveConnected: false, liveConnecting: true, mouthOpen: 0, avatarKey: 0,
    reducedMotion: typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    now: Date.now(), serverOffset: 0, ticker: null, toastMessage: '', toastTimer: null, settingsOpen: false, testingConnection: false,
    showTranscript: false, dimensionName: { coherence: 'Coherence and cohesion', vocabulary: 'Vocabulary', grammar: 'Grammar', task_response: 'Task response' },
  }),
  computed: {
    navigationLocked() { return this.busy || this.recording || this.transcribing || this.mediaBusy || this.playing || this.startingRecording || this.isMock && !!this.currentQuestion; },
    currentQuestion() { return this.session?.current_question || null; },
    availableSets() { return this.library.sets.filter(x => x.exam === this.form.exam && (this.form.mode === 'coach' || x.mock_allowed) && (!x.from_collection || x.id === this.form.set_id)); },
    officialSets() { return this.library.sets.filter(x => x.kind === 'official_excerpt'); },
    selectedSet() { return this.library.sets.find(x => x.id === this.form.set_id); },
    currentQuestionSource() { return this.currentQuestion?.provenance; },
    sections() { const selected = this.selectedSet; return sections[this.form.exam].filter(x => x.value === 'full' || !selected || selected.sections.includes(x.value)).map(x => x.value === 'full' && selected && !selected.mock_allowed ? {...x, label:'Selected questions · Focused practice'} : x); },
    isMock() { return !!this.session && this.session.setup.mode === 'mock'; },
    progress() { return this.session ? this.session.completed_questions / this.session.total_questions * 100 : 0; },
    sessionStages() {
      const selected = this.library.sets.find(x => x.id === this.session?.setup.set_id);
      const items = this.session?.setup.exam === 'toefl' ? [{ value: 'repeat', includes: ['repeat'], title: 'Listen and Repeat', description: selected?.mock_allowed ? '7 items · Repeat once after listening' : 'Listen and repeat sample' }, { value: 'interview', includes: ['interview'], title: 'Take an Interview', description: selected?.mock_allowed ? '4 questions · 45 seconds each' : 'Interview question · One follow-up' }] : [{ value: 'part1', includes: ['part1'], title: 'Introduction & interview', description: 'Everyday questions on familiar topics' }, { value: 'part2', includes: ['part2', 'rounding'], title: 'Individual long turn', description: '1 minute to prepare · Up to 2 minutes to speak' }, { value: 'part3', includes: ['part3'], title: 'Two-way discussion', description: 'Analyse, compare and discuss a topic' }];
      return selected?.mock_allowed ? items : items.filter(x => selected?.sections.some(s => x.includes.includes(s)));
    },
    secondsLeft() {
      const q = this.currentQuestion; if (!q || !q.answer_until) return null;
      const deadline = q.phase === 'preparing' ? q.prepare_until : q.answer_until;
      return Math.max(0, Math.ceil(deadline - this.now / 1000));
    },
    timerDisplay() { const value = this.secondsLeft; return value === null ? '— : —' : `${String(Math.floor(value / 60)).padStart(2, '0')} : ${String(value % 60).padStart(2, '0')}`; },
    timerPhase() { return !this.currentQuestion ? 'YOUR MOMENT' : !this.isMock ? 'Practice timer' : this.currentQuestion.phase === 'listening' ? 'Listen to the question' : this.currentQuestion.phase === 'preparing' ? 'Preparation time' : this.recording ? 'Answer countdown' : 'Time to answer'; },
    timerHint() { const q = this.currentQuestion; return !q ? 'You do not need to be perfect. Just begin.' : !this.isMock ? 'The timer is a guide. Each recording is limited to two minutes.' : q.phase === 'listening' ? 'The timer starts after the question finishes.' : q.phase === 'preparing' ? 'Take notes and speak when preparation ends.' : 'Recording ends and submits automatically when time is up.'; },
    composerHint() { return !this.currentQuestion ? 'Choose a practice to get started' : this.currentQuestion.phase === 'listening' ? 'Listen to Anya first' : this.currentQuestion.phase === 'preparing' ? 'Prepare and organise your thoughts' : this.isMock ? 'Mock recordings submit automatically' : 'Your turn to speak'; },
    canRecord() { return this.recording || (!!this.currentQuestion && !this.busy && !this.mediaBusy && !this.playing && !this.startingRecording && !this.transcribing && (!this.isMock || this.currentQuestion.phase === 'answering' && this.secondsLeft > 0)); },
    canSend() { return !!this.currentQuestion && !this.busy && !this.recording && !this.transcribing && !this.startingRecording && (this.draft.trim().length > 1 || !!this.recordingResult); },
    canReplay() { return !!this.currentQuestion && !this.busy && !this.recording && !this.transcribing && !this.startingRecording && !this.mediaBusy && !this.playing && (!this.isMock || this.currentQuestion.phase === 'listening'); },
  },
  watch: {
    view(value) { if (value !== 'practice') this.disconnectAvatar(); else { this.liveConnecting = true; this.$nextTick(this.connectAvatar); } },
    'form.set_id'() { if (!this.sections.some(x => x.value === this.form.section)) this.form.section = 'full'; },
    settingsOpen(value) {
      this.$nextTick(() => {
        if (value) this.$refs.settingsClose?.focus();
        else this.$refs.settingsTrigger?.focus();
      });
    },
  },
  async mounted() {
    if (window.matchMedia) {
      this.motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
      this.motionListener = event => { this.reducedMotion = event.matches; };
      if (this.motionPreference.addEventListener) this.motionPreference.addEventListener('change', this.motionListener);
      else this.motionPreference.addListener(this.motionListener);
    }
    this.ticker = setInterval(this.tick, 200);
    try {
      [this.status, this.library] = await Promise.all([api('/api/speaking/status'), api('/api/speaking/library')]);
      if (!this.status.api_configured) { this.offlineMode = true; this.form.mode = 'coach'; }
      const saved = localStorage.getItem('polyspeak-session');
      if (saved) { try { await this.restore(saved, false); } catch { localStorage.removeItem('polyspeak-session'); } }
      this.$nextTick(this.connectAvatar);
    } catch (error) { this.toast(error.message); }
  },
  beforeDestroy() {
    clearInterval(this.ticker); clearTimeout(this.recordTimer); clearTimeout(this.toastTimer); clearTimeout(this.idleFadeTimer);
    if (this.motionPreference) {
      if (this.motionPreference.removeEventListener) this.motionPreference.removeEventListener('change', this.motionListener);
      else this.motionPreference.removeListener(this.motionListener);
    }
    this.stopMedia(); if (this.voice) this.voice.destroy(); recorder.abort();
  },
  methods: {
    trapSettingsFocus(event) {
      const controls = [...this.$refs.settingsModal.querySelectorAll('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled])')];
      if (!controls.length) return;
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    },
    connectAvatar() {
      if (!this.voice && this.$refs.avatarAudio) {
        this.voice = new VoicePlayer(this.$refs.avatarAudio, {
          onState: this.liveEvent,
          onMouth: value => { this.mouthOpen = value; },
        });
      }
    },
    disconnectAvatar() { this.liveConnected = false; this.liveConnecting = false; this.stopMedia(); },
    avatarReady() { this.liveConnected = true; this.liveConnecting = false; this.avatarCaption = 'Ready when you are.'; },
    avatarFailed() { this.liveConnected = false; this.liveConnecting = false; this.avatarCaption = 'The avatar could not load. Please retry.'; },
    retryAvatar() { this.liveConnecting = true; this.avatarKey++; },
    liveEvent(event) {
      if (event.type === 'speech.start') { this.playing = true; this.mediaBusy = false; this.avatarCaption = 'Listen carefully. Your turn is next.'; }
      if (event.type === 'speech.end') this.playing = false;
    },
    stageName(value) { return stages[value] || value; },
    sourceLabel(value) { return ({ official_excerpt: 'Short official sample excerpt', original_practice: 'Original practice questions', institution_excerpt: 'Institutional question bank excerpt', recalled_excerpt: 'Institutional candidate recollection', ai_generated: 'Question generated from your response' })[value] || ''; },
    wordingLabel(value) { return ({verbatim_excerpt:'Original excerpt', edited_excerpt:'Spelling corrected', translated_recall:'Translated recollection, not original English wording', rephrased_recall:'Rephrased recollection, not original English wording'})[value] || ''; },
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
        this.connectAvatar(); await this.voice.unlock();
        if (this.form.mode === 'mock') await recorder.authorize();
        const value = await post('/api/speaking/sessions', { ...this.form, pace: this.quickMode ? 'demo' : 'standard', execution: this.offlineMode ? 'demo' : 'live' });
        this.takeSession(value); this.busy = false; this.$nextTick(this.playQuestion);
      } catch (error) { this.toast(error.name === 'NotAllowedError' ? 'Mock tests require microphone access. Allow it in your browser, or choose guided practice to type.' : error.message); }
      finally { this.busy = false; }
    },
    async restore(id, play = false) {
      this.stopMedia(); this.view = 'practice'; this.takeSession(await api(`/api/speaking/sessions/${id}`));
      if (this.currentQuestion?.phase === 'listening' && play) this.$nextTick(this.playQuestion);
      else if (this.isMock && this.currentQuestion?.phase === 'answering' && this.secondsLeft > 0) this.toast('The timer has resumed. Start recording to continue.');
    },
    async openHistory() { this.view = 'history'; try { this.history = await api('/api/speaking/sessions'); } catch (error) { this.toast(error.message); } },
    resetPractice() { this.stopMedia(); this.session = null; this.draft = ''; this.notes = ''; this.recordingResult = null; this.showTranscript = false; localStorage.removeItem('polyspeak-session'); this.view = 'practice'; this.$nextTick(this.connectAvatar); window.scrollTo({ top: 0, behavior: 'smooth' }); },
    chooseExcerpt(item) { if (this.recording || this.transcribing || this.busy) return; this.resetPractice(); this.form.exam = item.exam; this.form.mode = 'coach'; this.form.section = 'full'; this.form.set_id = item.id; },
    stopMedia() {
      this.mediaToken++; this.mediaBusy = false; this.playing = false; this.playBlocked = false; this.mediaQuestionId = null;
      if (this.voice) this.voice.stop();
    },
    async playQuestion() {
      if (!this.currentQuestion || !this.canReplay) return;
      const questionId = this.currentQuestion.id;
      if (this.session.setup.execution === 'demo') {
        this.avatarCaption = 'Offline demo: read the question and answer when ready.';
        await this.questionReady();
        return;
      }
      await this.playMedia(() => this.voice.playQuestion(this.session.id, questionId), questionId);
    },
    async previewNora() {
      try { this.connectAvatar(); await this.voice.unlock(); await this.playMedia(() => this.voice.preview("Hi, I'm Anya. Let's practise English together, one question at a time."), null); }
      catch (error) { this.toast(error.message); }
    },
    async playMedia(create, questionId) {
      await this.stopMedia(); const token = this.mediaToken; this.mediaQuestionId = questionId; this.mediaBusy = true; this.mediaFailed = false; this.mediaProgress = 10; this.mediaLabel = 'Preparing voice…';
      try {
        this.connectAvatar();
        if (!this.liveConnected) throw new Error('The avatar is not ready yet. Please wait or retry.');
        this.mediaLabel = 'Preparing the audio…';
        await create();
        if (token === this.mediaToken) { await new Promise(resolve => setTimeout(resolve, 180)); if (token === this.mediaToken) await this.mediaEnded(questionId); }
      } catch (error) { if (token === this.mediaToken) { this.mediaFailed = true; this.playing = false; this.playBlocked = error.name === 'NotAllowedError'; this.avatarCaption = 'Voice playback did not finish. Please retry.'; this.toast(error.message); } }
      finally { if (token === this.mediaToken) this.mediaBusy = false; }
    },
    async resumeVideo() { try { this.connectAvatar(); await this.voice.unlock(); this.playBlocked = false; if (this.currentQuestion) this.playQuestion(); else this.previewNora(); } catch { this.toast('Audio could not play. Please retry.'); } },
    async mediaEnded(questionId = this.mediaQuestionId) {
      this.playing = false;
      if (questionId && this.currentQuestion?.id === questionId && this.currentQuestion.phase === 'listening') await this.questionReady();
      else this.avatarCaption = 'Your turn. I am listening.';
    },
    async questionReady() {
      try {
        this.takeSession(await post(this.path('/ready'), { question_id: this.currentQuestion.id }));
        this.avatarCaption = this.currentQuestion.phase === 'preparing' ? 'Prepare now, then answer when the timer ends.' : this.isMock ? 'Your turn. Starting recording.' : 'Your turn. Record or type your answer.';
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
        if (this.isMock && this.secondsLeft <= 0) throw new Error('Time is up. You can skip this question to continue.');
        await recorder.start({ path: this.path(`/stt?question_id=${encodeURIComponent(this.currentQuestion.id)}`), onTranscript: text => { this.draft = text; } }); this.recording = true; this.recordStarted = Date.now(); this.avatarCaption = 'Recording started. Please answer.';
        this.recordingResult = null; this.draft = '';
        const duration = this.isMock ? Math.max(0.3, this.currentQuestion.answer_until - (Date.now() + this.serverOffset) / 1000) : 120;
        this.recordTimer = setTimeout(this.stopRecording, duration * 1000);
      } catch (error) { this.avatarCaption = 'Recording did not start. Check your microphone and retry.'; this.toast(error.name === 'NotAllowedError' ? 'Microphone access was denied. Allow it in your browser.' : error.message); }
      finally { this.startingRecording = false; }
    },
    async stopRecording() {
      if (!this.recording) return;
      this.recording = false; this.transcribing = true; clearTimeout(this.recordTimer); let submit = false;
      try {
        this.recordingResult = await recorder.stop();
        this.draft = this.recordingResult.text || ''; submit = this.isMock;
        if (this.recordingResult.transcription_error) this.toast('The recording was saved, but transcription did not finish. This answer will have insufficient text evidence.');
      } catch (error) { this.toast(error.message); }
      finally { this.transcribing = false; }
      if (submit) await this.sendAnswer();
    },
    async sendAnswer(skipped = false) {
      if (!this.currentQuestion || this.busy || this.recording || this.transcribing) return;
      this.stopMedia(); this.busy = true; this.busyLabel = skipped ? 'Saving this question and preparing the next' : 'Saving your answer and preparing the next';
      try {
        this.takeSession(await post(this.path('/answers'), { question_id: this.currentQuestion.id, answer: this.draft, audio_id: this.recordingResult?.id || null, skipped }));
        this.busy = false;
        if (this.currentQuestion) this.$nextTick(this.playQuestion);
        if (this.session.report_error) this.toast('Your answer was saved, but feedback is not ready. Please retry.');
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
      try { player.currentTime = Math.max(0, word.offset_seconds - .15); await player.play(); } catch { this.toast('Load the recording first, then select a word to replay it.'); }
    },
    exportReport() { window.location.href = this.path('/export'); },
    printReport() { window.print(); },
    dateLabel(value) { return new Date(value).toLocaleString('en-US'); },
    async testConnection() {
      this.testingConnection = true;
      try { await post('/api/speaking/check-connection', {}); this.toast('Conversation connection is working. Test voice and pronunciation services separately.'); } catch (error) { this.toast(error.message); }
      finally { this.testingConnection = false; }
    },
  },
}
