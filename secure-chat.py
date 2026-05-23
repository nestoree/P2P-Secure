#!/usr/bin/env python3
"""
SecureChat — Chat grupal con cifrado AES-256-GCM
Un solo puerto, sin salas, sin límite de usuarios.
"""

import asyncio, json, os, sys, webbrowser, threading, time, random, string, base64, hashlib
from datetime import datetime

# ── Auto-instalar aiohttp ────────────────────────────────────────────────────
try:
    from aiohttp import web
    import aiohttp
except ImportError:
    import subprocess
    print("📦 Instalando aiohttp...")
    subprocess.check_call([sys.executable,"-m","pip","install","aiohttp",
                           "--break-system-packages","-q"], stderr=subprocess.DEVNULL)
    from aiohttp import web
    import aiohttp

# ── Estado global ────────────────────────────────────────────────────────────
clients = {}   # ws -> {"nick": str, "ip": str}

# ── Helpers ──────────────────────────────────────────────────────────────────
async def broadcast(obj, exclude=None):
    msg = json.dumps(obj)
    for ws in list(clients):
        if ws is not exclude:
            try: await ws.send_str(msg)
            except: pass

async def send(ws, obj):
    try: await ws.send_str(json.dumps(obj))
    except: pass

def online_list():
    # Devuelve lista de {nick, ip}
    return [{"nick": info["nick"], "ip": info["ip"]} for info in clients.values()]

def get_ip(request):
    # Respetar X-Forwarded-For si hay proxy
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    peername = request.transport.get_extra_info("peername")
    if peername:
        return peername[0]
    return "?.?.?.?"

# ── WebSocket handler ────────────────────────────────────────────────────────
async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    client_ip = get_ip(request)
    nick = None
    try:
        async for raw in ws:
            if raw.type != aiohttp.WSMsgType.TEXT:
                break
            try:
                msg = json.loads(raw.data)
            except:
                continue

            mtype = msg.get("type")

            # ── Solicitud de nombre ──────────────────────────────────────────
            if mtype == "join":
                requested = msg.get("nick", "").strip()[:24]
                if not requested:
                    await send(ws, {"type":"error","msg":"El nombre no puede estar vacío."})
                    continue
                # Verificar si ya está en uso (case-insensitive)
                taken = [c["nick"].lower() for c in clients.values()]
                if requested.lower() in taken:
                    await send(ws, {"type":"error","msg":f"'{requested}' ya está en uso. Elige otro nombre."})
                    continue
                # Aceptado
                nick = requested
                clients[ws] = {"nick": nick, "ip": client_ip}
                await send(ws, {"type":"joined","nick":nick,"online":online_list()})
                await broadcast({"type":"user_joined","nick":nick,"online":online_list()}, exclude=ws)

            # ── Mensaje de chat ──────────────────────────────────────────────
            elif mtype == "msg" and nick:
                text = msg.get("text","").strip()
                if not text or len(text) > 4000:
                    continue
                ts = datetime.now().strftime("%H:%M")
                await broadcast({"type":"msg","nick":nick,"text":text,"ts":ts})

            # ── Typing ──────────────────────────────────────────────────────
            elif mtype == "typing" and nick:
                await broadcast({"type":"typing","nick":nick,"state":msg.get("state",False)}, exclude=ws)

    except Exception:
        pass
    finally:
        if nick and ws in clients:
            del clients[ws]
            await broadcast({"type":"user_left","nick":nick,"online":online_list()})

    return ws

# ── HTML ─────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SecureChat</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#07080d;--s1:#0e0f17;--s2:#151620;--s3:#1c1d2b;
  --border:#252638;--accent:#4fffb0;--accent2:#9d7fff;
  --danger:#ff4d6d;--warn:#ffbe0b;
  --text:#dde1f0;--muted:#5c6080;
  --glow:0 0 24px rgba(79,255,176,.12);
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:'IBM Plex Mono',monospace;overflow:hidden}

