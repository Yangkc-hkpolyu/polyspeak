<template>
  <div class="polyspeak">
    <header class="topbar">
      <button class="brand" :disabled="navigationLocked" @click="view='practice'"><span class="brand-icon">p</span>poly<span>speak</span><i>.</i></button>
      <nav aria-label="主导航"><button :disabled="navigationLocked" :class="{active:view==='practice'}" @click="view='practice'">口语练习</button><button :disabled="navigationLocked" :class="{active:view==='library'}" @click="view='library'">题库与资料 <b>{{library.collection_stats ? library.collection_stats.questions : '…'}}</b></button><button :disabled="navigationLocked" :class="{active:view==='history'}" @click="openHistory">练习记录</button></nav>
      <button class="service-badge" @click="settingsOpen=true"><i :class="{unavailable:!status.api_configured}"></i>{{status.api_configured?'语音与对话已配置':'服务待配置'}}<span>⚙</span></button>
    </header>

    <template v-if="view==='practice'">
      <section class="page-heading"><div><p class="eyebrow">A LITTLE PRACTICE. A CLEARER VOICE.</p><h1>让英语，成为一次自然的交流。</h1><p>和数字人 Nora 开口练习，从每一次回答中找到进步的方向。</p></div><span class="format-chip">IELTS <i></i> TOEFL 2026</span></section>
      <main class="workspace">
        <aside class="setup-panel card">
          <template v-if="!session">
            <p class="eyebrow">YOUR PRACTICE, YOUR PACE</p><h2>今天，练哪一场？</h2>
            <form @submit.prevent="startSession">
              <label>考试类型</label><div class="choice-row"><button type="button" :class="{selected:form.exam==='ielts'}" @click="changeExam('ielts')"><strong>IELTS</strong><small>雅思口语</small></button><button type="button" :class="{selected:form.exam==='toefl'}" @click="changeExam('toefl')"><strong>TOEFL</strong><small>2026 新版</small></button></div>
              <label for="mode">练习方式</label><select id="mode" v-model="form.mode" @change="validateSelection"><option value="mock">模拟考试 · 考后统一反馈</option><option value="coach">互动陪练 · 支持动态追问</option></select>
              <label for="practiceSet">选择题组</label><select id="practiceSet" v-model="form.set_id"><option v-for="item in availableSets" :value="item.id" :key="item.id">{{sourceLabel(item.kind)}} · {{item.title}}</option></select>
              <button type="button" class="text-button bank-entry-link" @click="view='library'">从更多题库中选一道题 →</button>
              <label for="section">练习环节</label><select id="section" v-model="form.section"><option v-for="item in sections" :value="item.value" :key="item.value">{{item.label}}</option></select>
              <div class="protocol-note"><template v-if="selectedSet&&!selectedSet.mock_allowed"><strong>分项陪练 · {{sourceLabel(selectedSet.kind)}}</strong><p>练习所选题干，Nora 可根据回答追问。题目节选不代表完整考试，详情见每题来源。</p></template><template v-else><strong>{{form.exam==='ielts'?'与考官进行分阶段对话':'听后复述 + 预设访谈'}}</strong><p>{{form.exam==='ielts'?'Part 1 日常问答 → Part 2 准备与长答 → Part 3 深入讨论。':'7 条听后复述，随后 4 道访谈，每道访谈 45 秒。模考不增加 AI 追问。'}}</p></template></div>
              <label class="check-label"><input id="quickMode" type="checkbox" v-model="quickMode">课堂快速展示 <small>缩短计时，非完整模考</small></label>
              <label class="check-label"><input id="offlineMode" type="checkbox" v-model="offlineMode">离线流程演示 <small>不生成 AI 评分</small></label>
              <button id="startButton" class="button primary full-width" :disabled="busy">{{busy?'正在准备…':'进入口语练习室'}}<span>↗</span></button>
              <p class="fine-print">模考用录音作答；陪练也可输入文字。<br>所有记录保存在本机。</p>
            </form>
          </template>
          <template v-else>
            <p class="eyebrow">STAY WITH THE CONVERSATION</p><h2>{{session.setup.exam==='ielts'?'IELTS Speaking':'TOEFL Speaking'}}</h2><p class="set-title">{{session.set_title}}</p>
            <div class="summary-tags"><span>{{session.setup.mode==='mock'?'模拟考试':'互动陪练'}}</span><span>{{session.setup.pace==='demo'?'快速展示':'标准计时'}}</span></div>
            <ol class="stage-list"><li v-for="stage in sessionStages" :key="stage.value" :class="{current:currentQuestion&&stage.includes.includes(currentQuestion.stage)}"><i></i><div><strong>{{stage.title}}</strong><small>{{stage.description}}</small></div></li></ol>
            <div class="progress-heading"><span>已完成题目</span><strong>{{session.completed_questions}} / {{session.total_questions}}</strong></div><div class="progress-track"><i :style="{width:progress+'%'}"></i></div>
            <p class="fine-print">{{session.setup.mode==='mock'?'考试期间不提示答案、不即时纠错。结束后再一起复盘。':'Nora 会根据你的回答补充一轮追问，你可以检查转写文字后再提交。'}}</p>
            <button class="button subtle full-width" :disabled="busy||recording||transcribing" @click="resetPractice">选择新练习</button>
            <button v-if="session.turns.length&&!session.report" class="text-button full-width" :disabled="busy||recording||transcribing" @click="finishSession">{{session.report_error?'重试生成反馈':'提前结束并复盘'}}</button>
          </template>
          <div class="side-footer"><span>✦</span><p>好表达，从说出第一句开始。</p></div>
        </aside>

        <section v-if="!session||!session.report" class="room card">
          <div class="room-heading"><div><p class="eyebrow">THE SPEAKING ROOM</p><h2>{{currentQuestion?stageName(currentQuestion.stage):'准备好了，我们就开始。'}}</h2></div><span class="live-tag"><i></i>{{session?'练习进行中':'等待开始'}}</span></div>
          <div v-if="session&&(session.setup.execution==='demo'||session.setup.pace==='demo')" class="notice demo-notice">{{session.setup.execution==='demo'?'离线流程演示：未调用对话模型，不显示模拟分数。 ':''}}{{session.setup.pace==='demo'?'快速展示已缩短计时，不代表完整考试。':''}}</div>
          <div class="room-grid">
            <div class="avatar-column">
              <div class="avatar-stage"><video ref="idleVideo" class="dynamic-avatar" v-show="!videoVisible" src="/speaking-assets/nora-idle.mp4?v=ielts-room-2-calm" poster="/speaking-assets/nora-dynamic.jpg?v=ielts-room-2-calm" aria-label="数字人待机动作" autoplay muted loop playsinline preload="auto"></video><video ref="avatarVideo" class="dynamic-avatar" v-show="videoVisible" playsinline preload="auto" aria-label="数字人提问视频" ></video><span class="avatar-label"><i></i>AI SPEAKING PARTNER</span><div class="nameplate"><h3>Nora <span>在这里，听你表达。</span></h3><p>{{avatarCaption}}</p></div><button v-if="playBlocked" class="play-overlay" @click="resumeVideo">▶<span>点击播放</span></button><div v-if="mediaBusy" class="media-loading"><span>{{mediaLabel}}</span><div class="progress-track"><i :style="{width:mediaProgress+'%'}"></i></div></div></div>
              <div class="avatar-toolbar"><span class="fine-print" v-if="liveConnected">● 实时连接</span><span class="fine-print" v-else-if="liveConnecting">实时连接中…</span><button v-else-if="!liveConnected" class="text-button" @click="connectAvatar">重连数字人</button><button class="text-button" :disabled="busy||recording||transcribing||mediaBusy||!!session" @click="previewNora">▷ 认识 Nora</button><button id="replayButton" class="text-button" :disabled="!canReplay" @click="playQuestion">↺ 重听问题</button></div>
              <div class="timer-card"><div><span>{{timerPhase}}</span><span class="timer-dot" :class="{recording}"></span></div><strong id="countdown">{{timerDisplay}}</strong><p>{{timerHint}}</p></div>
              <div class="small-note"><span>◌</span><p>先表达观点，再给出原因和例子。<br>不必寻找“标准立场”。</p></div>
            </div>

            <div class="dialogue-column">
              <div class="dialogue-heading"><h3>这一问，专注表达。</h3><span v-if="currentQuestion">{{currentQuestion.kind==='followup'?'动态追问':'QUESTION '+currentQuestion.number}}</span></div>
              <div v-if="!session" class="welcome"><span>“</span><h3>给想法一个声音。</h3><p>选择一套练习，让 Nora 带你进入<br>有节奏的英语对话。</p><div><b>01</b> 听问题 <i>→</i> <b>02</b> 开口说 <i>→</i> <b>03</b> 看反馈</div></div>
              <div v-else class="question-area">
                <p v-if="currentQuestion" class="question-source">{{sourceLabel(currentQuestion.source_kind)}}<span v-if="currentQuestion.wording"> · {{wordingLabel(currentQuestion.wording)}}</span><span v-if="currentQuestion.context"> · {{currentQuestion.context}}</span></p>
                <p v-if="currentQuestionSource" class="question-source"><a :href="currentQuestionSource.url" target="_blank" rel="noopener">{{currentQuestionSource.publisher}} · 查看题目来源 ↗</a></p>
                <h3 v-if="currentQuestion" id="questionText" class="question-text">{{currentQuestion.text}}</h3>
                <ul v-if="currentQuestion&&currentQuestion.card.length" class="cue-card"><li v-for="point in currentQuestion.card" :key="point">{{point}}</li></ul>
                <p v-if="currentQuestion&&currentQuestion.task_type==='repeat'" class="fine-print">复述原句在提交后显示。请先听语音，再复述一次。</p>
                <textarea v-if="currentQuestion&&currentQuestion.stage==='part2'" class="notes-input" v-model="notes" placeholder="准备笔记（仅自己可见，不计入回答）" aria-label="Part 2 准备笔记"></textarea>
                <div v-if="session.report_error" class="notice">回答已保存。{{session.report_error}}<button class="text-button" @click="finishSession">重试反馈</button></div>
                <p v-if="session.notices.length" class="fine-print">{{session.notices[session.notices.length-1]}}</p>
              </div>
              <div class="composer"><div class="composer-heading"><span :class="{recording}">{{recording?'● 录音中 · 实时转写':transcribing?'正在转写与保存录音…':composerHint}}</span><span>ENGLISH</span></div><textarea id="answerInput" v-model="draft" :readonly="isMock" :disabled="!currentQuestion||busy||recording||transcribing" :placeholder="isMock?'录音结束后自动保存并进入下一题；模考保留原始转写。':'点击录音，或在这里输入英文回答。'" maxlength="12000"></textarea><div class="composer-actions"><button id="recordButton" class="button record-button" :class="{recording}" :disabled="!canRecord" @click="recording?stopRecording():beginRecording()">{{recording?'■ 结束录音':'◉ 开始录音'}}</button><button v-if="!isMock" id="sendButton" class="button primary" :disabled="!canSend" @click="sendAnswer(false)">提交回答 ↗</button><button v-if="isMock&&mediaFailed&&currentQuestion&&currentQuestion.task_type!=='repeat'&&currentQuestion.phase==='listening'" class="button subtle" @click="questionReady">阅读后开始</button></div><p class="fine-print">{{isMock?'问题播放完毕后自动开始计时与录音。到时自动提交。':'语音转写可以检查后提交；文字作答不提供发音评分。'}}</p><button v-if="currentQuestion" id="skipButton" class="text-button skip-button" :disabled="busy||recording||transcribing" @click="skipQuestion">跳过本题，记为未作答</button></div>
              <details v-if="session&&session.turns.length" class="past-turns"><summary>已提交 {{session.turns.length}} 轮回答</summary><article v-for="turn in session.turns" :key="turn.id"><strong>{{turn.question}}</strong><p>{{turn.answer||'本题未获得文字回答。'}}</p></article></details>
            </div>
          </div>
          <footer class="room-footer"><span>✧ 真实录音 · 数字人语音 · 有依据的反馈</span><span>按你的节奏，一步一步进步。</span></footer>
        </section>

        <section v-else id="reportPanel" class="report card">
          <div class="report-heading"><div><p class="eyebrow">YOUR VOICE, WITH A WAY FORWARD</p><h2>把这次表达，变成下一次进步。</h2><p>{{session.set_title}} · {{session.turns.length}} 轮回答</p></div><span class="completed-badge">✓ 已保存</span></div>
          <div class="report-summary"><span>✦</span><p>{{session.report.summary}}</p></div><p class="notice">{{session.report.scope}}</p><p v-if="session.report.source==='offline_demo'" class="notice">此报告为离线流程说明，没有调用模型，不含模拟分数。</p><p class="fine-print">有效文字回答 {{session.report.coverage.answered}} 轮；跳过 {{session.report.coverage.skipped}} 题。{{session.report.coverage.early_finish?'本次提前结束，反馈仅覆盖已答内容。':''}}</p>
          <div class="dimension-grid"><article v-for="item in session.report.dimensions" :key="item.key"><h3>{{dimensionName[item.key]}}<strong>{{item.score}}<small>/10</small></strong></h3><div class="progress-track"><i :style="{width:item.score*10+'%'}"></i></div><p>{{item.comment}}</p></article></div>
          <layered-report v-if="session.report.layered" :layer="session.report.layered" /><div class="feedback-columns"><section><h3>已经做得不错</h3><ul><li v-for="text in session.report.strengths" :key="text">{{text}}</li></ul></section><section><h3>下一次，试着这样说</h3><ul><li v-for="text in session.report.improvements" :key="text">{{text}}</li></ul></section></div>
          <section v-if="session.report.examples.length" class="feedback-section"><h3>从你的原话开始</h3><article v-for="item in session.report.examples" :key="item.turn_id+item.quote" class="quote-feedback"><blockquote>{{item.quote}}</blockquote><p>{{item.suggestion}}</p></article></section>
          <section class="feedback-section"><h3>接下来，做一个小练习</h3><ol><li v-for="text in session.report.next_steps" :key="text">{{text}}</li></ol></section>
          <section class="feedback-section acoustic"><h3>录音与发音复听</h3><p class="fine-print">低分词是复听线索。ASR 用词差异与发音错误分别呈现。</p><article v-for="turn in session.turns" :key="turn.id"><h4>{{stageName(turn.stage)}} · {{turn.question}}</h4><audio v-if="turn.audio_id" :ref="'audio-'+turn.id" :src="recordingUrl(turn.audio_id)" controls preload="none"></audio><p v-if="turn.pronunciation.status!=='available'" class="fine-print">{{turn.pronunciation.message||'发音未评测。'}}</p><template v-else><p>Azure 逐词准确度均值：{{turn.pronunciation.word_accuracy_mean}} / 100</p><div class="word-feedback"><button v-for="(word,index) in turn.pronunciation.words" :key="index" :class="{low:word.accuracy!==null&&word.accuracy<70}" @click="playWord(turn,word)">{{word.word}} <small>{{word.accuracy}}</small></button></div><p class="fine-print">{{turn.pronunciation.scope}}</p></template><div v-if="turn.repetition" class="repeat-feedback"><p><b>原句</b> {{turn.repetition.target}}</p><p><b>识别</b> {{turn.repetition.recognized}}</p><p v-for="(diff,index) in turn.repetition.differences" :key="index">用词差异：{{diff.expected||'（原句无此词）'}} → {{diff.recognized||'（转写中缺少）'}}</p><small>{{turn.repetition.scope}}</small></div></article></section>
          <div class="report-actions"><button class="button primary" @click="resetPractice">再练一次 ↗</button><button id="exportButton" class="button subtle" @click="exportReport">↓ 导出反馈</button><button class="button subtle" @click="printReport">打印 / 保存 PDF</button><button class="text-button" @click="showTranscript=!showTranscript">{{showTranscript?'收起文字记录':'查看文字记录'}}</button></div><section v-if="showTranscript" class="transcript"><article v-for="turn in session.turns" :key="turn.id"><h4>{{turn.question}}</h4><p>{{turn.answer||'未作答 / 转写未完成'}}</p></article></section>
        </section>
      </main>
    </template>

    <question-library v-if="view==='library'" :library="library" @choose="chooseExcerpt" />

    <main v-if="view==='history'" class="history-page"><div class="page-heading"><div><p class="eyebrow">EVERY ATTEMPT LEAVES A LITTLE PROGRESS</p><h1>回到上一次开口的地方。</h1><p>最近 30 次练习，仅保存在这台电脑。</p></div></div><div v-if="!history.length" class="card welcome"><h3>还没有练习记录。</h3><p>完成第一轮回答，留下一次真实的进步。</p><button class="button primary" @click="view='practice'">开始练习</button></div><button v-for="item in history" :key="item.id" class="card history-item" @click="restore(item.id)"><span class="source-tag">{{item.exam.toUpperCase()}}</span><div><strong>{{item.title}}</strong><small>{{dateLabel(item.created_at)}} · {{item.answered}} 轮回答</small></div><span>{{item.status==='completed'?'查看反馈':'继续练习'}} ↗</span></button></main>

    <footer class="page-footer"><span>POLYSPEAK · SPEAK A LITTLE MORE, EVERY DAY.</span><span>COMP4431 COURSE PROTOTYPE · 非官方考试服务</span></footer>
    <div v-if="busy" class="busy-overlay" role="status"><div class="spinner"></div><h3>{{busyLabel}}</h3><p>你的回答会保存在本机，请稍候。</p></div>
    <div v-if="toastMessage" class="toast" role="status">{{toastMessage}}</div>
    <div v-if="settingsOpen" class="modal-backdrop" @click.self="settingsOpen=false"><section class="settings-modal card" role="dialog" aria-modal="true" aria-label="服务状态"><div><h2>服务状态</h2><button class="text-button" @click="settingsOpen=false">关闭 ×</button></div><dl><dt>对话模型</dt><dd>{{status.chat_model}}</dd><dt>语音识别</dt><dd>{{status.asr_model}}</dd><dt>数字人</dt><dd>{{status.avatar_available?'Nora · 口型模型已安装':'模型待安装'}}</dd><dt>发音评测</dt><dd>{{status.pronunciation_configured?'Azure 凭据已配置':'Azure 待配置，不显示发音分'}}</dd><dt>文本微调</dt><dd>尚未训练，当前使用基础模型</dd></dl><p>密钥保存在 E 盘副本的服务器配置中。这里仅显示配置状态。</p><button class="button primary" :disabled="testingConnection" @click="testConnection">{{testingConnection?'测试中…':'测试对话连接'}}</button></section></div>
  </div>
</template>

<script>
import controller from './controller'
export default controller
</script>
