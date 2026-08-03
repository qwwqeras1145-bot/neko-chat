# 🐱 喵酱 Chat — 猫娘 AI 聊天助手

> 纯 AI 聊天应用：**手机 APP（Android）+ 在线网站（PWA）+ 电脑端（网页）**，三端互相独立。
> 首次填写 API Key 即可开始聊天，内置猫娘人设提示词（可自由修改）。

## ✨ 功能

- 🐱 猫娘 AI 人设（内置提示词，可在设置里随意改写）
- 💬 流式输出（打字机效果），多轮上下文对话
- 🧠 **深度思考**（推理模型，先思考后回答，思考过程可展开）
- 🔉 **语音朗读**（每条回复可点 🔊，也可开启自动朗读）
- 🎤 **语音输入**（点麦克风说话自动转文字，浏览器需支持 Web Speech）
- 💬 **上下文记忆长度**可调（0~30 轮）
- 🔑 支持 DeepSeek / OpenAI / Kimi / 通义 / GLM / 硅基流动 + **自定义 API**
- 🎨 粉色猫娘主题：猫耳标题、漂浮猫爪背景、渐变气泡、SVG 猫娘头像

## 📲 三种使用方式

| 端 | 形式 | 入口 |
|---|---|---|
| 📱 手机 APP | Android APK（WebView 打包，离线可用） | GitHub Release 下载 `neko-chat.apk` 安装 |
| 🌐 在线网站 | PWA（可添加到主屏幕） | https://qwwqeras1145-bot.github.io/neko-chat/ |
| 💻 电脑端 | Python 本地服务 + 网页 / Windows exe | `desktop/server.py` 或 Release 下载 exe |

> 三端互相独立，各自保存配置，互不干扰。

## 🚀 快速开始

### 📱 手机 APP（Android）

1. 在 GitHub Release 下载 `neko-chat.apk`
2. 手机安装（首次安装需允许"未知来源"）
3. 打开 APP → 右上角 ⚙️ 填 API Key → 开聊
4. 配置保存在手机本地

> 语音朗读可用（系统 TTS）；语音输入依赖 Web Speech，个别安卓 WebView 可能不支持，请手动打字。

### 🌐 在线网站（PWA）

1. 浏览器打开 https://qwwqeras1145-bot.github.io/neko-chat/
2. ⚙️ 填 API Key → 保存开聊
3. 浏览器菜单 → **添加到主屏幕**，像 APP 一样用

> 浏览器直连 API 需服务商开放 CORS（DeepSeek、OpenAI、硅基流动等均支持）。

### 💻 电脑端

```bash
cd desktop
python server.py        # 或双击 run.bat
```

1. 打开 `http://127.0.0.1:8321`
2. 首次使用 ⚙️ 填 API Key → 保存
3. 开聊！配置保存在本地 `config.json`

**Windows 免 Python 版**：下载 Release 的 `neko-chat-windows.exe` 双击即用。

## ⚙️ 配置说明

| 项目 | 说明 |
|---|---|
| API 服务商 | 一键切换 DeepSeek / OpenAI / Kimi / 通义 / GLM / 硅基流动 |
| 自定义 API | 任意 OpenAI 兼容 base_url + model |
| API Key | 各服务商后台申请的密钥 |
| 深度思考 | 自动切换推理模型（如 deepseek-reasoner / o3-mini） |
| 上下文记忆 | 0~30 轮，0 = 每句独立 |
| 语音朗读 | 自动朗读 AI 回复（中文 TTS） |
| 人设提示词 | 默认猫娘「喵酱」，可随意改写 |
| 温度 | 0~1.5，越低越严谨，越高越活泼 |

## 🐱 默认人设（喵酱）

```
你是「喵酱」，一只来自猫星的猫娘 AI 助理…
温柔黏人、有点小傲娇、喜欢小鱼干 🐟
认真回答 + 可爱卖萌，拒绝违规内容…
```
完整提示词见代码内 `DEFAULT_PROMPT`，可在设置中修改。

## 🛠️ 技术栈

- **电脑端**：Python 标准库（http.server 流式代理 + 内嵌网页 UI），零第三方依赖
- **在线网站/手机 APP**：HTML/CSS/JS + PWA（localStorage 存配置，直连 OpenAI 兼容 API）
- **Android APP**：原生 WebView 加载离线页面（`android/` 目录，Gradle 构建 APK）
- **构建**：GitHub Actions 自动打包 Windows exe + Android APK

## 📦 本地打包（开发者）

```bash
# 电脑端
pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --console --name neko-chat-windows desktop/server.py

# Android APP
cp mobile/index.html android/app/src/main/assets/index.html
cd android && gradle assembleDebug
```

## 📄 License

MIT