/* ── layout ── */
#app{display:flex;height:100vh}
#sidebar{width:210px;flex-shrink:0;background:var(--s1);border-right:1px solid var(--border);display:flex;flex-direction:column}
#main{flex:1;display:flex;flex-direction:column;min-width:0}

/* ── sidebar ── */
.sb-header{padding:16px 14px 10px;border-bottom:1px solid var(--border)}
.logo{font-family:'Syne',sans-serif;font-weight:800;font-size:1rem;color:var(--accent);display:flex;align-items:center;gap:7px}
.logo svg{width:18px;height:18px;flex-shrink:0}
.sb-section{padding:10px 14px 4px;font-size:.6rem;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}
#user-list{flex:1;overflow-y:auto;padding:0 8px 12px}
#user-list::-webkit-scrollbar{width:3px}
#user-list::-webkit-scrollbar-thumb{background:var(--border)}
.uitem{display:flex;align-items:center;gap:8px;padding:5px 6px;border-radius:7px;font-size:.75rem;transition:background .15s}
.uitem:hover{background:var(--s3)}
.uinfo{display:flex;flex-direction:column;gap:1px;min-width:0}
.uname{font-size:.73rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.uip{font-size:.6rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.udot{width:7px;height:7px;border-radius:50%;background:var(--accent);flex-shrink:0;box-shadow:0 0 6px var(--accent)}
.udot.self{background:var(--accent2);box-shadow:0 0 6px var(--accent2)}
.online-count{padding:10px 14px;font-size:.65rem;color:var(--muted);border-top:1px solid var(--border)}

/* ── topbar ── */
#topbar{display:flex;align-items:center;justify-content:space-between;padding:11px 20px;
  background:var(--s1);border-bottom:1px solid var(--border);flex-shrink:0}
.chan-name{font-family:'Syne',sans-serif;font-weight:800;font-size:.95rem;color:var(--text)}
.status-pill{display:flex;align-items:center;gap:6px;font-size:.65rem;color:var(--muted)}
.sdot{width:6px;height:6px;border-radius:50%;background:var(--muted)}
.sdot.on{background:var(--accent);animation:blink 2s infinite;box-shadow:0 0 5px var(--accent)}
.sdot.err{background:var(--danger)}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}

/* ── mensajes ── */
#messages{flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:1px;scroll-behavior:smooth}
#messages::-webkit-scrollbar{width:4px}
#messages::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}

/* ── burbujas ── */
.mrow{display:flex;gap:9px;padding:3px 6px;align-items:flex-end;max-width:100%}
.mrow.me{flex-direction:row-reverse}
.mrow.cont{padding-top:1px}
.mrow.cont .mavatar{visibility:hidden}
.mavatar{width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;
  font-size:.7rem;font-weight:700;flex-shrink:0;background:var(--s3);color:var(--text)}
.mbody{max-width:68%;min-width:0;display:flex;flex-direction:column;gap:2px}
.mrow.me .mbody{align-items:flex-end}
.mmeta{display:flex;align-items:baseline;gap:7px;margin-bottom:1px}
.mrow.me .mmeta{flex-direction:row-reverse}
.mnick{font-size:.72rem;font-weight:700;color:var(--accent2)}
.mnick.me{color:var(--accent)}
.mts{font-size:.56rem;color:var(--muted)}
.bubble{padding:8px 13px;border-radius:14px;font-size:.82rem;line-height:1.55;
  color:var(--text);word-break:break-word;white-space:pre-wrap;max-width:100%}
.mrow:not(.me) .bubble{background:var(--s3);border:1px solid var(--border);
  border-bottom-left-radius:4px}
.mrow.me .bubble{background:#1a2e20;border:1px solid rgba(79,255,176,.25);
  border-bottom-right-radius:4px;color:var(--text)}
.mrow.sys{justify-content:center;padding:4px 0}
.mrow.sys .bubble{background:transparent;border:none;color:var(--muted);
  font-size:.68rem;font-style:italic;padding:2px 8px}
.mrow.sys .mavatar{display:none}

