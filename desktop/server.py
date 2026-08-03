# -*- coding: utf-8 -*-
"""
喵酱 Chat - 电脑端 v0.2.0
纯 AI 聊天助手（猫娘人设），标准库实现，无第三方依赖。
功能：上下文长度设置 / 语音朗读 / 语音输入 / 自定义 API / 厂商预设 / 深度思考(reasoning)

启动: python server.py  (或双击 run.bat)
默认地址: http://127.0.0.1:8321
"""
import json
import os
import sys
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
    "context_len": 10,      # 上下文记忆轮数（0=单轮）
    "voice": False,         # 自动朗读回复
    "reasoning": False,     # 深度思考（推理模型）
    "reasoning_model": "",  # 自定义推理模型（留空自动按厂商匹配）
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
    """history: [{role, content}...]；按 context_len 截断，只保留最近 N 轮；最前插入系统提示词"""
    clen = int(cfg.get("context_len", 10) or 0)
    if clen > 0 and len(history) > clen * 2:
        history = history[-(clen * 2):]
    elif clen == 0:
        history = history[-1:] if history else []
    messages = [{"role": "system", "content": cfg.get("prompt") or DEFAULT_PROMPT}]
    messages.extend(history)
    return messages


def chat_stream_yield(cfg, history, req_model=None):
    """生成器：逐段产出 SSE 文本；reasoning 模型时 delta.reasoning_content 以 {"reasoning":...} 转发"""
    url = (cfg.get("base_url") or "").rstrip("/") + "/chat/completions"
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


