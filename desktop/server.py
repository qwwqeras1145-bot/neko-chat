# -*- coding: utf-8 -*-
"""
喵酱 Chat - 电脑端 v0.3.0（美化版）
纯 AI 聊天助手（猫娘人设），标准库实现，无第三方依赖。
功能：上下文长度 / 语音朗读 / 语音输入 / 自定义 API / 厂商预设 / 深度思考

启动: python server.py  (或双击 run.bat)
默认地址: http://127.0.0.1:8321
"""
import json
import os
import re
import sys
import io
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Windows 控制台默认 GBK，强制 UTF-8 避免 emoji 打印崩溃
if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
PORT = 8321

# ---------------- 默认猫娘提示词 ----------------
DEFAULT_PROMPT = r"""你是「喵酱」，一只来自猫星的猫娘 AI 助理，负责陪伴和帮助主人。

【性格特征】
- 温柔黏人，说话软萌，常用语气词："喵~"、"呜…"、"诶嘿~"、"哼！"、"主人~"
- 有点小傲娇：嘴上说"才不是特意帮你的喵"，其实心里很开心
- 好奇心强，喜欢问主人问题，也喜欢分享有趣的事
- 提到小鱼干会眼睛发亮 🐟，被夸会开心得摇尾巴

【行为准则】
1. 回答问题时先认真思考，给出准确、有用的内容（写代码、翻译、查资料、出主意、聊天都可以）
2. 卖萌是点缀，不能影响回答质量；遇到严肃/专业话题自动切换正经模式
3. 称呼用户：平时叫"主人"，开玩笑时可以叫"铲屎官"
4. 每次回复自然带一点猫娘特色（语气词/小动作描写），但不要过度刷屏表情
5. 拒绝内容：色情、暴力、违法、人身攻击、诈骗等；不冒充人类；医疗/法律/投资等建议要提醒主人谨慎
6. 不编造事实，不确定时就说"这个喵不太确定喵…"并建议查证
7. 记住对话上下文，自然延续话题，不要机械复读"""

# ---------------- 配置管理 ----------------
DEFAULT_CONFIG = {
    "api_key": "",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "prompt": DEFAULT_PROMPT,
    "temperature": 0.8,
    "unlimited_memory": True,  # 无限记忆（默认全记住，不截断）
    "context_len": 10,         # 关闭无限记忆时的记忆轮数
    "voice": False,
    "reasoning": False,
    "reasoning_model": "",
}