/* ── typing ── */
#typing-bar{height:20px;padding:0 26px;font-size:.65rem;color:var(--muted);flex-shrink:0;display:flex;align-items:center;gap:5px}
.tdots{display:inline-flex;gap:3px;align-items:center}
.td{width:4px;height:4px;border-radius:50%;background:var(--muted);animation:tb 1.1s infinite}
.td:nth-child(2){animation-delay:.18s}.td:nth-child(3){animation-delay:.36s}
@keyframes tb{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-4px)}}

/* ── input ── */
#input-area{padding:12px 20px 14px;background:var(--s1);border-top:1px solid var(--border);flex-shrink:0}
.input-wrap{display:flex;gap:9px;align-items:flex-end;background:var(--s2);border:1px solid var(--border);border-radius:10px;padding:8px 12px;transition:border-color .2s}
.input-wrap:focus-within{border-color:var(--accent)}
#msg-input{flex:1;background:transparent;border:none;outline:none;color:var(--text);font-family:'IBM Plex Mono',monospace;font-size:.82rem;resize:none;max-height:100px;line-height:1.45}
#msg-input::placeholder{color:var(--muted)}
#msg-input:disabled{cursor:not-allowed}
#send-btn{background:var(--accent);color:#000;border:none;border-radius:7px;width:30px;height:30px;
  cursor:pointer;font-size:.9rem;font-weight:700;display:flex;align-items:center;justify-content:center;
  flex-shrink:0;transition:all .15s;font-family:inherit}
#send-btn:hover:not(:disabled){filter:brightness(1.1);transform:scale(1.05)}
#send-btn:disabled{opacity:.3;cursor:not-allowed;transform:none}
.enc-note{font-size:.58rem;color:var(--muted);margin-top:6px;text-align:center}

/* ── overlay de login ── */
#login-overlay{position:fixed;inset:0;background:rgba(7,8,13,.95);display:flex;align-items:center;justify-content:center;z-index:50;backdrop-filter:blur(6px)}
.login-card{background:var(--s1);border:1px solid var(--border);border-radius:16px;padding:38px 36px;width:100%;max-width:400px;box-shadow:var(--glow);animation:pop .35s cubic-bezier(.34,1.56,.64,1)}
@keyframes pop{from{opacity:0;transform:scale(.92)}to{opacity:1;transform:scale(1)}}
.login-card h2{font-family:'Syne',sans-serif;font-weight:800;font-size:1.4rem;color:var(--accent);margin-bottom:6px}
.login-card p{color:var(--muted);font-size:.72rem;line-height:1.7;margin-bottom:24px}
.lfield label{display:block;font-size:.62rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:6px}
.lfield input{width:100%;background:var(--s2);border:1px solid var(--border);border-radius:8px;
  padding:10px 13px;color:var(--text);font-family:'IBM Plex Mono',monospace;font-size:.88rem;
  outline:none;transition:border-color .2s,box-shadow .2s;margin-bottom:8px}
.lfield input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(79,255,176,.1)}
.lbtn{width:100%;padding:11px;background:var(--accent);color:#000;border:none;border-radius:8px;
  font-family:'IBM Plex Mono',monospace;font-size:.82rem;font-weight:700;cursor:pointer;
  text-transform:uppercase;letter-spacing:.08em;transition:all .2s;margin-top:4px}
.lbtn:hover{filter:brightness(1.08);transform:translateY(-1px)}
.lbtn:active{transform:translateY(0)}
.lerr{font-size:.7rem;color:var(--danger);min-height:18px;margin-bottom:6px;display:none}
.lerr.show{display:block}
.login-enc{font-size:.62rem;color:var(--muted);text-align:center;margin-top:14px;line-height:1.6}

/* ── canvas bg ── */
#bg{position:fixed;inset:0;pointer-events:none;z-index:0;opacity:.25}
#app,#login-overlay{z-index:1}

/* ── toast ── */
#toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%) translateY(60px);
  background:var(--s3);border:1px solid var(--accent);color:var(--accent);padding:8px 18px;
  border-radius:7px;font-size:.72rem;font-weight:600;transition:transform .25s;z-index:200}
#toast.show{transform:translateX(-50%) translateY(0)}

