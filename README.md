# PolySpeak — IELTS / TOEFL 口语练习

面向课程小组的口语模考与互动陪练平台。支持语音输入、数字人语音回答、动态追问、逐题评价和报告导出。

网页界面、题库标签、服务提示和 AI 反馈报告统一使用英文；原始回答与引用保持原样。

- 数字人：人物视频帧 + 本地 Wav2Lip 口型模型，LiveTalking + WebRTC 持续传输音视频。
- 对话与反馈：Qwen 文本 API；语音识别、语音合成为 Qwen 实时 API。
- 模式：IELTS 模考、TOEFL 2026 模考，以及动态追问陪练。
- 报告：逐题特征、语言维度、原话修订、录音复听、JSON 导出和打印。

这是公开仓库，可以直接分享链接、克隆代码或下载源码，无需添加协作者。API Key、录音、历史记录和本机环境不在 Git 中。
模型和人物素材可从 [v3.0.0 Release](https://github.com/Yangkc-hkpolyu/polyspeak/releases/tag/v3.0.0) 直接下载。

## 第一次启动（Windows）

准备 Python 3.11 或 3.12、Git 和网络连接。网页已构建，不必安装 Node；本机启动不需要 Docker。

```powershell
git clone https://github.com/Yangkc-hkpolyu/polyspeak.git
cd polyspeak
python -m venv .venv
.\.venv\Scripts\python.exe -s -m pip install -r requirements-speaking.txt
Copy-Item speaking.env.example speaking.env
```

打开 `speaking.env`，填写自己的 `DASHSCOPE_API_KEY`。其余模型配置可先用默认值。
从上面的 Release 下载 `COMP4431_PolySpeak_model_assets.zip`。不用手动解压，执行下面的命令并替换 ZIP 的实际路径：

```powershell
.\.venv\Scripts\python.exe -s scripts/download_speaking_model.py --archive "E:\Downloads\COMP4431_PolySpeak_model_assets.zip"
.\start-speaking.bat
```

安装程序校验 SHA-256，再把模型和人物帧放入正确目录。若已安装 GitHub CLI 并通过 `gh auth login` 登录，可不带 `--archive` 运行安装程序，由它下载 Release；浏览器手动下载无需登录。

浏览器打开 http://127.0.0.1:8008/，允许麦克风权限。首次数字人连接需要加载和预热口型模型。
建议使用 NVIDIA GPU；纯 CPU 能否达到实时速度取决于硬件。根据本机驱动安装相应的 PyTorch CUDA 构建。

## macOS

```sh
git clone https://github.com/Yangkc-hkpolyu/polyspeak.git
cd polyspeak
python3.11 -m venv .venv
.venv/bin/python -s -m pip install -r requirements-speaking.txt
cp speaking.env.example speaking.env
# 编辑 speaking.env 填写 API Key，并从 Release 下载模型素材 ZIP
.venv/bin/python -s scripts/download_speaking_model.py --archive ~/Downloads/COMP4431_PolySpeak_model_assets.zip
sh start-speaking.sh
```

提供 MPS/CPU 选择逻辑，但 Mac 真机的完整运行与速度尚未验证。已验证环境是 Windows + NVIDIA GPU。

## 练习与资料

选择 IELTS 或 TOEFL、模考或陪练，再选择题组。模考按题目自动录音和提交；陪练可以检查转写或直接输入文字。
“课堂快速展示”使用缩短计时，不能视为正式考试时长。AI 反馈是练习建议，不是官方考试成绩。

题库含 282 道带来源标记的机构题库或回忆题，另有 6 套原创模拟题，见 [题库说明](docs/SPEAKING_QUESTION_BANK.md)。
官方资料 PDF 不在 Git 中，需要时运行：

```powershell
.\.venv\Scripts\python.exe -s scripts/download_speaking_sources.py
```

## 能力和限制

- 当前文本模型尚未微调，默认调用 `qwen-plus-latest`。
- Azure 发音评测可选。配置 `AZURE_SPEECH_KEY` 和 `AZURE_REGION` 后才能取得实际音频评测；未配置时显示未评估。
- 不采集考生视频，目光、表情、姿态等指标保持未评估。
- 实时视频已验证本机连接。公网部署仍需 STUN/TURN、HTTPS 和媒体网络配置；`deploy/speaking/` 是未验证的部署骨架。
- 语音与文本 API 会使用填写该 Key 的账号额度。

## 开发与测试

前端在 `frontend/src/speaking/`，后端在 `backend/speaking/`。前端修改后重建：

```sh
cd frontend
npm ci
npm run build
```

从仓库根目录运行协议检查：

```powershell
.\.venv\Scripts\python.exe -s -m pytest speaking-tests -q
```

`port_speaking_realtime.py`、`prepare_speaking_avatar.py` 和 `prepare_exam_room.py` 是维护者重建素材的工具，需要原项目文件；使用 Release 素材运行本平台不需要执行它们。

架构和移植范围见 [实时交互说明](docs/SPEAKING_REALTIME.md)，既有验证见 [测试记录](docs/SPEAKING_TESTING.md)。
仓库保留已构建网页；没有复制原面试平台的招聘、认证和管理系统。

## 来源与课程提交

本项目基于用户提供的 PolyInterview 代码及 LiveTalking/Wav2Lip 方案，保留第三方来源与许可。人物素材、权重和第三方代码各自适用原有条款，见 [来源说明](THIRD_PARTY_SPEAKING.md)。

提交前请填写组员信息，并按课程要求准备 PPT、演示和代码包：

| Student ID | English Name | Contribution |
|---|---|---|
| 待填写 | 待填写 | 待填写 |
| 待填写 | 待填写 | 待填写 |