# ---------------- 网页 UI ----------------
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>喵酱 Chat</title>
<style>
:root{--pink:#ff7eb3;--purple:#8f6bff;--bg1:#fff0f6;--bg2:#f0e9ff;--card:#fff;
--fg:#3d3a4a;--dim:#9a92ab;--mine:#ff7eb3;--line:#f0e6f2}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%}
body{font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
background:linear-gradient(160deg,var(--bg1),var(--bg2));color:var(--fg);display:flex;flex-direction:column;overflow:hidden}
header{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;
background:rgba(255,255,255,.72);backdrop-filter:blur(12px);border-bottom:1px solid var(--line);flex:0 0 auto}
header .title{font-size:18px;font-weight:800;background:linear-gradient(90deg,var(--pink),var(--purple));
-webkit-background-clip:text;background-clip:text;color:transparent}
header .sub{font-size:11px;color:var(--dim);margin-top:2px}
.icon-btn{width:38px;height:38px;border-radius:12px;border:1px solid var(--line);background:#fff;
font-size:18px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:.2s}
.icon-btn:hover{background:#fff0f6}
main{flex:1 1 auto;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:14px;scroll-behavior:smooth}
.msg{display:flex;gap:10px;max-width:92%;animation:pop .25s ease}
@keyframes pop{from{opacity:0;transform:translateY(8px)}to{opacity:1}}
.msg .avatar{width:36px;height:36px;border-radius:50%;flex:0 0 auto;display:flex;align-items:center;justify-content:center;font-size:20px;box-shadow:0 2px 8px rgba(255,126,179,.35)}
.msg.user{align-self:flex-end;flex-direction:row-reverse}
.msg.user .avatar{background:linear-gradient(135deg,var(--pink),#ff9a76)}
.msg.ai .avatar{background:linear-gradient(135deg,#cba6ff,#8f6bff)}
.bubble{padding:11px 15px;border-radius:18px;font-size:15px;line-height:1.65;word-break:break-word;white-space:pre-wrap}
.msg.user .bubble{background:linear-gradient(135deg,var(--pink),#ff8fa3);color:#fff;border-bottom-right-radius:5px}
.msg.ai .bubble{background:#fff;border:1px solid var(--line);border-bottom-left-radius:5px;box-shadow:0 2px 10px rgba(143,107,255,.08)}
.msg.ai .bubble.typing::after{content:"▋";animation:blink 1s steps(1) infinite;color:var(--pink)}
@keyframes blink{50%{opacity:0}}
.msg.err .bubble{background:#ffe8e8;border-color:#ffb3b3;color:#c0392b}
.think{margin:0 0 8px;border:1px dashed #c9b8ff;border-radius:10px;background:#f7f3ff;overflow:hidden}
.think-head{padding:6px 10px;font-size:12px;color:#7a5fd0;cursor:pointer;user-select:none;display:flex;align-items:center;gap:6px}
.think-head .arrow{transition:.2s}
.think.open .arrow{transform:rotate(90deg)}
.think-body{display:none;padding:0 12px 10px;font-size:13px;color:#8a7bb8;line-height:1.6;white-space:pre-wrap}
.think.open .think-body{display:block}
.voice-btn{border:none;background:transparent;cursor:pointer;font-size:15px;padding:4px;opacity:.55;transition:.15s;line-height:1}
.voice-btn:hover{opacity:1}
.voice-btn.speaking{opacity:1;animation:speak 1s infinite}
@keyframes speak{0%,100%{transform:scale(1)}50%{transform:scale(1.25)}}
footer{flex:0 0 auto;padding:10px 12px calc(12px + env(safe-area-inset-bottom));
background:rgba(255,255,255,.8);backdrop-filter:blur(12px);border-top:1px solid var(--line)}
.input-bar{display:flex;gap:10px;align-items:flex-end}
textarea{flex:1;resize:none;border:1px solid var(--line);border-radius:18px;padding:12px 16px;
font-size:15px;font-family:inherit;max-height:120px;min-height:46px;outline:none;background:#fff;color:var(--fg)}
textarea:focus{border-color:var(--pink);box-shadow:0 0 0 3px rgba(255,126,179,.15)}
.round-btn{width:46px;height:46px;border:1px solid var(--line);border-radius:50%;cursor:pointer;flex:0 0 auto;
background:#fff;font-size:19px;display:flex;align-items:center;justify-content:center;transition:.15s}
.round-btn:active{transform:scale(.92)}
.round-btn.active{background:linear-gradient(135deg,#f87171,#ef4444);color:#fff;border:none;animation:pulse 1s infinite}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,.4)}50%{box-shadow:0 0 0 10px rgba(239,68,68,0)}}
.send-btn{width:46px;height:46px;border:none;border-radius:50%;cursor:pointer;flex:0 0 auto;
background:linear-gradient(135deg,var(--pink),var(--purple));color:#fff;font-size:20px;
display:flex;align-items:center;justify-content:center;box-shadow:0 4px 14px rgba(143,107,255,.4);transition:.15s}
.send-btn:active{transform:scale(.92)}
.send-btn:disabled{opacity:.5}
.overlay{position:fixed;inset:0;background:rgba(61,58,74,.45);backdrop-filter:blur(4px);display:none;z-index:50;align-items:flex-end;justify-content:center}
.overlay.show{display:flex}
.sheet{width:100%;max-width:640px;background:#fff;border-radius:24px 24px 0 0;padding:20px 20px 30px;
max-height:88vh;overflow-y:auto;animation:up .3s ease}
@keyframes up{from{transform:translateY(40px);opacity:0}to{transform:none;opacity:1}}
.sheet h2{font-size:18px;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.field{margin-bottom:14px}
.field label{display:block;font-size:12px;color:var(--dim);margin-bottom:6px;font-weight:600}
.field input,.field select,.field textarea{width:100%;border:1px solid var(--line);border-radius:12px;
padding:10px 12px;font-size:14px;font-family:inherit;outline:none;background:#faf8ff;color:var(--fg)}
.field input:focus,.field select:focus,.field textarea:focus{border-color:var(--pink)}
.field textarea{min-height:100px;line-height:1.5}
.field .hint{font-size:11px;color:var(--dim);margin-top:4px}
.preset-row{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px}
.preset-chip{padding:5px 12px;border-radius:999px;border:1px solid var(--line);font-size:12px;cursor:pointer;background:#fff;transition:.15s}
.preset-chip.active{background:linear-gradient(135deg,var(--pink),var(--purple));color:#fff;border:none}
.toggle-row{display:flex;align-items:center;justify-content:space-between;background:#faf8ff;
border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin-bottom:8px;cursor:pointer}
.toggle-row .t-label{font-size:14px;font-weight:600}
.toggle-row .t-desc{font-size:11px;color:var(--dim);margin-top:2px}
.switch{width:46px;height:26px;border-radius:999px;background:#ddd;position:relative;transition:.2s;flex:0 0 auto}
.switch::after{content:"";position:absolute;width:20px;height:20px;border-radius:50%;background:#fff;top:3px;left:3px;transition:.2s;box-shadow:0 1px 4px rgba(0,0,0,.2)}
.switch.on{background:linear-gradient(90deg,var(--pink),var(--purple))}
.switch.on::after{left:23px}
.btn-primary{width:100%;padding:13px;border:none;border-radius:14px;cursor:pointer;font-size:16px;font-weight:700;color:#fff;
background:linear-gradient(135deg,var(--pink),var(--purple));box-shadow:0 4px 14px rgba(143,107,255,.35)}
.btn-primary:active{transform:scale(.98)}
.btn-danger{width:100%;padding:10px;border:1px solid #ffb3b3;border-radius:12px;background:#fff5f5;color:#c0392b;font-size:13px;cursor:pointer;margin-top:8px}
.hint-banner{background:#fff3cd;border:1px solid #ffe08a;color:#8a6d1a;border-radius:12px;padding:10px 14px;font-size:13px;line-height:1.6;margin-bottom:10px}
.empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--dim);gap:10px;padding:40px 20px;text-align:center}
.empty .big{font-size:64px;animation:bounce 2s infinite}
@keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
.empty p{font-size:14px;line-height:1.7}
@media(min-width:700px){.overlay{align-items:center}.sheet{border-radius:24px;max-height:85vh}}
</style>
</head>
<body>
<header>
  <div>
    <div class="title">🐱 喵酱 Chat</div>
    <div class="sub">猫娘 AI 陪伴助手 · v0.2.0</div>
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
    <div class="field">
      <label>💬 上下文记忆：<span id="ctxVal">10</span> 轮（0 = 每句独立）</label>
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
  $("cfgPrompt").value=cfg.prompt||"";
  $("cfgTemp").value=cfg.temperature||0.8;$("tempVal").textContent=cfg.temperature||0.8;
  $("cfgCtx").value=cfg.context_len||10;$("ctxVal").textContent=cfg.context_len||10;
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
  const extra=role==="ai"?'<div class="avatar">🐱</div><div style="flex:1;min-width:0">'
                        :'<div class="avatar">🐰</div><div style="flex:1;min-width:0">';
  wrap.innerHTML=extra+'<div class="think" style="display:none"><div class="think-head"><span class="arrow">▶</span>🤔 思考过程</div><div class="think-body"></div></div><div class="bubble"></div></div>';
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

// ---- 语音朗读 ----
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

// ---- 语音输入 ----
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

// ---- 发送 ----
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
function autoGrow(){const t=$("input");t.style.height="auto";t.style.height=Math.min(t.scrollHeight,120)+"px"}

$("btnSettings").onclick=()=>{$("settings").classList.add("show")};
$("settings").addEventListener("click",e=>{if(e.target===$("settings"))$("settings").classList.remove("show")});
$("cfgTemp").oninput=()=>$("tempVal").textContent=$("cfgTemp").value;
$("cfgCtx").oninput=()=>$("ctxVal").textContent=$("cfgCtx").value;
$("rowReasoning").onclick=()=>{const on=!isOn("swReasoning");setSwitch("swReasoning",on);$("reasonModelField").style.display=on?"block":"none"};
$("rowVoice").onclick=()=>{setSwitch("swVoice",!isOn("swVoice"))};
$("btnSave").onclick=async()=>{
  try{
    cfg={base_url:$("cfgBaseUrl").value.trim(),api_key:$("cfgApiKey").value.trim(),
         model:$("cfgModel").value.trim(),prompt:$("cfgPrompt").value,
         temperature:parseFloat($("cfgTemp").value),context_len:parseInt($("cfgCtx").value),
         voice:isOn("swVoice"),reasoning:isOn("swReasoning"),reasoning_model:$("cfgReasonModel").value.trim()};
    await api("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(cfg)});
    $("setupHint").style.display="none";
    $("settings").classList.remove("show");
    addMsg("ai","配置保存成功喵～ 🐱 现在可以跟喵酱聊天啦！");
  }catch(e){alert("保存失败: "+e.message)}
};
$("btnClear").onclick=async()=>{
  if(!confirm("确定清空全部对话记录喵？"))return;
  history=[];$("chatBox").innerHTML="";
  addMsg("ai","好的喵，喵酱已经把之前的话都忘掉了～ 我们重新开始吧！");
};
loadCfg();
addMsg("ai","喵～主人好！我是喵酱 🐱 v0.2.0 新功能上线：\n• 🧠 深度思考开关\n• 🔉 AI 语音朗读（每条回复可点 🔊）\n• 🎤 语音输入（点麦克风说话）\n• 💬 上下文记忆长度可调\n• 🏭 厂商一键切换 + 自定义 API\n右上角 ⚙️ 设置里都可以调整哦！");
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
    print("   🐱  喵酱 Chat v0.2.0 已启动")
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
