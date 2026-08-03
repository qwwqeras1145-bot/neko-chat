# -*- coding: utf-8 -*-
"""
喵酱 Chat - 电脑端
纯 AI 聊天助手（猫娘人设），标准库实现，无第三方依赖。
首次填写 API Key 即可聊天，支持流式输出。

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
    "stream": True,
}

MODEL_PRESETS = [
    {"name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    {"name": "Moonshot Kimi", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    {"name": "阿里通义", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    {"name": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    {"name": "硅基流动", "base_url": "https://api.siliconflow.cn/v1", "model": "deepseek-ai/DeepSeek-V3"},
    {"name": "自定义", "base_url": "", "model": ""},
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
    """history: [{role, content}...] 前端传来的对话；在最前插入系统提示词"""
    messages = [{"role": "system", "content": cfg.get("prompt") or DEFAULT_PROMPT}]
    messages.extend(history)
    return messages


def chat_stream_yield(cfg, history):
    """生成器：逐段产出 SSE 文本（data: {...}），直到流结束"""
    url = (cfg.get("base_url") or "").rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg.get("model") or "deepseek-chat",
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
        with urllib.request.urlopen(req, timeout=120) as resp:
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
                    if content:
                        yield "data: " + json.dumps({"content": content}, ensure_ascii=False) + "\n\n"
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
:root{--pink:#ff7eb3;--purple:#8f6bff;--bg1:#fff0f6;--bg2:#f0e9ff;--card:#ffffff;
--fg:#3d3a4a;--dim:#9a92ab;--mine:#ff7eb3;--ai:#ffffff;--line:#f0e6f2}
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
.msg{display:flex;gap:10px;max-width:88%;animation:pop .25s ease}
@keyframes pop{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.msg .avatar{width:36px;height:36px;border-radius:50%;flex:0 0 auto;display:flex;align-items:center;justify-content:center;font-size:20px;box-shadow:0 2px 8px rgba(255,126,179,.35)}
.msg.user{align-self:flex-end;flex-direction:row-reverse}
.msg.user .avatar{background:linear-gradient(135deg,var(--pink),#ff9a76)}
.msg.ai .avatar{background:linear-gradient(135deg,#cba6ff,#8f6bff)}
.bubble{padding:11px 15px;border-radius:18px;font-size:15px;line-height:1.65;word-break:break-word;white-space:pre-wrap}
.msg.user .bubble{background:linear-gradient(135deg,var(--pink),#ff8fa3);color:#fff;border-bottom-right-radius:5px}
.msg.ai .bubble{background:var(--ai);border:1px solid var(--line);border-bottom-left-radius:5px;box-shadow:0 2px 10px rgba(143,107,255,.08)}
.msg.ai .bubble.typing::after{content:"▋";animation:blink 1s steps(1) infinite;color:var(--pink)}
@keyframes blink{50%{opacity:0}}
.msg.err .bubble{background:#ffe8e8;border-color:#ffb3b3;color:#c0392b}
footer{flex:0 0 auto;padding:10px 12px calc(12px + env(safe-area-inset-bottom));
background:rgba(255,255,255,.8);backdrop-filter:blur(12px);border-top:1px solid var(--line)}
.input-bar{display:flex;gap:10px;align-items:flex-end}
textarea{flex:1;resize:none;border:1px solid var(--line);border-radius:18px;padding:12px 16px;
font-size:15px;font-family:inherit;max-height:120px;min-height:46px;outline:none;background:#fff;color:var(--fg)}
textarea:focus{border-color:var(--pink);box-shadow:0 0 0 3px rgba(255,126,179,.15)}
.send-btn{width:46px;height:46px;border:none;border-radius:50%;cursor:pointer;flex:0 0 auto;
background:linear-gradient(135deg,var(--pink),var(--purple));color:#fff;font-size:20px;
display:flex;align-items:center;justify-content:center;box-shadow:0 4px 14px rgba(143,107,255,.4);transition:.15s}
.send-btn:active{transform:scale(.92)}
.send-btn:disabled{opacity:.5}
/* 设置面板 */
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
.field textarea{min-height:110px;line-height:1.5}
.field .hint{font-size:11px;color:var(--dim);margin-top:4px}
.preset-row{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px}
.preset-chip{padding:5px 12px;border-radius:999px;border:1px solid var(--line);font-size:12px;cursor:pointer;background:#fff;transition:.15s}
.preset-chip.active{background:linear-gradient(135deg,var(--pink),var(--purple));color:#fff;border:none}
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
    <div class="sub">猫娘 AI 陪伴助手</div>
  </div>
  <button class="icon-btn" id="btnSettings" title="设置">⚙️</button>
</header>
<main id="chatBox"></main>
<footer>
  <div class="hint-banner" id="setupHint" style="display:none">
    🐾 还没配置 API 哦～ 点右上角 ⚙️ 填一下 API Key 就能开聊喵！
  </div>
  <div class="input-bar">
    <textarea id="input" placeholder="跟喵酱说点什么…（Enter 发送 / Shift+Enter 换行）"></textarea>
    <button class="send-btn" id="btnSend">➤</button>
  </div>
</footer>

<div class="overlay" id="settings">
  <div class="sheet">
    <h2>⚙️ 设置</h2>
    <div class="field">
      <label>API 服务商</label>
      <div class="preset-row" id="presetRow"></div>
    </div>
    <div class="field">
      <label>API Base URL</label>
      <input id="cfgBaseUrl" placeholder="https://api.deepseek.com/v1">
      <div class="hint">OpenAI 兼容接口地址，以 /v1 结尾</div>
    </div>
    <div class="field">
      <label>API Key</label>
      <input id="cfgApiKey" type="password" placeholder="sk-...">
    </div>
    <div class="field">
      <label>模型</label>
      <input id="cfgModel" placeholder="deepseek-chat">
    </div>
    <div class="field">
      <label>人设提示词（可自由修改）</label>
      <textarea id="cfgPrompt"></textarea>
    </div>
    <div class="field">
      <label>温度：<span id="tempVal">0.8</span>（越低越严谨，越高越活泼）</label>
      <input id="cfgTemp" type="range" min="0" max="1.5" step="0.1" value="0.8" style="width:100%">
    </div>
    <button class="btn-primary" id="btnSave">💾 保存并开聊</button>
    <button class="btn-danger" id="btnClear">🗑️ 清空对话记录</button>
  </div>
</div>

<script>
const PRESETS=[
{name:"DeepSeek",base_url:"https://api.deepseek.com/v1",model:"deepseek-chat"},
{name:"OpenAI",base_url:"https://api.openai.com/v1",model:"gpt-4o-mini"},
{name:"Kimi",base_url:"https://api.moonshot.cn/v1",model:"moonshot-v1-8k"},
{name:"通义",base_url:"https://dashscope.aliyuncs.com/compatible-mode/v1",model:"qwen-plus"},
{name:"GLM",base_url:"https://open.bigmodel.cn/api/paas/v4",model:"glm-4-flash"},
{name:"硅基流动",base_url:"https://api.siliconflow.cn/v1",model:"deepseek-ai/DeepSeek-V3"},
{name:"自定义",base_url:"",model:""}];
const $=id=>document.getElementById(id);
let cfg=null,history=[],busy=false;

async function api(path,opts){const r=await fetch(path,opts);if(!r.ok)throw new Error("HTTP "+r.status);return r.json()}

async function loadCfg(){
  cfg=await api("/api/config");
  $("cfgBaseUrl").value=cfg.base_url||"";
  $("cfgApiKey").value=cfg.api_key||"";
  $("cfgModel").value=cfg.model||"";
  $("cfgPrompt").value=cfg.prompt||"";
  $("cfgTemp").value=cfg.temperature||0.8;
  $("tempVal").textContent=cfg.temperature||0.8;
  const cur=cfg.base_url||"";
  PRESETS.forEach((p,i)=>{
    const chip=document.createElement("div");
    chip.className="preset-chip"+(p.base_url&&cur.startsWith(p.base_url.split("/")[2])?" active":"");
    chip.textContent=p.name;
    chip.onclick=()=>{
      $("cfgBaseUrl").value=p.base_url; $("cfgModel").value=p.model;
      document.querySelectorAll(".preset-chip").forEach(c=>c.classList.remove("active"));
      chip.classList.add("active");
    };
    $("presetRow").appendChild(chip);
  });
  $("setupHint").style.display=cfg.api_key?"none":"block";
}

function addMsg(role,text){
  const box=$("chatBox");
  const wrap=document.createElement("div");
  wrap.className="msg "+role;
  wrap.innerHTML='<div class="avatar">'+(role==="ai"?"🐱":"🐰")+'</div><div class="bubble"></div>';
  const b=wrap.querySelector(".bubble");
  b.textContent=text;
  box.appendChild(wrap);box.scrollTop=box.scrollHeight;
  return {wrap,b};
}

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
  let acc="";
  try{
    const r=await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({messages:history})});
    const reader=r.body.getReader();const dec=new TextDecoder();
    let buf="";
    while(true){
      const {done,value}=await reader.read();
      if(done)break;
      buf+=dec.decode(value,{stream:true});
      const parts=buf.split("\n\n");buf=parts.pop();
      for(const p of parts){
        if(!p.startsWith("data:"))continue;
        try{
          const obj=JSON.parse(p.slice(5).trim());
          if(obj.error){ai.b=(ai.bubble.textContent||"")+"\n[错误] "+obj.error;continue}
          acc+=obj.content||"";
          ai.bubble.textContent=acc;ai.wrap.scrollIntoView({behavior:"smooth",block:"end"});
        }catch(e){}
      }
    }
    ai.wrap.classList.remove("typing");
    if(!acc)ai.bubble.textContent="(喵？没有收到回复，检查一下 API 设置喵…)";
    history.push({role:"assistant",content:acc||"(空回复)"});
  }catch(e){
    ai.wrap.classList.remove("typing");
    ai.bubble.textContent="[连接失败] "+e.message+"\n喵酱连不上服务器了呜…";
    history.push({role:"assistant",content:"[连接失败] "+e.message});
  }
  busy=false;$("btnSend").disabled=false;
}

$("btnSend").onclick=send;
$("input").addEventListener("keydown",e=>{
  if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}
  autoGrow();
});
function autoGrow(){const t=$("input");t.style.height="auto";t.style.height=Math.min(t.scrollHeight,120)+"px"}

$("btnSettings").onclick=()=>{$("settings").classList.add("show")};
$("settings").addEventListener("click",e=>{if(e.target===$("settings"))$("settings").classList.remove("show")});
$("cfgTemp").oninput=()=>$("tempVal").textContent=$("cfgTemp").value;
$("btnSave").onclick=async()=>{
  try{
    cfg={base_url:$("cfgBaseUrl").value.trim(),api_key:$("cfgApiKey").value.trim(),
         model:$("cfgModel").value.trim(),prompt:$("cfgPrompt").value,temperature:parseFloat($("cfgTemp").value)};
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
addMsg("ai","喵～主人好！我是喵酱 🐱 一只来自猫星的猫娘 AI 助理。\n写代码、翻译、查资料、聊天、听你吐槽……都可以找喵酱哦！\n（右上角 ⚙️ 可以设置/修改 API）");
</script>
</body>
</html>"""

# ---------------- HTTP 服务 ----------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="text/plain; charset=utf-8", extra=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            self._send(200, HTML, "text/html; charset=utf-8")
        elif self.path.split("?")[0] == "/api/config":
            self._send(200, json.dumps(load_config(), ensure_ascii=False), "application/json; charset=utf-8")
        else:
            self._send(404, "Not Found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        path = self.path.split("?")[0]
        if path == "/api/config":
            try:
                cfg = json.loads(raw)
                save_config(cfg)
                self._send(200, json.dumps({"ok": True}))
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}))
        elif path == "/api/chat":
            try:
                body = json.loads(raw)
                history = body.get("messages", [])
                cfg = load_config()
                if not cfg.get("api_key"):
                    self._send(401, json.dumps({"error": "请先配置 API Key"}))
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                for chunk in chat_stream_yield(cfg, history):
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
    print("   🐱  喵酱 Chat 已启动")
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