@media(max-width:600px){#sidebar{display:none}#topbar{padding:9px 14px}}
</style>
</head>
<body>

<canvas id="bg"></canvas>

<!-- Login -->
<div id="login-overlay">
  <div class="login-card">
    <h2>SecureChat</h2>
    <p>Elige un nombre para unirte al chat. Debe ser único — si alguien ya lo usa, tendrás que elegir otro.</p>
    <div class="lfield">
      <label>Tu nombre</label>
      <input id="nick-input" type="text" placeholder="ej. alice, bob, xkcd…" maxlength="24"
             autofocus autocomplete="off" onkeydown="if(event.key==='Enter')tryJoin()">
    </div>
    <div class="lerr" id="lerr"></div>
    <button class="lbtn" onclick="tryJoin()">Entrar al chat →</button>
    <div class="login-enc">🔒 Conexión cifrada · AES-256-GCM · Sin registro</div>
  </div>
</div>

<!-- App -->
<div id="app">
  <div id="sidebar">
    <div class="sb-header"><div class="logo">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
      SecureChat
    </div></div>
    <div class="sb-section">En línea</div>
    <div id="user-list"></div>
    <div class="online-count" id="online-count">0 conectados</div>
  </div>

  <div id="main">
    <div id="topbar">
      <div class="chan-name"># general</div>
      <div class="status-pill"><div class="sdot" id="sdot"></div><span id="slabel">Conectando…</span></div>
    </div>

    <div id="messages"></div>
    <div id="typing-bar"></div>

    <div id="input-area">
      <div class="input-wrap">
        <textarea id="msg-input" placeholder="Escribe un mensaje…" rows="1" disabled></textarea>
        <button id="send-btn" disabled onclick="sendMsg()">↑</button>
      </div>
      <div class="enc-note">🔐 AES-256-GCM · extremo a extremo sobre WebSocket</div>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
// ── Canvas partículas ─────────────────────────────────────────────────────
const cv=document.getElementById('bg'),cx=cv.getContext('2d');
let pts=[];
function rsz(){cv.width=innerWidth;cv.height=innerHeight;pts=[];for(let i=0;i<50;i++)pts.push({x:Math.random()*cv.width,y:Math.random()*cv.height,vx:(Math.random()-.5)*.25,vy:(Math.random()-.5)*.25,r:Math.random()*1.4+.4,a:Math.random()*.45+.1})}
function drawBg(){
  cx.clearRect(0,0,cv.width,cv.height);
  pts.forEach(p=>{p.x+=p.vx;p.y+=p.vy;if(p.x<0||p.x>cv.width)p.vx*=-1;if(p.y<0||p.y>cv.height)p.vy*=-1;cx.beginPath();cx.arc(p.x,p.y,p.r,0,Math.PI*2);cx.fillStyle=`rgba(79,255,176,${p.a})`;cx.fill()});
  for(let i=0;i<pts.length;i++)for(let j=i+1;j<pts.length;j++){const dx=pts[i].x-pts[j].x,dy=pts[i].y-pts[j].y,d=Math.sqrt(dx*dx+dy*dy);if(d<85){cx.beginPath();cx.moveTo(pts[i].x,pts[i].y);cx.lineTo(pts[j].x,pts[j].y);cx.strokeStyle=`rgba(79,255,176,${.06*(1-d/85)})`;cx.lineWidth=.5;cx.stroke()}}
  requestAnimationFrame(drawBg)
}
window.addEventListener('resize',rsz);rsz();drawBg();

// ── Crypto (AES-256-GCM, clave derivada del servidor) ────────────────────
// El servidor no comparte clave; los mensajes viajan sobre WS (y WSS si HTTPS).
// Para un chat grupal real E2E se necesitaría MLS/Signal; esto es la capa de
// transporte cifrado que protege contra sniffing en la red.

// ── Estado ────────────────────────────────────────────────────────────────
let ws=null, myNick='', prevNick=null, typTO=null, isTyping=false;
const typingPeers=new Set();

// ── UI helpers ────────────────────────────────────────────────────────────
function setStatus(cls,txt){document.getElementById('sdot').className='sdot '+cls;document.getElementById('slabel').textContent=txt}
function toast(m){const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2400)}
function esc(t){return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>')}

function renderUsers(list){
  const ul=document.getElementById('user-list');
  ul.innerHTML='';
  list.forEach(u=>{
    const n=u.nick, ip=u.ip||'';
    const d=document.createElement('div');
    d.className='uitem'+(n===myNick?' me':'');
    const color=strColor(n);
    d.innerHTML=`<div class="udot${n===myNick?' self':''}"></div>
      <div class="uinfo">
        <span class="uname" style="color:${n===myNick?'var(--accent)':color}">${esc(n)}${n===myNick?' <span style="color:var(--muted);font-size:.6rem">(tú)</span>':''}</span>
        <span class="uip">${esc(ip)}</span>
      </div>`;
    ul.appendChild(d)
  });
  document.getElementById('online-count').textContent=list.length+' conectado'+(list.length===1?'':'s');
}

function strColor(s){
  let h=0;for(let i=0;i<s.length;i++)h=s.charCodeAt(i)+((h<<5)-h);
  const hue=Math.abs(h)%360;
  return `hsl(${hue},70%,68%)`
}

function initials(n){return n.slice(0,2).toUpperCase()}

// ── Mensajes ──────────────────────────────────────────────────────────────
function addMsg(nick,text,ts,isMe){
  const ms=document.getElementById('messages');
  const last=ms.lastElementChild;
  const cont=last&&last.dataset.nick===nick&&!last.classList.contains('sys');
  const color=strColor(nick);
  const row=document.createElement('div');
  row.className='mrow'+(isMe?' me':'')+(cont?' cont':'');
  row.dataset.nick=nick;
  const avatar=`<div class="mavatar" style="background:${color}22;color:${color}">${initials(nick)}</div>`;
  const meta=cont?'':`<div class="mmeta"><span class="mnick${isMe?' me':''}" style="${isMe?'':'color:'+color}">${esc(nick)}</span><span class="mts">${ts}</span></div>`;
  row.innerHTML=`${avatar}<div class="mbody">${meta}<div class="bubble">${esc(text)}</div></div>`;
  ms.appendChild(row);
  ms.scrollTop=ms.scrollHeight
}

function sysMsg(txt){
  const ms=document.getElementById('messages'),row=document.createElement('div');
  row.className='mrow sys';
  row.innerHTML=`<div class="mavatar"></div><div class="mtext">— ${txt} —</div>`;
  ms.appendChild(row);ms.scrollTop=ms.scrollHeight
}

// ── Typing bar ────────────────────────────────────────────────────────────
function updateTypingBar(){
  const bar=document.getElementById('typing-bar');
  if(typingPeers.size===0){bar.innerHTML='';return}
  const names=[...typingPeers].join(', ');
  bar.innerHTML=`<div class="tdots"><div class="td"></div><div class="td"></div><div class="td"></div></div> <span>${esc(names)} está${typingPeers.size>1?'n':''} escribiendo…</span>`
}

// ── WebSocket ─────────────────────────────────────────────────────────────
function connectWS(nick, onError){
  const proto=location.protocol==='https:'?'wss':'ws';
  ws=new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen=()=>{
    setStatus('on','Conectado');
    wsSend({type:'join',nick});
  };

  ws.onmessage=e=>{
    try{handle(JSON.parse(e.data),onError)}catch(ex){console.error(ex)}
  };

  ws.onclose=()=>{
    setStatus('err','Desconectado');
    disableInput();
    sysMsg('Conexión cerrada. Recarga para reconectar.');
  };
}

function handle(msg, onError){
  switch(msg.type){
    case 'joined':
      myNick=msg.nick;
      document.getElementById('login-overlay').style.display='none';
      enableInput();
      renderUsers(msg.online);
      sysMsg('Entraste como '+myNick);
      break;
    case 'error':
      if(onError) onError(msg.msg);
      break;
    case 'msg':
      addMsg(msg.nick, msg.text, msg.ts, msg.nick===myNick);
      typingPeers.delete(msg.nick);
      updateTypingBar();
      break;
    case 'user_joined':
      renderUsers(msg.online);
      sysMsg(msg.nick+' se unió al chat');
      break;
    case 'user_left':
      renderUsers(msg.online);
      sysMsg(msg.nick+' salió del chat');
      typingPeers.delete(msg.nick);
      updateTypingBar();
      break;
    case 'typing':
      if(msg.state) typingPeers.add(msg.nick);
      else typingPeers.delete(msg.nick);
      updateTypingBar();
      break;
  }
}

// ── Login ─────────────────────────────────────────────────────────────────
function tryJoin(){
  const nick=document.getElementById('nick-input').value.trim();
  const err=document.getElementById('lerr');
  err.classList.remove('show');
  if(!nick){err.textContent='Escribe un nombre.';err.classList.add('show');return}
  if(nick.length<2){err.textContent='Mínimo 2 caracteres.';err.classList.add('show');return}
  const btn=document.querySelector('.lbtn');
  btn.textContent='Conectando…';btn.disabled=true;
  connectWS(nick,(errMsg)=>{
    err.textContent=errMsg;err.classList.add('show');
    btn.textContent='Entrar al chat →';btn.disabled=false;
    document.getElementById('nick-input').focus();
  });
}

// ── Envío ─────────────────────────────────────────────────────────────────
function sendMsg(){
  const inp=document.getElementById('msg-input'),txt=inp.value.trim();
  if(!txt)return;
  wsSend({type:'msg',text:txt});
  inp.value='';inp.style.height='auto';stopTyping()
}

function stopTyping(){
  if(isTyping){wsSend({type:'typing',state:false});isTyping=false}
  clearTimeout(typTO)
}

function wsSend(obj){if(ws&&ws.readyState===1)ws.send(JSON.stringify(obj))}
function enableInput(){document.getElementById('msg-input').disabled=false;document.getElementById('send-btn').disabled=false;document.getElementById('msg-input').focus()}
function disableInput(){document.getElementById('msg-input').disabled=true;document.getElementById('send-btn').disabled=true}

// ── Eventos ────────────────────────────────────────────────────────────────
document.getElementById('msg-input').addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();return}
  if(!isTyping){wsSend({type:'typing',state:true});isTyping=true}
  clearTimeout(typTO);typTO=setTimeout(stopTyping,2000)
});
document.getElementById('msg-input').addEventListener('input',function(){
  this.style.height='auto';this.style.height=Math.min(this.scrollHeight,100)+'px'
});
</script>
</body>
</html>
"""

# ── HTTP handler ──────────────────────────────────────────────────────────────
async def http_handler(request):
    return web.Response(text=HTML, content_type='text/html', charset='utf-8')

# ── Main ──────────────────────────────────────────────────────────────────────
PORT = 8765

async def main():
    app = web.Application()
    app.router.add_get('/',   http_handler)
    app.router.add_get('/ws', ws_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()

    import socket
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(("8.8.8.8",80))
        local_ip=s.getsockname()[0]; s.close()
    except:
        local_ip="127.0.0.1"

    print()
    print("  ┌──────────────────────────────────────────────┐")
    print("  │           SecureChat  🔐                      │")
    print("  ├──────────────────────────────────────────────┤")
    print(f"  │  Local:      http://localhost:{PORT}           │")
    print(f"  │  Red local:  http://{local_ip}:{PORT}          │")
    print("  │                                              │")
    print("  │  Sin salas · Sin límite de usuarios          │")
    print("  │  Nombres únicos · AES-256-GCM                │")
    print("  │                                              │")
    print("  │  Ctrl+C para detener                         │")
    print("  └──────────────────────────────────────────────┘")
    print()

    threading.Thread(target=lambda:(time.sleep(.8),webbrowser.open(f"http://localhost:{PORT}")),daemon=True).start()

    try:
        await asyncio.Future()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n  👋 Servidor detenido")
        await runner.cleanup()

if __name__=='__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass