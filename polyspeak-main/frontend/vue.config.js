const { defineConfig } = require('@vue/cli-service')
const fs = require('fs')
const path = require('path')
const TerserPlugin = require('terser-webpack-plugin')

// Read centralized port configuration
let ports = { frontend: 8080, backend: 5002, auth: 4001, digitalHuman: 8010, stt: 8765, tts: 9880, maintenance: 9080 }
try {
  const portsConfig = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../config/ports.json'), 'utf-8'))
  const activeEnv = portsConfig.active || 'development'
  ports = portsConfig[activeEnv] || ports
} catch (e) {
  console.warn('[vue.config.js] Failed to load ports.json, using defaults:', e.message)
}

// Dev HTTPS: only if self-signed certs exist (for LAN testing)
const sslCert = path.resolve(__dirname, '../backend/ssl/cert.pem')
const sslKey = path.resolve(__dirname, '../backend/ssl/key.pem')
const hasLocalSsl = fs.existsSync(sslCert) && fs.existsSync(sslKey)
const httpsConfig = hasLocalSsl
  ? { key: fs.readFileSync(sslKey), cert: fs.readFileSync(sslCert) }
  : false

const speakingOnly = process.env.SPEAKING_ONLY === 'true'
const isGatewayMode =
  process.env.VUE_APP_DEPLOY_MODE === 'gateway' ||
  (process.env.VUE_APP_DEPLOY_MODE !== 'direct' &&
    process.env.VUE_APP_API_BASE !== undefined)

function isLegacyProductRoute(requestPath = '') {
  return (
    /^\/adminlogin\/?$/.test(requestPath) ||
    /^\/admin(\/.*)?$/.test(requestPath) ||
    /^\/wie-admin(\/.*)?$/.test(requestPath) ||
    /^\/wie-student(\/.*)?$/.test(requestPath) ||
    /^\/login\/?$/.test(requestPath) ||
    /^\/userlogin\/?$/.test(requestPath) ||
    /^\/verify-email\/?$/.test(requestPath) ||
    /^\/reset-password\/?$/.test(requestPath) ||
    /^\/email-verification-pending\/?$/.test(requestPath) ||
    /^\/profile\/?$/.test(requestPath) ||
    /^\/recruitment(\/.*)?$/.test(requestPath) ||
    /^\/PositionRecommendation\/?$/.test(requestPath) ||
    /^\/MaterialRecommendation\/?$/.test(requestPath) ||
    /^\/CVRevise\/?$/.test(requestPath) ||
    /^\/InterviewSimulation\/?$/.test(requestPath) ||
    /^\/booking\/?$/.test(requestPath) ||
    /^\/interview\/history(\/.*)?$/.test(requestPath) ||
    /^\/dev\/evaluation-preview\/?$/.test(requestPath)
  )
}

module.exports = defineConfig({
  outputDir: speakingOnly ? 'dist-speaking' : 'dist',
  pages: speakingOnly ? { index: { entry: 'src/speaking-main.js', template: 'public/speaking.html', filename: 'index.html', title: 'PolySpeak · IELTS & TOEFL' } } : {
    index: {
      entry: 'src/main.js',
      template: 'public/index.html',
      filename: 'index.html'
    },
    admin: {
      entry: 'src/admin-main.js',
      template: 'public/admin.html',
      filename: 'admin.html'
    }
  },
  // 所有环境均不生成 source map，防止浏览器还原源码
  productionSourceMap: false,
  devServer: {
    host: speakingOnly ? '127.0.0.1' : '0.0.0.0',
    port: speakingOnly ? 8088 : ports.frontend,
    https: speakingOnly ? false : httpsConfig,
    allowedHosts: 'all',
    // 与 frontend/serve.json、nginx 一致：管理端须返回 admin.html，否则会落到用户端 SPA。
    historyApiFallback: {
      rewrites: [
        { from: /^\/wie\/wie-admin/, to: '/admin.html' },
        { from: /^\/wie\/recruitment\/admin/, to: '/index.html' },
        { from: /^\/wie\//, to: '/index.html' },
        { from: /^\/polyinterview\/adminlogin/, to: '/admin.html' },
        { from: /^\/polyinterview\/admin/, to: '/admin.html' },
        { from: /^\/polyinterview\//, to: '/index.html' },
        { from: /./, to: '/index.html' }
      ]
    },
    setupMiddlewares(middlewares, devServer) {
      devServer.app.use((req, res, next) => {
        if (isLegacyProductRoute(req.path)) {
          res.status(404).send('Legacy product routes are disabled. Use /wie/* or /polyinterview/*.')
          return
        }
        if (/^\/wie\/adminlogin\/?$/.test(req.path)) {
          res.redirect(302, '/wie/wie-admin/login')
          return
        }
        if (/^\/wie\/admin\/?$/.test(req.path)) {
          res.redirect(302, '/wie/wie-admin')
          return
        }
        if (/^\/wie\/admin\//.test(req.path)) {
          res.redirect(302, req.originalUrl.replace(/^\/wie\/admin/, '/wie/wie-admin'))
          return
        }
        if (/^\/wie\/wie-admin(\/.*)?$/.test(req.path)) {
          req.url = '/admin.html'
        } else if (/^\/polyinterview\/adminlogin\/?$/.test(req.path) || /^\/polyinterview\/admin(\/.*)?$/.test(req.path)) {
          req.url = '/admin.html'
        }
        next()
      })
      return middlewares
    },
    proxy: speakingOnly ? {
      '/api': { target: 'http://127.0.0.1:8008', changeOrigin: false },
      '/media': { target: 'http://127.0.0.1:8008', changeOrigin: false },
      '/speaking-assets': { target: 'http://127.0.0.1:8008', changeOrigin: false }
    } : {
      '/api': {
        target: `https://localhost:${ports.backend}`,
        secure: false,
        changeOrigin: true
      },
      '/interview': {
        target: `https://localhost:${ports.backend}`,
        secure: false,
        changeOrigin: true,
        bypass(req) {
          if ((req.path || req.url || '').startsWith('/interview/')) return null
          return req.url
        }
      }
    },
    client: {
      webSocketURL: 'auto://0.0.0.0:0/ws',
      overlay: { errors: true, warnings: false }
    },
    onListening: function (devServer) {
      const wss = devServer.webSocketServer && devServer.webSocketServer.implementation
      if (wss) {
        wss.on('connection', (ws) => {
          ws.on('error', (err) => {
            console.warn('[dev-server] WebSocket client error (ignored):', err.message)
          })
        })
      }
    }
  },
  // ——— 代码混淆：使用 Webpack 内置 TerserPlugin 压缩 + 变量名混淆 ———
  configureWebpack: {
    // 关闭 devtool，所有环境都不暴露源码映射
    devtool: false,
    optimization: {
      // 所有环境均启用压缩
      minimize: true,
      minimizer: [
        new TerserPlugin({
          terserOptions: {
            // 压缩选项
            compress: {
              drop_debugger: true,   // 移除 debugger 语句
              passes: 2              // 多轮压缩，进一步精简
            },
            // 变量名混淆（核心）
            mangle: {
              toplevel: true,        // 混淆顶层变量名
              properties: {
                regex: /^_/          // 仅混淆下划线开头的属性名（安全策略）
              }
            },
            // 输出格式
            output: {
              comments: false,       // 移除所有注释
              beautify: false,       // 不格式化，保持压缩
              ascii_only: true       // 转义非 ASCII 字符
            }
          },
          extractComments: false     // 不提取注释到单独文件
        })
      ]
    }
  },
  chainWebpack: config => {
    if (speakingOnly) config.plugins.delete('copy')
    if (isGatewayMode) {
      config.plugin('gateway-mode-notice').use(
        class {
          apply (compiler) {
            let printed = false
            compiler.hooks.done.tap('GatewayModeNotice', () => {
              if (printed) return
              printed = true
              setTimeout(() => {
                console.log('\n  [API gateway mode] Use unified reverse proxy URL (e.g. https://localhost)\n')
              }, 50)
            })
          }
        }
      )
    }
    config.plugin('define').tap(args => {
      const processEnv = args[0]['process.env']
      processEnv.VUE_APP_PORT_FRONTEND = JSON.stringify(ports.frontend)
      processEnv.VUE_APP_PORT_BACKEND = JSON.stringify(ports.backend)
      processEnv.VUE_APP_PORT_AUTH = JSON.stringify(ports.auth)
      processEnv.VUE_APP_PORT_DIGITAL_HUMAN = JSON.stringify(ports.digitalHuman)
      processEnv.VUE_APP_PORT_STT = JSON.stringify(ports.stt)
      processEnv.VUE_APP_PORT_TTS = JSON.stringify(ports.tts)
      processEnv.VUE_APP_PORT_MAINTENANCE = JSON.stringify(ports.maintenance)
      return args
    })
  },
  transpileDependencies: true
})

