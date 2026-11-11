# 云端小组演示部署

此配置部署当前 PolySpeak 口语平台的前端、FastAPI、SQLite、录音和本地口型模型。它不启动原项目的招聘、认证和 PostgreSQL 服务。本机仍可使用 `start-speaking.bat`，不需要 Docker。

## 当前状态

此目录仍是部署骨架，尚未发布到服务器或开通付费资源。数字人已改为 PolyInterview 的 LiveTalking＋WebRTC，语音输入为 WebSocket 实时识别。目前只验证了本机连接；公网部署还需要补齐 STUN/TURN 和媒体网络配置，不能只启动下方 HTTP 代理便认为实时视频已部署完成。当前本机最多两个数字人连接，未进行多人并发测试。详见 `docs/SPEAKING_REALTIME.md`。

## 服务器准备

使用带 NVIDIA GPU 的 Linux 服务器，安装兼容的驱动、Docker Compose 和 NVIDIA Container Toolkit。准备指向服务器的域名，并开放 TCP 80/443。浏览器录音需要可信 HTTPS；Caddy 为正确配置的域名申请证书。

1. 上传最新 `COMP4431_PolySpeak_source.zip`，解压进入 `COMP4431_PolySpeak/`。
2. 将 `COMP4431_PolySpeak_model_assets.zip` 解压到同一目录，提供权重和 `speaking-models/avatars/nora/` 动态素材。它们不包含在源码包。
3. 如需本地打开官方 PDF，上传 `speaking-resources/official/`；不上传时仍可使用官方来源链接。
4. 复制 `deploy/speaking/cloud.env.example` 为 `deploy/speaking/cloud.env`，填入域名、自己的 API Key 和演示密码哈希。不要上传原 `backend/.env` 或真实用户录音。
5. 运行下方命令生成密码哈希，输入供组员使用的密码，将输出保存在单引号内：

```sh
docker run --rm -it caddy:2 caddy hash-password
```

## 启动

在解压后的项目根目录执行：

```sh
docker compose --env-file deploy/speaking/cloud.env -f deploy/speaking/compose.yaml config --quiet
docker compose --env-file deploy/speaking/cloud.env -f deploy/speaking/compose.yaml up -d --build
docker compose --env-file deploy/speaking/cloud.env -f deploy/speaking/compose.yaml ps
```

打开配置的 `https://域名`，使用 `team`（或自定用户名）和演示密码登录。检查题库、数字人播放、麦克风录音和反馈后才算部署完成。启动会检查 CUDA 和权重，缺失时直接报错，不悄悄回退成缓慢的 CPU 渲染。

镜像默认使用 PyTorch 2.6.0 / CUDA 12.6 的官方 wheel；需要依目标 GPU/驱动验证，尚未在云端运行该镜像。不要把本机 Windows `.venv` 上传到 Linux。

## 数据与访问

后端端口只在容器网络内开放；Caddy 提供 HTTPS 和演示密码。当前所有获准进入的组员共享练习记录，未实现个人账号隔离，因此这是受限的小组演示配置。SQLite、录音、视频缓存位于持久化 `runtime` 卷，重建容器不会自动清空；备份应同时包含该卷与单独保管的服务器配置。不要用 `down -v` 操作需要保留的记录。

## 官方依据

- [Docker Compose GPU 支持](https://docs.docker.com/compose/how-tos/gpu-support/)
- [PyTorch 历史版本安装](https://docs.pytorch.org/get-started/previous-versions/)
- [Caddy 自动 HTTPS](https://caddyserver.com/docs/automatic-https)
- [Caddy 访问密码](https://caddyserver.com/docs/caddyfile/directives/basic_auth)