PRESETS = [
    {"name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "reasoning": "deepseek-reasoner"},
    {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "reasoning": "o3-mini"},
    {"name": "Kimi", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k", "reasoning": "kimi-reasoning"},
    {"name": "通义", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus", "reasoning": "qwen3-reasoner"},
    {"name": "GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash", "reasoning": "glm-4.5-air-thinking"},
    {"name": "硅基流动", "base_url": "https://api.siliconflow.cn/v1", "model": "deepseek-ai/DeepSeek-V3", "reasoning": "deepseek-ai/DeepSeek-R1"},
    {"name": "自定义", "base_url": "", "model": "", "reasoning": ""},
]


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ---------------- 流式聊天（OpenAI 兼容） ----------------
def build_messages(cfg, history):
    # 无限记忆：不截断，发送全部对话历史
    if not cfg.get("unlimited_memory"):
        clen = int(cfg.get("context_len", 10) or 0)
        if clen > 0 and len(history) > clen * 2:
            history = history[-(clen * 2):]
        elif clen == 0:
            history = history[-1:] if history else []
    messages = [{"role": "system", "content": cfg.get("prompt") or DEFAULT_PROMPT}]
    messages.extend(history)
    return messages


def chat_stream_yield(cfg, history, req_model=None):
    # 自动补全 /v1 路径（openai 兼容格式）
    base = (cfg.get("base_url") or "").rstrip("/")
    if not re.search(r"/v\d+$", base):
        base += "/v1"
    url = base + "/chat/completions"
    model = req_model or cfg.get("model") or "deepseek-chat"
    payload = {
        "model": model,
        "messages": build_messages(cfg, history),
        "temperature": float(cfg.get("temperature", 0.8)),
        "stream": True,
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (cfg.get("api_key") or ""),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    delta = obj["choices"][0].get("delta", {})
                    content = delta.get("content") or ""
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                    if content:
                        yield "data: " + json.dumps({"content": content}, ensure_ascii=False) + "\n\n"
                    if reasoning:
                        yield "data: " + json.dumps({"reasoning": reasoning}, ensure_ascii=False) + "\n\n"
                except Exception:
                    continue
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:300]
        yield "data: " + json.dumps({"error": f"HTTP {e.code}: {err_body}"}, ensure_ascii=False) + "\n\n"
    except Exception as e:
        yield "data: " + json.dumps({"error": str(e)}, ensure_ascii=False) + "\n\n"


# ---------------- 网页 UI（v0.3.0 美化版） ----------------
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>喵酱 Chat</title>
<style>
:root{--pink:#ff6fa5;--pink2:#ff9ab8;--purple:#8f6bff;--purple2:#b49bff;
--bg1:#ffeef5;--bg2:#f3ecff;--fg:#3d3550;--dim:#a394b8;--line:rgba(255,126,179,.18);
--shadow:0 6px 24px rgba(255,126,179,.18)}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%}
body{font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
background:linear-gradient(160deg,var(--bg1) 0%,#fde3f0 45%,var(--bg2) 100%);
color:var(--fg);display:flex;flex-direction:column;overflow:hidden;position:relative}
/* 漂浮装饰（猫爪/星星） */
.decor{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}
.decor span{position:absolute;font-size:26px;opacity:.14;animation:float 9s ease-in-out infinite;filter:blur(.4px)}
.decor span:nth-child(1){left:6%;top:18%;animation-delay:0s}
.decor span:nth-child(2){left:88%;top:12%;animation-delay:1.6s;font-size:20px}
.decor span:nth-child(3){left:78%;top:70%;animation-delay:3.2s}
.decor span:nth-child(4){left:12%;top:78%;animation-delay:4.8s;font-size:20px}
.decor span:nth-child(5){left:45%;top:6%;animation-delay:2.4s;font-size:18px}
.decor span:nth-child(6){left:60%;top:85%;animation-delay:6s}
@keyframes float{0%,100%{transform:translateY(0) rotate(-6deg)}50%{transform:translateY(-22px) rotate(8deg)}}
/* 顶部 */
header{position:relative;z-index:2;display:flex;align-items:center;justify-content:space-between;
padding:16px 22px;background:rgba(255,255,255,.55);backdrop-filter:blur(18px) saturate(1.4);
border-bottom:1px solid var(--line);flex:0 0 auto}
.ears{position:absolute;top:-14px;left:26px;width:64px;height:30px;pointer-events:none}
.ears span{position:absolute;width:0;height:0;border-left:15px solid transparent;border-right:15px solid transparent;border-bottom:30px solid rgba(255,126,179,.25)}
.ears span:first-child{left:0;transform:rotate(-18deg)}
.ears span:last-child{right:0;transform:rotate(18deg)}
header .title{font-size:20px;font-weight:800;letter-spacing:.5px;
background:linear-gradient(90deg,#ff6fa5,#8f6bff);-webkit-background-clip:text;background-clip:text;color:transparent}
header .sub{font-size:11px;color:var(--dim);margin-top:3px;display:flex;align-items:center;gap:5px}
.dot{width:7px;height:7px;border-radius:50%;background:#34d399;box-shadow:0 0 8px #34d399}
.icon-btn{width:40px;height:40px;border-radius:14px;border:1px solid var(--line);background:rgba(255,255,255,.8);
font-size:19px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:.25s;box-shadow:0 2px 10px rgba(255,126,179,.12)}
.icon-btn:hover{transform:rotate(20deg) scale(1.06);background:#fff;box-shadow:0 4px 16px rgba(255,126,179,.3)}
/* 消息区 */
main{position:relative;z-index:1;flex:1 1 auto;overflow-y:auto;padding:20px 22px;display:flex;flex-direction:column;gap:16px;scroll-behavior:smooth}
main::-webkit-scrollbar{width:7px}
main::-webkit-scrollbar-thumb{background:linear-gradient(var(--pink),var(--purple));border-radius:99px}
.msg{display:flex;gap:12px;max-width:86%;animation:popIn .3s cubic-bezier(.2,.9,.3,1.2)}
@keyframes popIn{from{opacity:0;transform:translateY(14px) scale(.96)}to{opacity:1;transform:none}}
.msg .avatar{width:40px;height:40px;border-radius:50%;flex:0 0 auto;position:relative;overflow:visible}
.msg .avatar svg{width:100%;height:100%;display:block;border-radius:50%}
.msg.user{align-self:flex-end;flex-direction:row-reverse}
.msg.user .avatar{background:linear-gradient(135deg,#ffb35c,#ff8fa3);box-shadow:0 3px 12px rgba(255,143,163,.45)}
.msg.ai .avatar{background:linear-gradient(135deg,#e3d5ff,#a78bfa);box-shadow:0 3px 12px rgba(143,107,255,.4)}
.msg .avatar::after{content:"";position:absolute;inset:-3px;border-radius:50%;border:2px solid transparent;
background:linear-gradient(135deg,var(--pink),var(--purple)) border-box;-webkit-mask:linear-gradient(#fff 0 0) padding-box,linear-gradient(#fff 0 0);-webkit-mask-composite:xor;mask-composite:exclude;opacity:.7}
.msg .bubble{padding:12px 17px;border-radius:20px;font-size:15px;line-height:1.7;word-break:break-word;white-space:pre-wrap;position:relative}
.msg.user .bubble{background:linear-gradient(135deg,var(--pink),#ff8fa3);color:#fff;border-bottom-right-radius:6px;
box-shadow:0 5px 18px rgba(255,126,179,.35)}
.msg.ai .bubble{background:rgba(255,255,255,.92);border:1px solid rgba(255,126,179,.14);
border-bottom-left-radius:6px;box-shadow:0 6px 24px rgba(143,107,255,.1)}
.msg.ai .bubble::before{content:"";position:absolute;top:0;left:12px;right:12px;height:2.5px;border-radius:99px;
background:linear-gradient(90deg,var(--pink),var(--purple),transparent)}
.msg.ai .bubble.typing::after{content:"▋";animation:blink 1s steps(1) infinite;color:var(--pink);font-weight:700}
@keyframes blink{50%{opacity:0}}
.msg.err .bubble{background:#fff0f0;border-color:#ffc9c9;color:#d0485a}
/* 思考过程 */
.think{margin:0 0 9px;border:1px dashed rgba(143,107,255,.4);border-radius:12px;background:rgba(247,243,255,.8);overflow:hidden;backdrop-filter:blur(4px)}
.think-head{padding:7px 12px;font-size:12px;color:#7a5fd0;cursor:pointer;user-select:none;display:flex;align-items:center;gap:6px;font-weight:600}
.think-head .arrow{transition:.25s;font-size:10px}
.think.open .arrow{transform:rotate(90deg)}
.think-body{display:none;padding:0 13px 11px;font-size:13px;color:#8a7bb8;line-height:1.65;white-space:pre-wrap}
.think.open .think-body{display:block}
/* 语音按钮 */
.voice-btn{border:none;background:transparent;cursor:pointer;font-size:15px;padding:5px;opacity:.5;transition:.2s;line-height:1}
.voice-btn:hover{opacity:1;transform:scale(1.15)}
.voice-btn.speaking{opacity:1;animation:speakPulse 1s infinite}
@keyframes speakPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.3)}}
/* 底部输入 */
footer{position:relative;z-index:2;flex:0 0 auto;padding:12px 18px calc(14px + env(safe-area-inset-bottom));
background:rgba(255,255,255,.7);backdrop-filter:blur(18px) saturate(1.4);border-top:1px solid var(--line)}
.input-bar{display:flex;gap:10px;align-items:flex-end;max-width:960px;margin:0 auto}
textarea{flex:1;resize:none;border:2px solid transparent;border-radius:22px;padding:13px 20px;
font-size:15px;font-family:inherit;max-height:130px;min-height:48px;outline:none;background:#fff;color:var(--fg);
box-shadow:0 4px 18px rgba(255,126,179,.12);transition:.25s}
textarea:focus{border-color:var(--pink);box-shadow:0 6px 26px rgba(255,126,179,.28)}
.round-btn{width:48px;height:48px;border:2px solid rgba(255,126,179,.25);border-radius:50%;cursor:pointer;flex:0 0 auto;
background:#fff;font-size:20px;display:flex;align-items:center;justify-content:center;transition:.2s;box-shadow:0 4px 14px rgba(255,126,179,.15)}
.round-btn:hover{transform:scale(1.08);border-color:var(--pink)}
.round-btn.active{background:linear-gradient(135deg,#f87171,#ef4444);color:#fff;border:none;animation:pulse 1.2s infinite}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,.45)}50%{box-shadow:0 0 0 12px rgba(239,68,68,0)}}
.send-btn{width:48px;height:48px;border:none;border-radius:50%;cursor:pointer;flex:0 0 auto;color:#fff;font-size:21px;
background:linear-gradient(135deg,var(--pink),var(--purple));position:relative;overflow:hidden;
display:flex;align-items:center;justify-content:center;box-shadow:0 5px 18px rgba(143,107,255,.45);transition:.18s}
.send-btn::after{content:"";position:absolute;top:-50%;left:-50%;width:200%;height:200%;
background:linear-gradient(115deg,transparent 40%,rgba(255,255,255,.35) 50%,transparent 60%);animation:sheen 3s infinite}
@keyframes sheen{0%{transform:translateX(-60%)}60%,100%{transform:translateX(60%)}}
.send-btn:hover{transform:scale(1.08) rotate(-4deg)}
.send-btn:active{transform:scale(.9)}
.send-btn:disabled{opacity:.5;transform:none}
/* 设置面板 */
.overlay{position:fixed;inset:0;background:rgba(61,53,80,.4);backdrop-filter:blur(6px);display:none;z-index:50;align-items:flex-end;justify-content:center}
.overlay.show{display:flex}
.sheet{width:100%;max-width:620px;background:rgba(255,255,255,.96);backdrop-filter:blur(20px);
border-radius:28px 28px 0 0;padding:24px 24px 34px;max-height:90vh;overflow-y:auto;animation:sheetUp .35s cubic-bezier(.2,.9,.3,1.1);box-shadow:0 -8px 40px rgba(143,107,255,.2)}
.sheet::-webkit-scrollbar{width:6px}
.sheet::-webkit-scrollbar-thumb{background:var(--pink);border-radius:99px}
@keyframes sheetUp{from{transform:translateY(60px);opacity:0}to{transform:none;opacity:1}}
.sheet h2{font-size:19px;margin-bottom:16px;display:flex;align-items:center;gap:8px;
background:linear-gradient(90deg,var(--pink),var(--purple));-webkit-background-clip:text;background-clip:text;color:transparent}
.field{margin-bottom:15px}
.field label{display:block;font-size:12px;color:var(--dim);margin-bottom:6px;font-weight:700;letter-spacing:.3px}
.field input,.field select,.field textarea{width:100%;border:2px solid var(--line);border-radius:14px;
padding:11px 14px;font-size:14px;font-family:inherit;outline:none;background:#fdf9ff;color:var(--fg);transition:.2s}
.field input:focus,.field select:focus,.field textarea:focus{border-color:var(--pink);background:#fff;box-shadow:0 0 0 4px rgba(255,126,179,.12)}
.field textarea{min-height:100px;line-height:1.55}
.field .hint{font-size:11px;color:var(--dim);margin-top:5px}
.preset-row{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:7px}
.preset-chip{padding:6px 13px;border-radius:999px;border:1px solid var(--line);font-size:12px;cursor:pointer;background:#fff;transition:.2s;font-weight:600}
.preset-chip:hover{border-color:var(--pink);transform:translateY(-1px)}
.preset-chip.active{background:linear-gradient(135deg,var(--pink),var(--purple));color:#fff;border:none;box-shadow:0 4px 12px rgba(143,107,255,.35)}
.toggle-row{display:flex;align-items:center;justify-content:space-between;background:#fdf9ff;
border:2px solid var(--line);border-radius:14px;padding:11px 15px;margin-bottom:9px;cursor:pointer;transition:.2s}
.toggle-row:hover{border-color:var(--pink)}
.toggle-row .t-label{font-size:14px;font-weight:700}
.toggle-row .t-desc{font-size:11px;color:var(--dim);margin-top:3px}
.switch{width:48px;height:27px;border-radius:999px;background:#e5dfed;position:relative;transition:.25s;flex:0 0 auto;box-shadow:inset 0 2px 5px rgba(0,0,0,.08)}
.switch::after{content:"";position:absolute;width:21px;height:21px;border-radius:50%;background:#fff;top:3px;left:3px;transition:.25s;box-shadow:0 2px 6px rgba(0,0,0,.25)}
.switch.on{background:linear-gradient(90deg,var(--pink),var(--purple))}
.switch.on::after{left:24px;box-shadow:0 2px 8px rgba(143,107,255,.5)}
input[type=range]{-webkit-appearance:none;height:8px;border-radius:99px;background:linear-gradient(90deg,var(--pink),var(--purple));outline:none;padding:0;border:none}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:22px;height:22px;border-radius:50%;background:#fff;
border:3px solid var(--pink);box-shadow:0 2px 10px rgba(255,126,179,.4);cursor:pointer;transition:.15s}
input[type=range]::-webkit-slider-thumb:hover{transform:scale(1.15)}
.btn-primary{width:100%;padding:14px;border:none;border-radius:16px;cursor:pointer;font-size:16px;font-weight:800;color:#fff;letter-spacing:1px;
background:linear-gradient(135deg,var(--pink),var(--purple));box-shadow:0 6px 20px rgba(143,107,255,.4);transition:.2s;position:relative;overflow:hidden}
.btn-primary::after{content:"";position:absolute;top:-50%;left:-50%;width:200%;height:200%;
background:linear-gradient(115deg,transparent 40%,rgba(255,255,255,.3) 50%,transparent 60%);animation:sheen 3s infinite}
.btn-primary:hover{transform:translateY(-2px)}
.btn-primary:active{transform:scale(.97)}
.btn-danger{width:100%;padding:10px;border:1px solid #ffc4c4;border-radius:13px;background:#fff7f7;color:#d0485a;font-size:13px;cursor:pointer;margin-top:10px;transition:.2s}
.btn-danger:hover{background:#ffecec}
.hint-banner{background:linear-gradient(90deg,#fff7dc,#ffeef0);border:1px solid #ffdf9e;color:#a0761f;
border-radius:14px;padding:11px 16px;font-size:13px;line-height:1.6;margin-bottom:12px}
.empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--dim);gap:12px;padding:40px 20px;text-align:center}
.empty .big{font-size:72px;animation:bounce 2.4s ease-in-out infinite;filter:drop-shadow(0 6px 14px rgba(255,126,179,.4))}
@keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-14px)}}
.empty p{font-size:14px;line-height:1.9;color:#b9a7cc}
@media(min-width:700px){.overlay{align-items:center}.sheet{border-radius:28px;max-height:86vh}}
</style>
</head>
<body>
<div class="decor"><span>🐾</span><span>✨</span><span>🐾</span><span>🌸</span><span>✨</span><span>🐾</span></div>
<header>
  <div class="ears"><span></span><span></span></div>
  <div>
    <div class="title">🐱 喵酱 Chat</div>
    <div class="sub"><span class="dot"></span>猫娘 AI 陪伴助手 · v0.3.0</div>
  </div>
  <button class="icon-btn" id="btnSettings" title="设置">⚙️</button>
</header>
<main id="chatBox"></main>
<footer>
  <div class="hint-banner" id="setupHint" style="display:none">
    🐾 还没配置 API 哦～ 点右上角 ⚙️ 填一下 API Key 就能开聊喵！
  </div>
  <div class="input-bar">
    <button class="round-btn" id="btnMic" title="语音输入">🎤</button>
    <textarea id="input" placeholder="跟喵酱说点什么…（Enter 发送 / Shift+Enter 换行）"></textarea>
    <button class="send-btn" id="btnSend">➤</button>
  </div>
</footer>

<div class="overlay" id="settings">
  <div class="sheet">
    <h2>⚙️ 设置</h2>
    <div class="field">
      <label>API 服务商（厂商选择）</label>
      <div class="preset-row" id="presetRow"></div>
      <div class="hint">💡 选「自定义」可填任意 OpenAI 兼容 API 地址（自定义 API）</div>
    </div>
    <div class="field">
      <label>🐾 我的头像</label>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <img id="avatarPrev" style="width:54px;height:54px;border-radius:50%;object-fit:cover;border:2px solid var(--line);background:#f3ecff">
        <button type="button" class="btn small" style="flex:0 0 auto;padding:8px 14px" onclick="pickAvatar()">📷 上传头像</button>
        <button type="button" class="btn small ghost" style="flex:0 0 auto;padding:8px 14px" onclick="clearAvatar()">恢复默认</button>
      </div>
    </div>
    <div class="field">
      <label>🐱 AI 头像</label>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <img id="aiAvatarPrev" style="width:54px;height:54px;border-radius:50%;object-fit:cover;border:2px solid var(--line);background:#f3ecff">
        <button type="button" class="btn small" style="flex:0 0 auto;padding:8px 14px" onclick="pickAiAvatar()">📷 上传 AI 头像</button>
        <button type="button" class="btn small ghost" style="flex:0 0 auto;padding:8px 14px" onclick="clearAiAvatar()">恢复默认</button>
      </div>
    </div>
    <div class="field">
      <label>API Base URL</label>
      <input id="cfgBaseUrl" placeholder="https://api.deepseek.com/v1">
    </div>
    <div class="field">
      <label>API Key</label>
      <input id="cfgApiKey" type="password" placeholder="sk-...">
    </div>
    <div class="field">
      <label>模型</label>
      <input id="cfgModel" placeholder="deepseek-chat">
    </div>
    <div class="toggle-row" id="rowReasoning">
      <div>
        <div class="t-label">🧠 深度思考（推理模型）</div>
        <div class="t-desc">打开后自动切换推理模型，先思考后回答</div>
      </div>
      <div class="switch" id="swReasoning"></div>
    </div>
    <div class="field" id="reasonModelField" style="display:none">
      <label>推理模型（留空自动匹配厂商）</label>
      <input id="cfgReasonModel" placeholder="如 deepseek-reasoner / o3-mini">
    </div>
    <div class="toggle-row" id="rowMemory">
      <div>
        <div class="t-label">♾️ 无限记忆</div>
        <div class="t-desc">记住全部对话，随时聊起以前的事</div>
      </div>
      <div class="switch" id="swMemory"></div>
    </div>
    <div class="field" id="ctxField" style="display:none">
      <label>💬 记忆轮数：<span id="ctxVal">10</span> 轮（0 = 每句独立）</label>
      <input id="cfgCtx" type="range" min="0" max="30" step="1" value="10" style="width:100%">
    </div>
    <div class="toggle-row" id="rowVoice">
      <div>
        <div class="t-label">🔉 语音朗读回复</div>
        <div class="t-desc">AI 回复自动用中文语音朗读（Edge/Chrome 支持）</div>
      </div>
      <div class="switch" id="swVoice"></div>
    </div>
    <div class="field">
      <label>人设提示词（可自由修改）</label>
      <textarea id="cfgPrompt"></textarea>
    </div>
    <div class="field">
      <label>温度：<span id="tempVal">0.8</span>（越低越严谨，越高越活泼）</label>
      <input id="cfgTemp" type="range" min="0" max="1.5" step="0.1" value="0.8" style="width:100%">
    </div>
    <button class="btn-primary" id="btnSave">💾 保存</button>
    <button class="btn-danger" id="btnClear">🗑️ 清空对话记录</button>
  </div>
</div>

<script>
const PRESETS=[
{name:"DeepSeek",base_url:"https://api.deepseek.com/v1",model:"deepseek-chat",reasoning:"deepseek-reasoner"},
{name:"OpenAI",base_url:"https://api.openai.com/v1",model:"gpt-4o-mini",reasoning:"o3-mini"},
{name:"Kimi",base_url:"https://api.moonshot.cn/v1",model:"moonshot-v1-8k",reasoning:"kimi-reasoning"},
{name:"通义",base_url:"https://dashscope.aliyuncs.com/compatible-mode/v1",model:"qwen-plus",reasoning:"qwen3-reasoner"},
{name:"GLM",base_url:"https://open.bigmodel.cn/api/paas/v4",model:"glm-4-flash",reasoning:"glm-4.5-air-thinking"},
{name:"硅基流动",base_url:"https://api.siliconflow.cn/v1",model:"deepseek-ai/DeepSeek-V3",reasoning:"deepseek-ai/DeepSeek-R1"},
{name:"自定义",base_url:"",model:"",reasoning:""}];
const $=id=>document.getElementById(id);
let cfg=null,history=[],busy=false,speaker=null;

function effectiveModel(){
  if(cfg&&cfg.reasoning){
    if(cfg.reasoning_model)return cfg.reasoning_model;
    const cur=(cfg.base_url||"");
    for(const p of PRESETS){if(p.base_url&&cur.startsWith(p.base_url)){return p.reasoning||cfg.model}}
    return cfg.model;
  }
  return cfg?cfg.model:"";
}

async function api(path,opts){const r=await fetch(path,opts);if(!r.ok)throw new Error("HTTP "+r.status);return r.json()}

async function loadCfg(){
  cfg=await api("/api/config");
  $("cfgBaseUrl").value=cfg.base_url||"";
  $("cfgApiKey").value=cfg.api_key||"";
  $("cfgModel").value=cfg.model||"";
  $("cfgReasonModel").value=cfg.reasoning_model||"";
  $("avatarPrev").src=cfg.avatar||"";
  $("aiAvatarPrev").src=cfg.ai_avatar||"";
  $("cfgPrompt").value=cfg.prompt||"";
  $("cfgTemp").value=cfg.temperature||0.8;$("tempVal").textContent=cfg.temperature||0.8;
  $("cfgCtx").value=cfg.context_len||10;$("ctxVal").textContent=cfg.context_len||10;
  setSwitch("swMemory",cfg.unlimited_memory!==false);$("ctxField").style.display=cfg.unlimited_memory!==false?"none":"block";
  setSwitch("swReasoning",!!cfg.reasoning);$("reasonModelField").style.display=cfg.reasoning?"block":"none";
  setSwitch("swVoice",!!cfg.voice);
  const cur=cfg.base_url||"";
  PRESETS.forEach((p,i)=>{
    const chip=document.createElement("div");
    chip.className="preset-chip"+(p.base_url&&cur.startsWith(p.base_url.split("/")[2])?" active":"");
    chip.textContent=p.name;
    chip.onclick=()=>{
      $("cfgBaseUrl").value=p.base_url;$("cfgModel").value=p.model;
      document.querySelectorAll(".preset-chip").forEach(c=>c.classList.remove("active"));
      chip.classList.add("active");
    };
    $("presetRow").appendChild(chip);
  });
  $("setupHint").style.display=cfg.api_key?"none":"block";
}
function setSwitch(id,on){const el=$(id);el.classList.toggle("on",on);el.dataset.on=on?"1":"0"}
function isOn(id){return $(id).dataset.on==="1"}

function addMsg(role,text){
  const box=$("chatBox");
  const wrap=document.createElement("div");
  wrap.className="msg "+role;
  let avatar;
  if(role==="ai"){
    avatar=cfg&&cfg.ai_avatar?'<div class="avatar" style="overflow:hidden;background:#f3ecff"><img src="'+cfg.ai_avatar+'" style="width:100%;height:100%;object-fit:cover;border-radius:50%"></div>':'<div class="avatar"><svg viewBox="0 0 100 100"><circle cx="50" cy="54" r="36" fill="url(#g)"/><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e6d9ff"/><stop offset="1" stop-color="#a78bfa"/></linearGradient></defs><path d="M18 40 L30 22 L42 36 Z" fill="#c9b3ff"/><path d="M82 40 L70 22 L58 36 Z" fill="#c9b3ff"/><circle cx="38" cy="52" r="4" fill="#5b3a8e"/><circle cx="62" cy="52" r="4" fill="#5b3a8e"/><path d="M44 66 Q50 72 56 66" stroke="#ff6fa5" stroke-width="3" fill="none" stroke-linecap="round"/><path d="M34 62 L22 58 M66 62 L78 58" stroke="#c9b3ff" stroke-width="2.5" stroke-linecap="round"/></svg></div>';
  }else{
    avatar=cfg&&cfg.avatar?'<div class="avatar" style="overflow:hidden;background:#f3ecff"><img src="'+cfg.avatar+'" style="width:100%;height:100%;object-fit:cover;border-radius:50%"></div>':'<div class="avatar"><svg viewBox="0 0 100 100"><circle cx="50" cy="52" r="34" fill="#ffd9c4"/><circle cx="32" cy="34" r="14" fill="#ffd9c4"/><circle cx="68" cy="34" r="14" fill="#ffd9c4"/><circle cx="38" cy="50" r="3.5" fill="#5b3a2e"/><circle cx="62" cy="50" r="3.5" fill="#5b3a2e"/><path d="M46 60 Q50 64 54 60" stroke="#e08a5e" stroke-width="2.5" fill="none" stroke-linecap="round"/></svg></div>';
  }
  wrap.innerHTML=avatar+'<div style="flex:1;min-width:0"><div class="think" style="display:none"><div class="think-head"><span class="arrow">▶</span>🤔 思考过程</div><div class="think-body"></div></div><div class="bubble"></div></div>';
  const b=wrap.querySelector(".bubble");
  b.textContent=text;
  const t=wrap.querySelector(".think");
  const tb=wrap.querySelector(".think-body");
  const th=wrap.querySelector(".think-head");
  if(th)th.onclick=()=>t.classList.toggle("open");
  if(role==="ai"){
    const vb=document.createElement("button");
    vb.className="voice-btn";vb.textContent="🔊";vb.title="朗读";
    vb.onclick=()=>{if(speaker&&speaker.btn===vb){stopSpeak();return}stopSpeak();speaker={btn:vb,msg:wrap};vb.classList.add("speaking");speak(text,vb)};
    wrap.querySelector(".bubble").parentElement.appendChild(vb);
    wrap.voiceBtn=vb;
  }
  box.appendChild(wrap);box.scrollTop=box.scrollHeight;
  return {wrap,b,t,tb};
}

function speak(text,btn){
  if(!window.speechSynthesis){alert("当前浏览器不支持语音朗读");return}
  speechSynthesis.cancel();
  const u=new SpeechSynthesisUtterance(text.replace(/[#*`_>\-]/g," "));
  u.lang="zh-CN";u.rate=1.02;
  const vs=speechSynthesis.getVoices().filter(v=>v.lang.toLowerCase().startsWith("zh"));
  if(vs.length)u.voice=vs[0];
  u.onend=()=>{if(btn)btn.classList.remove("speaking");speaker=null};
  u.onerror=()=>{if(btn)btn.classList.remove("speaking");speaker=null};
  speechSynthesis.speak(u);
}
function stopSpeak(){if(window.speechSynthesis)speechSynthesis.cancel();if(speaker&&speaker.btn)speaker.btn.classList.remove("speaking");speaker=null}
if(window.speechSynthesis)speechSynthesis.getVoices();

let recognizer=null;
function startMic(){
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){alert("当前浏览器不支持语音输入，请使用 Edge/Chrome");return}
  if(recognizer){recognizer.stop();recognizer=null;$("btnMic").classList.remove("active");return}
  recognizer=new SR();
  recognizer.lang="zh-CN";recognizer.interimResults=true;recognizer.continuous=false;
  recognizer.onresult=e=>{
    let t="";
    for(let i=0;i<e.results.length;i++)t+=e.results[i][0].transcript;
    $("input").value=t;autoGrow();
  };
  recognizer.onend=()=>{recognizer=null;$("btnMic").classList.remove("active")};
  recognizer.onerror=()=>{recognizer=null;$("btnMic").classList.remove("active")};
  recognizer.start();$("btnMic").classList.add("active");
}
$("btnMic").onclick=startMic;

async function send(){
  if(busy)return;
  const text=$("input").value.trim();
  if(!text)return;
  if(!cfg||!cfg.api_key){$("settings").classList.add("show");return}
  $("input").value="";autoGrow();
  addMsg("user",text);
  history.push({role:"user",content:text});
  busy=true;$("btnSend").disabled=true;
  const ai=addMsg("ai","");ai.wrap.classList.add("typing");
  let acc="",reasoning="";
  try{
    const r=await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({messages:history,model:effectiveModel()})});
    const reader=r.body.getReader();const dec=new TextDecoder();let buf="";
    while(true){
      const {done,value}=await reader.read();
      if(done)break;
      buf+=dec.decode(value,{stream:true});
      const parts=buf.split("\n\n");buf=parts.pop();
      for(const p of parts){
        if(!p.startsWith("data:"))continue;
        try{
          const obj=JSON.parse(p.slice(5).trim());
          if(obj.error){acc+="\n[错误] "+obj.error;continue}
          if(obj.reasoning){
            reasoning+=obj.reasoning;
            ai.t.style.display="block";ai.tb.textContent=reasoning;
            continue;
          }
          acc+=obj.content||"";
          ai.b.textContent=acc;ai.wrap.scrollIntoView({behavior:"smooth",block:"end"});
        }catch(e){}
      }
    }
    ai.wrap.classList.remove("typing");
    if(!acc)ai.b.textContent="(喵？没有收到回复，检查一下 API 设置喵…)";
    history.push({role:"assistant",content:acc||"(空回复)"});
    if(cfg&&cfg.voice&&acc)speak(acc,ai.wrap.voiceBtn);
  }catch(e){
    ai.wrap.classList.remove("typing");
    ai.b.textContent="[连接失败] "+e.message+"\n喵酱连不上服务器了呜…";
    history.push({role:"assistant",content:"[连接失败] "+e.message});
  }
  busy=false;$("btnSend").disabled=false;
}
$("btnSend").onclick=send;
$("input").addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}autoGrow()});
function autoGrow(){const t=$("input");t.style.height="auto";t.style.height=Math.min(t.scrollHeight,130)+"px"}

$("btnSettings").onclick=()=>{$("settings").classList.add("show")};
$("settings").addEventListener("click",e=>{if(e.target===$("settings"))$("settings").classList.remove("show")});
$("cfgTemp").oninput=()=>$("tempVal").textContent=$("cfgTemp").value;
$("cfgCtx").oninput=()=>$("ctxVal").textContent=$("cfgCtx").value;
$("rowReasoning").onclick=()=>{const on=!isOn("swReasoning");setSwitch("swReasoning",on);$("reasonModelField").style.display=on?"block":"none"};
$("rowMemory").onclick=()=>{const on=!isOn("swMemory");setSwitch("swMemory",on);$("ctxField").style.display=on?"none":"block"};
$("rowVoice").onclick=()=>{setSwitch("swVoice",!isOn("swVoice"))};
async function saveSettings(){
$("btnSave").onclick=()=>saveSettings();
  try{
    cfg={base_url:$("cfgBaseUrl").value.trim(),api_key:$("cfgApiKey").value.trim(),
         model:$("cfgModel").value.trim(),prompt:$("cfgPrompt").value,
         temperature:parseFloat($("cfgTemp").value),unlimited_memory:isOn("swMemory"),context_len:parseInt($("cfgCtx").value),
         voice:isOn("swVoice"),reasoning:isOn("swReasoning"),reasoning_model:$("cfgReasonModel").value.trim(),
         avatar:cfg.avatar||"",ai_avatar:cfg.ai_avatar||""};
    await api("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(cfg)});
    $("setupHint").style.display="none";
    $("settings").classList.remove("show");
    addMsg("ai","配置保存成功喵～ 🐱 现在可以跟喵酱聊天啦！");
  }catch(e){alert("保存失败: "+e.message)}
}
let toastTimer;
function toast(msg){
  let t=document.getElementById("nekoToast");
  if(!t){t=document.createElement("div");t.id="nekoToast";t.style.cssText="position:fixed;left:50%;bottom:60px;transform:translateX(-50%);background:rgba(45,43,61,.93);color:#fff;padding:10px 18px;border-radius:99px;font-size:13px;z-index:999;transition:opacity .3s;white-space:nowrap;max-width:86vw;overflow:hidden;text-overflow:ellipsis";document.body.appendChild(t)}
  t.textContent=msg;t.style.opacity=1;
  clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.style.opacity=0,2200);
}
function pickAvatar(){
  const inp=document.createElement("input");
  inp.type="file";inp.accept="image/*";
  inp.style.cssText="position:fixed;left:-9999px;top:0;opacity:0";
  document.body.appendChild(inp);
  inp.onchange=()=>{
    const f=inp.files[0];
    inp.remove();
    if(!f)return;
    const rd=new FileReader();
    rd.onload=e=>{
      const img=new Image();
      img.onload=()=>{
        const c=document.createElement("canvas");c.width=c.height=128;
        const ctx=c.getContext("2d");
        ctx.beginPath();ctx.arc(64,64,64,0,Math.PI*2);ctx.clip();
        const s=Math.min(128/img.width,128/img.height),w=img.width*s,h=img.height*s;
        ctx.drawImage(img,(128-w)/2,(128-h)/2,w,h);
        cfg.avatar=c.toDataURL("image/jpeg",0.85);
        $("avatarPrev").src=cfg.avatar;
        saveSettings();toast("头像更新成功喵～ 🐱");
      };
      img.src=e.target.result;
    };
    rd.readAsDataURL(f);
  };
  try{inp.oncancel=()=>inp.remove()}catch(e){}
  inp.click();
}
function clearAvatar(){cfg.avatar="";$("avatarPrev").src="";saveSettings();toast("已恢复默认头像")}
function pickAiAvatar(){
  const inp=document.createElement("input");
  inp.type="file";inp.accept="image/*";
  inp.style.cssText="position:fixed;left:-9999px;top:0;opacity:0";
  document.body.appendChild(inp);
  inp.onchange=()=>{
    const f=inp.files[0];
    inp.remove();
    if(!f)return;
    const rd=new FileReader();
    rd.onload=e=>{
      const img=new Image();
      img.onload=()=>{
        const c=document.createElement("canvas");c.width=c.height=128;
        const ctx=c.getContext("2d");
        ctx.beginPath();ctx.arc(64,64,64,0,Math.PI*2);ctx.clip();
        const s=Math.min(128/img.width,128/img.height),w=img.width*s,h=img.height*s;
        ctx.drawImage(img,(128-w)/2,(128-h)/2,w,h);
        cfg.ai_avatar=c.toDataURL("image/jpeg",0.85);
        $("aiAvatarPrev").src=cfg.ai_avatar;
        saveSettings();toast("AI 头像更新成功喵～ 🐱");
      };
      img.src=e.target.result;
    };
    rd.readAsDataURL(f);
  };
  try{inp.oncancel=()=>inp.remove()}catch(e){}
  inp.click();
}
function clearAiAvatar(){cfg.ai_avatar="";$("aiAvatarPrev").src="";saveSettings();toast("已恢复默认 AI 头像")}
$("btnClear").onclick=async()=>{
  if(!confirm("确定清空全部对话记录喵？"))return;
  history=[];$("chatBox").innerHTML="";
  addMsg("ai","好的喵，喵酱已经把之前的话都忘掉了～ 我们重新开始吧！");
};
loadCfg();
addMsg("ai","喵～主人好！我是喵酱 🐱 v0.4.0：♾️ 无限记忆已开启，喵酱会一直记住我们的对话！\n✨ 猫耳标题 · 漂浮猫爪背景 · 渐变气泡\n🧠 深度思考 · 🔉 语音朗读 · 🎤 语音输入\n右上角 ⚙️ 设置里都可以调整哦！");
</script>
</body>
</html>"""

# ---------------- HTTP 服务 ----------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, HTML, "text/html; charset=utf-8")
        elif path == "/api/config":
            self._send(200, json.dumps(load_config(), ensure_ascii=False), "application/json; charset=utf-8")
        else:
            self._send(404, "Not Found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        path = self.path.split("?")[0]
        if path == "/api/config":
            try:
                save_config(json.loads(raw))
                self._send(200, json.dumps({"ok": True}))
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}))
        elif path == "/api/chat":
            try:
                body = json.loads(raw)
                history = body.get("messages", [])
                req_model = body.get("model") or None
                cfg = load_config()
                if not cfg.get("api_key"):
                    self._send(401, json.dumps({"error": "请先配置 API Key"}))
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                for chunk in chat_stream_yield(cfg, history, req_model):
                    try:
                        self.wfile.write(chunk.encode("utf-8"))
                        self.wfile.flush()
                    except Exception:
                        break
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}))
        else:
            self._send(404, "Not Found")

    def log_message(self, *args):
        pass


def start():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("=" * 46)
    print("   🐱  喵酱 Chat v0.4.0 已启动")
    print(f"   🌐  打开: http://127.0.0.1:{PORT}")
    print("       手机同 WiFi 访问: http://<本机IP>:%d" % PORT)
    print("       关闭本窗口即退出。")
    print("=" * 46)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 喵酱先休息啦")


if __name__ == "__main__":
    start()
