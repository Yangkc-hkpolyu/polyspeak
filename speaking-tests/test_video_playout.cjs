// Deterministic display-clock tests: never render early or accumulate a backlog.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const path = require('node:path')
let next = 0, created = 0
const captures = new Map(), animations = new Map(), draws = []
const video = {
  videoWidth: 1276, videoHeight: 720,
  requestVideoFrameCallback(fn) { captures.set(++next, fn); return next },
  cancelVideoFrameCallback(id) { captures.delete(id) },
}
const canvas = { width: 0, height: 0, style: {}, getContext: () => ({ drawImage: frame => draws.push(frame) }) }
const context = vm.createContext({
  document: { createElement() { created++; return { width: 0, height: 0, getContext: () => ({ drawImage() {} }) } } },
  requestAnimationFrame(fn) { animations.set(++next, fn); return next },
  cancelAnimationFrame(id) { animations.delete(id) },
})
const source = fs.readFileSync(path.join(__dirname, '../frontend/src/speaking/video-playout.js'), 'utf8').replace('export class', 'class')
const Playout = vm.runInContext(source + '\nVideoPlayout', context)
function capture(time) { const [id, fn] = captures.entries().next().value; captures.delete(id); fn(time, { expectedDisplayTime: time, rtpTimestamp: time }) }
function present(time) { const [id, fn] = animations.entries().next().value; animations.delete(id); fn(time) }
async function run() {
  const shown = [], player = new Playout(video, canvas, 180, (now, m) => shown.push([now, m.rtpTimestamp]))
  const ready = player.start()
  assert.equal(player.start(), ready, 'Repeated play must preserve the same buffer')
  capture(100); capture(140)
  present(279); assert.equal(draws.length, 0, 'Do not reveal a frame before its due time')
  present(280); assert.equal(await ready, true)
  assert.deepEqual(shown[0], [280, 100])
  assert.equal(canvas.width, 1276); assert.equal(canvas.height, 720)
  assert.equal(canvas.style.visibility, 'visible')
  for (let time = 180; time < 2000; time += 40) capture(time)
  assert(player.queue.length <= player.limit)
  assert(created <= player.limit, 'Keep memory bounded during a stalled display')
  present(2200)
  assert.deepEqual(shown.at(-1), [2200, 1980], 'Discard overdue frames instead of replaying a growing backlog')
  assert.equal(player.queue.length, 0)
  const staleCapture = captures.values().next().value
  const stalePresent = animations.values().next().value
  player.stop()
  assert.equal(captures.size, 0); assert.equal(animations.size, 0)
  assert.equal(canvas.style.visibility, 'hidden')
  const restarted = player.start()
  staleCapture(3000, { expectedDisplayTime: 3000 }); stalePresent(4000)
  assert.equal(player.queue.length, 0, 'Old connection callbacks must not enter the new stream')
  capture(3000); present(3180); assert.equal(await restarted, true)
  player.stop()
  const pending = player.start(); player.stop(); assert.equal(await pending, false)
  assert.equal(await new Playout({}, canvas).start(), false, 'Unsupported browsers retain native playback')
  assert.equal(await new Playout(video, canvas, 0).start(), false)
  console.log('Video playout timing, queue bounds, full resolution and lifecycle tests passed')
}
run().catch(error => { console.error(error); process.exitCode = 1 })
