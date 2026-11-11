<template>
  <div class="live2d-stage" role="img" aria-label="Live2D speaking partner Anya" style="background: #d6c2a1 url('/speaking-assets/live2d/forger-inspired-room.png') center / cover no-repeat">
    <canvas ref="canvas" class="live2d-canvas" aria-hidden="true"></canvas>
    <div v-if="status === 'loading'" class="live2d-status" role="status">Loading speaking partner…</div>
    <div v-else-if="status === 'error'" class="live2d-status live2d-error" role="status">Could not load the avatar. Check the model files and reload.</div>
  </div>
</template>

<script>
const DEFAULT_CORE_URL = '/speaking-assets/live2d/live2dcubismcore.min.js'
const DEFAULT_MODEL_URL = '/speaking-assets/live2d/ANIYA/ANIYA.model3.json'

// The Core is a separate Live2D runtime, shared by all mounted avatar stages.
let corePromise = null
function ensureCubismCore(url) {
  if (window.Live2DCubismCore) return Promise.resolve()
  if (corePromise) return corePromise
  corePromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = url
    script.async = true
    script.onload = () => {
      if (window.Live2DCubismCore) resolve()
      else reject(new Error('Live2D Core did not load correctly.'))
    }
    script.onerror = () => reject(new Error('Unable to load Live2D Core.'))
    document.head.appendChild(script)
  }).catch(error => { corePromise = null; throw error })
  return corePromise
}

export default {
  name: 'Live2DAvatar',
  props: {
    mouthOpen: { type: Number, default: 0 },
    modelUrl: { type: String, default: DEFAULT_MODEL_URL },
    coreUrl: { type: String, default: DEFAULT_CORE_URL },
  },
  data: () => ({ status: 'loading' }),
  mounted() {
    this._stageDestroyed = false
    this._mouthValue = 0
    this.initStage()
  },
  beforeDestroy() {
    this._stageDestroyed = true
    this.destroyStage()
  },
  methods: {
    async initStage() {
      try {
        // Load Core first: the Cubism 4 adapter expects its global runtime.
        await ensureCubismCore(this.coreUrl)
        if (this._stageDestroyed) return
        const PIXI = await import('pixi.js')
        window.PIXI = PIXI
        const { Live2DModel } = await import('pixi-live2d-display/cubism4')
        if (this._stageDestroyed) return
        Live2DModel.registerTicker(PIXI.Ticker)

        this._pixi = new PIXI.Application({
          view: this.$refs.canvas,
          backgroundAlpha: 0,
          antialias: true,
          autoDensity: true,
          resolution: Math.min(window.devicePixelRatio || 1, 2),
        })
        const model = await Live2DModel.from(this.modelUrl, { autoInteract: false })
        if (this._stageDestroyed) {
          model.destroy({ children: true, texture: true, baseTexture: true })
          return
        }
        this._model = model
        const internal = model.internalModel
        const core = internal?.coreModel
        const parameterIds = core?.getModel()?.parameters?.ids
        const mouthIndex = parameterIds ? Array.from(parameterIds).indexOf('ParamMouthOpenY') : -1
        if (mouthIndex < 0 || !core?.setParameterValueByIndex) throw new Error('The model does not support mouth movement.')
        model.anchor.set(0.5, 0)
        this._pixi.stage.addChild(model)
        this._updateMouth = () => {
          const value = Number(this.mouthOpen)
          const target = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0
          // A quicker opening and slower release make amplitude changes less abrupt.
          this._mouthValue += (target - this._mouthValue) * (target > this._mouthValue ? 0.55 : 0.25)
          core.setParameterValueByIndex(mouthIndex, this._mouthValue)
        }
        // Apply after idle motion and physics so they cannot overwrite speech.
        internal.on('beforeModelUpdate', this._updateMouth)
        this._resizeStage = () => this.resizeStage()
        if (typeof ResizeObserver !== 'undefined') {
          this._resizeObserver = new ResizeObserver(this._resizeStage)
          this._resizeObserver.observe(this.$el)
        } else window.addEventListener('resize', this._resizeStage)
        this.resizeStage()
        this.status = 'ready'
        this.$emit('ready')
      } catch (error) {
        if (this._stageDestroyed) return
        this.destroyStage()
        this.status = 'error'
        this.$emit('error', error)
      }
    },
    resizeStage() {
      if (!this._pixi || !this._model || this._stageDestroyed) return
      const width = this.$el.clientWidth
      const height = this.$el.clientHeight
      if (!width || !height) return
      this._pixi.renderer.resize(width, height)
      const naturalWidth = this._model.internalModel.width
      const naturalHeight = this._model.internalModel.height
      if (!naturalWidth || !naturalHeight) return
      // Frame Anya's face and upper body without hiding her mouth behind the caption.
      const scale = Math.max(width / naturalWidth, height / naturalHeight) * 0.95
      this._model.scale.set(scale)
      this._model.position.set(width / 2, 0)
    },
    destroyStage() {
      if (this._resizeObserver) this._resizeObserver.disconnect()
      else if (this._resizeStage) window.removeEventListener('resize', this._resizeStage)
      this._resizeObserver = null
      if (this._model && this._updateMouth) this._model.internalModel.off('beforeModelUpdate', this._updateMouth)
      this._updateMouth = null
      if (this._pixi) this._pixi.destroy(false, { children: true, texture: true, baseTexture: true })
      this._pixi = null
      this._model = null
    },
  },
}
</script>

<style scoped>
.live2d-stage {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: transparent;
}
.live2d-canvas { display: block; width: 100%; height: 100%; }
.live2d-status {
  position: absolute;
  inset: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 24px;
  color: #365a48;
  background: #edf5ed;
  font-size: 14px;
  text-align: center;
}
.live2d-error { color: #85463c; background: #f9f2ef; }
</style>
