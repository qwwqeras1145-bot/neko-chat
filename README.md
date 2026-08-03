# 🐱 喵酱 Chat — 猫娘 AI 聊天助手

> 纯 AI 聊天应用，手机端 + 电脑端，**互相独立**，无需互通。
> 首次填写 API Key 即可开始聊天，内置猫娘人设提示词（可自由修改）。

## ✨ 功能

- 🐱 猫娘 AI 人设（内置提示词，可在设置里随意改写）
- 💬 流式输出（打字机效果），多轮上下文对话
- 📱 **手机端**：PWA 网页应用，可添加到主屏幕，像原生 APP 一样使用
- 💻 **电脑端**：Python 本地服务 + 网页界面，双击启动
- 🔑 支持 DeepSeek / OpenAI / Kimi / 通义 / GLM / 硅基流动 等 OpenAI 兼容 API
- 🎨 粉色猫娘主题，可爱猫爪元素

## 🚀 快速开始

### 📱 手机端

1. 打开页面（部署方式见下）
2. 点右上角 ⚙️ 填写 **API Key**（服务商可选 DeepSeek / Kimi / OpenAI 等）
3. 保存后即可开聊
4. 浏览器菜单 → **"添加到主屏幕"**，就像安装了一个 APP

> 手机端是浏览器直连 API，需要服务商开放 CORS（DeepSeek、OpenAI、硅基流动等均支持）。
> 若提示跨域错误，可换用支持浏览器直连的服务商，或使用电脑端。

**手机端部署方式（任选其一）：**

| 方式 | 说明 |
|---|---|
| GitHub Pages | 把 `mobile/` 部署到 Pages，手机浏览器打开网址 |
| 本地服务器 | 手机和电脑连同一 WiFi，电脑运行 `desktop/server.py`，手机访问 `http://<电脑IP>:8321/mobile` 需自行托管 |
| 静态托管 | 任意静态托管（Netlify / Vercel / 对象存储）上传 `mobile/` 即可 |

### 💻 电脑端

```bash
cd desktop
python server.py        # 或双击 run.bat
```

1. 浏览器自动/手动打开 `http://127.0.0.1:8321`
2. 首次使用点右上角 ⚙️ 填 **API Key** → 保存
3. 开聊！配置保存在本地 `config.json`

**Windows 免 Python 版**：下载 Release 里的 `neko-chat-windows.exe` 双击即用。

## ⚙️ 配置说明

| 项目 | 说明 |
|---|---|
| API Base URL | OpenAI 兼容接口地址，例如 `https://api.deepseek.com/v1` |
| API Key | 各服务商后台申请的密钥 |
| 模型 | 例如 `deepseek-chat` / `gpt-4o-mini` / `moonshot-v1-8k` |
| 人设提示词 | 默认猫娘「喵酱」人设，可随意改写 |
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
- **手机端**：纯 HTML/CSS/JS + PWA（localStorage 存配置，前端直连 OpenAI 兼容 API）
- **构建**：GitHub Actions + PyInstaller 自动打包 Windows exe

## 📦 打包（开发者）

```bash
pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --console --name neko-chat-windows desktop/server.py
```

## 📄 License

MIT
