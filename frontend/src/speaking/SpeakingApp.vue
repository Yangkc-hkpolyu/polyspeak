<template>
  <div class="polyspeak">
    <header class="topbar">
      <button class="brand" :disabled="navigationLocked" @click="view='practice'"><span class="brand-icon">p</span>poly<span>speak</span><i>.</i></button>
      <nav aria-label="Main navigation"><button :disabled="navigationLocked" :class="{active:view==='practice'}" @click="view='practice'">Speaking practice</button><button :disabled="navigationLocked" :class="{active:view==='library'}" @click="view='library'">Question library <b>{{library.collection_stats ? library.collection_stats.questions : '…'}}</b></button><button :disabled="navigationLocked" :class="{active:view==='history'}" @click="openHistory">Practice history</button></nav>
      <button class="service-badge" @click="settingsOpen=true"><i :class="{unavailable:!status.api_configured}"></i>{{status.api_configured?'Services configured':'Setup required'}}<span>⚙</span></button>
    </header>

    <template v-if="view==='practice'">
      <section class="page-heading"><div><p class="eyebrow">A LITTLE PRACTICE. A CLEARER VOICE.</p><h1>Make English a natural conversation.</h1><p>Practise speaking with Nora and discover ways to improve with every answer.</p></div><span class="format-chip">IELTS <i></i> TOEFL 2026</span></section>
      <main class="workspace">
        <aside class="setup-panel card">
          <template v-if="!session">
            <p class="eyebrow">YOUR PRACTICE, YOUR PACE</p><h2>What will you practise today?</h2>
            <form @submit.prevent="startSession">
              <label>Exam</label><div class="choice-row"><button type="button" :class="{selected:form.exam==='ielts'}" @click="changeExam('ielts')"><strong>IELTS</strong><small>Speaking</small></button><button type="button" :class="{selected:form.exam==='toefl'}" @click="changeExam('toefl')"><strong>TOEFL</strong><small>2026 format</small></button></div>
              <label for="mode">Practice mode</label><select id="mode" v-model="form.mode" @change="validateSelection"><option value="mock">Mock test · Feedback at the end</option><option value="coach">Guided practice · Follow-up questions</option></select>
              <label for="practiceSet">Question set</label><select id="practiceSet" v-model="form.set_id"><option v-for="item in availableSets" :value="item.id" :key="item.id">{{sourceLabel(item.kind)}} · {{item.title}}</option></select>
              <button type="button" class="text-button bank-entry-link" @click="view='library'">Explore more questions →</button>
              <label for="section">Section</label><select id="section" v-model="form.section"><option v-for="item in sections" :value="item.value" :key="item.value">{{item.label}}</option></select>
              <div class="protocol-note"><template v-if="selectedSet&&!selectedSet.mock_allowed"><strong>Guided practice · {{sourceLabel(selectedSet.kind)}}</strong><p>Practise the selected questions with follow-ups from Nora. Excerpts are not full tests; see each question source for details.</p></template><template v-else><strong>{{form.exam==='ielts'?'A structured conversation with an examiner':'Listen and Repeat + Take an Interview'}}</strong><p>{{form.exam==='ielts'?'Part 1 interview → Part 2 preparation and long turn → Part 3 discussion.':'Repeat 7 sentences, then answer 4 interview questions with 45 seconds each. Mock tests do not add AI follow-ups.'}}</p></template></div>
              <label class="check-label"><input id="quickMode" type="checkbox" v-model="quickMode">Quick classroom demo <small>Shortened timing; not a full test</small></label>
              <label class="check-label"><input id="offlineMode" type="checkbox" v-model="offlineMode">Offline walkthrough <small>No AI scores</small></label>
              <button id="startButton" class="button primary full-width" :disabled="busy">{{busy?'Preparing…':'Enter the speaking room'}}<span>↗</span></button>
              <p class="fine-print">Record answers in a mock test, or speak or type in guided practice.<br>All records are stored on this computer.</p>
            </form>
          </template>
          <template v-else>
            <p class="eyebrow">STAY WITH THE CONVERSATION</p><h2>{{session.setup.exam==='ielts'?'IELTS Speaking':'TOEFL Speaking'}}</h2><p class="set-title">{{session.set_title}}</p>
            <div class="summary-tags"><span>{{session.setup.mode==='mock'?'Mock test':'Guided practice'}}</span><span>{{session.setup.pace==='demo'?'Quick demo':'Standard timing'}}</span></div>
            <ol class="stage-list"><li v-for="stage in sessionStages" :key="stage.value" :class="{current:currentQuestion&&stage.includes.includes(currentQuestion.stage)}"><i></i><div><strong>{{stage.title}}</strong><small>{{stage.description}}</small></div></li></ol>
            <div class="progress-heading"><span>Questions completed</span><strong>{{session.completed_questions}} / {{session.total_questions}}</strong></div><div class="progress-track"><i :style="{width:progress+'%'}"></i></div>
            <p class="fine-print">{{session.setup.mode==='mock'?'Mock tests provide no answer hints or live corrections. Review your feedback after the test.':'Nora can ask one follow-up based on your answer. You can check the transcript before submitting.'}}</p>
            <button class="button subtle full-width" :disabled="busy||recording||transcribing" @click="resetPractice">Choose a new practice</button>
            <button v-if="session.turns.length&&!session.report" class="text-button full-width" :disabled="busy||recording||transcribing" @click="finishSession">{{session.report_error?'Retry feedback':'Finish early and review'}}</button>
          </template>
          <div class="side-footer"><span>✦</span><p>Progress starts with your first sentence.</p></div>
        </aside>

        <section v-if="!session||!session.report" class="room card">
          <div class="room-heading"><div><p class="eyebrow">THE SPEAKING ROOM</p><h2>{{currentQuestion?stageName(currentQuestion.stage):'Ready when you are.'}}</h2></div><span class="live-tag"><i></i>{{session?'In progress':'Ready to begin'}}</span></div>
          <div v-if="session&&(session.setup.execution==='demo'||session.setup.pace==='demo')" class="notice demo-notice">{{session.setup.execution==='demo'?'Offline walkthrough: no conversation model is used and no scores are shown. ':''}}{{session.setup.pace==='demo'?'Quick demo uses shortened timing and is not a full test.':''}}</div>
          <div class="room-grid">
            <div class="avatar-column">
              <div class="avatar-stage"><video ref="idleVideo" class="dynamic-avatar" v-show="!videoVisible" src="/speaking-assets/nora-idle.mp4?v=ielts-room-2-calm" poster="/speaking-assets/nora-dynamic.jpg?v=ielts-room-2-calm" aria-label="Nora waiting to speak" autoplay muted loop playsinline preload="auto"></video><video ref="avatarVideo" class="dynamic-avatar" v-show="videoVisible" playsinline preload="auto" aria-label="Nora asking a question" ></video><span class="avatar-label"><i></i>AI SPEAKING PARTNER</span><div class="nameplate"><h3>Nora <span>Here to listen.</span></h3><p>{{avatarCaption}}</p></div><button v-if="playBlocked" class="play-overlay" @click="resumeVideo">▶<span>Play video</span></button><div v-if="mediaBusy" class="media-loading"><span>{{mediaLabel}}</span><div class="progress-track"><i :style="{width:mediaProgress+'%'}"></i></div></div></div>
              <div class="avatar-toolbar"><span class="fine-print" v-if="liveConnected">● Live connection</span><span class="fine-print" v-else-if="liveConnecting">Connecting live…</span><button v-else-if="!liveConnected" class="text-button" @click="connectAvatar">Reconnect Nora</button><button class="text-button" :disabled="busy||recording||transcribing||mediaBusy||!!session" @click="previewNora">▷ Meet Nora</button><button id="replayButton" class="text-button" :disabled="!canReplay" @click="playQuestion">↺ Replay question</button></div>
              <div class="timer-card"><div><span>{{timerPhase}}</span><span class="timer-dot" :class="{recording}"></span></div><strong id="countdown">{{timerDisplay}}</strong><p>{{timerHint}}</p></div>
              <div class="small-note"><span>◌</span><p>Share your view, then give reasons and examples.<br>There is no single correct opinion.</p></div>
            </div>

            <div class="dialogue-column">
              <div class="dialogue-heading"><h3>Focus on your answer.</h3><span v-if="currentQuestion">{{currentQuestion.kind==='followup'?'FOLLOW-UP':'QUESTION '+currentQuestion.number}}</span></div>
              <div v-if="!session" class="welcome"><span>“</span><h3>Give your ideas a voice.</h3><p>Choose a practice session and let Nora guide you through<br>an English conversation at your pace.</p><div><b>01</b> Listen <i>→</i> <b>02</b> Speak <i>→</i> <b>03</b> Review</div></div>
              <div v-else class="question-area">
                <p v-if="currentQuestion" class="question-source">{{sourceLabel(currentQuestion.source_kind)}}<span v-if="currentQuestion.wording"> · {{wordingLabel(currentQuestion.wording)}}</span><span v-if="currentQuestion.context"> · {{currentQuestion.context}}</span></p>
                <p v-if="currentQuestionSource" class="question-source"><a :href="currentQuestionSource.url" target="_blank" rel="noopener">{{currentQuestionSource.publisher}} · View question source ↗</a></p>
                <h3 v-if="currentQuestion" id="questionText" class="question-text">{{currentQuestion.text}}</h3>
                <ul v-if="currentQuestion&&currentQuestion.card.length" class="cue-card"><li v-for="point in currentQuestion.card" :key="point">{{point}}</li></ul>
                <p v-if="currentQuestion&&currentQuestion.task_type==='repeat'" class="fine-print">The original sentence appears after you submit. Listen first, then repeat it once.</p>
                <textarea v-if="currentQuestion&&currentQuestion.stage==='part2'" class="notes-input" v-model="notes" placeholder="Preparation notes (private; not part of your answer)" aria-label="Part 2 preparation notes"></textarea>
                <div v-if="session.report_error" class="notice">Your answer was saved. {{session.report_error}}<button class="text-button" @click="finishSession">Retry feedback</button></div>
                <p v-if="session.notices.length" class="fine-print">{{session.notices[session.notices.length-1]}}</p>
              </div>
              <div class="composer"><div class="composer-heading"><span :class="{recording}">{{recording?'● Recording · Live transcript':transcribing?'Transcribing and saving your recording…':composerHint}}</span><span>ENGLISH</span></div><textarea id="answerInput" v-model="draft" :readonly="isMock" :disabled="!currentQuestion||busy||recording||transcribing" :placeholder="isMock?'Your recording saves and advances automatically. Mock tests retain the original transcript.':'Start recording, or type your answer in English here.'" maxlength="12000"></textarea><div class="composer-actions"><button id="recordButton" class="button record-button" :class="{recording}" :disabled="!canRecord" @click="recording?stopRecording():beginRecording()">{{recording?'■ Stop recording':'◉ Start recording'}}</button><button v-if="!isMock" id="sendButton" class="button primary" :disabled="!canSend" @click="sendAnswer(false)">Submit answer ↗</button><button v-if="isMock&&mediaFailed&&currentQuestion&&currentQuestion.task_type!=='repeat'&&currentQuestion.phase==='listening'" class="button subtle" @click="questionReady">Read and start</button></div><p class="fine-print">{{isMock?'The timer and recording start after the question finishes playing. Your answer submits when time runs out.':'Check your transcript before submitting. Typed answers do not receive pronunciation scores.'}}</p><button v-if="currentQuestion" id="skipButton" class="text-button skip-button" :disabled="busy||recording||transcribing" @click="skipQuestion">Skip question and mark unanswered</button></div>
              <details v-if="session&&session.turns.length" class="past-turns"><summary>{{session.turns.length}} answers submitted</summary><article v-for="turn in session.turns" :key="turn.id"><strong>{{turn.question}}</strong><p>{{turn.answer||'No text answer was captured for this question.'}}</p></article></details>
            </div>
          </div>
          <footer class="room-footer"><span>✧ Your recordings · Nora speaking · Evidence-based feedback</span><span>Improve one step at a time, at your pace.</span></footer>
        </section>

        <section v-else id="reportPanel" class="report card">
          <div class="report-heading"><div><p class="eyebrow">YOUR VOICE, WITH A WAY FORWARD</p><h2>Turn this practice into your next step.</h2><p>{{session.set_title}} · {{session.turns.length}} answers</p></div><span class="completed-badge">✓ Saved</span></div>
          <div class="report-summary"><span>✦</span><p>{{session.report.summary}}</p></div><p class="notice">{{session.report.scope}}</p><p v-if="session.report.source==='offline_demo'" class="notice">This report describes an offline walkthrough. No model was used and no scores are included.</p><p class="fine-print">Text answers: {{session.report.coverage.answered}}; skipped questions: {{session.report.coverage.skipped}}. {{session.report.coverage.early_finish?'This session ended early. Feedback covers only the answers submitted.':''}}</p>
          <div class="dimension-grid"><article v-for="item in session.report.dimensions" :key="item.key"><h3>{{dimensionName[item.key]}}<strong>{{item.score}}<small>/10</small></strong></h3><div class="progress-track"><i :style="{width:item.score*10+'%'}"></i></div><p>{{item.comment}}</p></article></div>
          <layered-report v-if="session.report.layered" :layer="session.report.layered" /><div class="feedback-columns"><section><h3>What went well</h3><ul><li v-for="text in session.report.strengths" :key="text">{{text}}</li></ul></section><section><h3>What to improve next</h3><ul><li v-for="text in session.report.improvements" :key="text">{{text}}</li></ul></section></div>
          <section v-if="session.report.examples.length" class="feedback-section"><h3>Starting with your own words</h3><article v-for="item in session.report.examples" :key="item.turn_id+item.quote" class="quote-feedback"><blockquote>{{item.quote}}</blockquote><p>{{item.suggestion}}</p></article></section>
          <section class="feedback-section"><h3>Your next practice steps</h3><ol><li v-for="text in session.report.next_steps" :key="text">{{text}}</li></ol></section>
          <section class="feedback-section acoustic"><h3>Recordings and pronunciation review</h3><p class="fine-print">Use low-scoring words as replay cues. Transcription differences and pronunciation errors are shown separately.</p><article v-for="turn in session.turns" :key="turn.id"><h4>{{stageName(turn.stage)}} · {{turn.question}}</h4><audio v-if="turn.audio_id" :ref="'audio-'+turn.id" :src="recordingUrl(turn.audio_id)" controls preload="none"></audio><p v-if="turn.pronunciation.status!=='available'" class="fine-print">{{turn.pronunciation.message||'Pronunciation was not assessed.'}}</p><template v-else><p>Azure mean word accuracy: {{turn.pronunciation.word_accuracy_mean}} / 100</p><div class="word-feedback"><button v-for="(word,index) in turn.pronunciation.words" :key="index" :class="{low:word.accuracy!==null&&word.accuracy<70}" @click="playWord(turn,word)">{{word.word}} <small>{{word.accuracy}}</small></button></div><p class="fine-print">{{turn.pronunciation.scope}}</p></template><div v-if="turn.repetition" class="repeat-feedback"><p><b>Original</b> {{turn.repetition.target}}</p><p><b>Transcript</b> {{turn.repetition.recognized}}</p><p v-for="(diff,index) in turn.repetition.differences" :key="index">Word difference: {{diff.expected||'(not in the original)'}} → {{diff.recognized||'(missing from the transcript)'}}</p><small>{{turn.repetition.scope}}</small></div><VoiceCoach v-if="turn.audio_id" :key="session.id + turn.id" :session-id="session.id" :turn="turn" :availability="status.voice_coach" /></article></section>
          <div class="report-actions"><button class="button primary" @click="resetPractice">Practise again ↗</button><button id="exportButton" class="button subtle" @click="exportReport">↓ Export feedback</button><button class="button subtle" @click="printReport">Print / Save PDF</button><button class="text-button" @click="showTranscript=!showTranscript">{{showTranscript?'Hide transcript':'View transcript'}}</button></div><section v-if="showTranscript" class="transcript"><article v-for="turn in session.turns" :key="turn.id"><h4>{{turn.question}}</h4><p>{{turn.answer||'Unanswered / transcription incomplete'}}</p></article></section>
        </section>
      </main>
    </template>

    <question-library v-if="view==='library'" :library="library" @choose="chooseExcerpt" />

    <main v-if="view==='history'" class="history-page"><div class="page-heading"><div><p class="eyebrow">EVERY ATTEMPT LEAVES A LITTLE PROGRESS</p><h1>Pick up where you left off.</h1><p>Your latest 30 practice sessions, stored on this computer.</p></div></div><div v-if="!history.length" class="card welcome"><h3>No practice sessions yet.</h3><p>Complete your first answer to start tracking your progress.</p><button class="button primary" @click="view='practice'">Start practising</button></div><button v-for="item in history" :key="item.id" class="card history-item" @click="restore(item.id)"><span class="source-tag">{{item.exam.toUpperCase()}}</span><div><strong>{{item.title}}</strong><small>{{dateLabel(item.created_at)}} · {{item.answered}} answers</small></div><span>{{item.status==='completed'?'View feedback':'Continue practice'}} ↗</span></button></main>

    <footer class="page-footer"><span>POLYSPEAK · SPEAK A LITTLE MORE, EVERY DAY.</span><span>COMP4431 COURSE PROTOTYPE · UNOFFICIAL EXAM PRACTICE</span></footer>
    <div v-if="busy" class="busy-overlay" role="status"><div class="spinner"></div><h3>{{busyLabel}}</h3><p>Please wait. Your answers are saved on this computer.</p></div>
    <div v-if="toastMessage" class="toast" role="status">{{toastMessage}}</div>
    <div v-if="settingsOpen" class="modal-backdrop" @click.self="settingsOpen=false"><section class="settings-modal card" role="dialog" aria-modal="true" aria-label="Service status"><div><h2>Service status</h2><button class="text-button" @click="settingsOpen=false">Close ×</button></div><dl><dt>Conversation model</dt><dd>{{status.chat_model}}</dd><dt>Speech recognition</dt><dd>{{status.asr_model}}</dd><dt>Avatar</dt><dd>{{status.avatar_available?'Nora · Lip-sync model installed':'Model not installed'}}</dd><dt>Pronunciation assessment</dt><dd>{{status.pronunciation_configured?'Azure credentials configured':'Azure setup required; pronunciation scores unavailable'}}</dd><dt>Examiner fine-tuning</dt><dd>The examiner uses the cloud conversation model.</dd><dt>Fine-tuned voice advice</dt><dd>{{status.voice_coach ? status.voice_coach.message : "Voice advice status is unavailable."}}</dd></dl><p>Credentials are stored in the server configuration. Only the configuration status is shown here.</p><button class="button primary" :disabled="testingConnection" @click="testConnection">{{testingConnection?'Testing…':'Test conversation connection'}}</button></section></div>
  </div>
</template>

<script>
import controller from './controller'
export default controller
</script>
