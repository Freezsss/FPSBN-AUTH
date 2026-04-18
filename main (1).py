"""
FPSBN-AUTH Server - Railway
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import json, os

app = Flask(__name__)
CORS(app)

DB_FILE = "auth_db.json"
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "change_moi_2024")


def load_codes():
    codes = {}
    for key, value in os.environ.items():
        if key.startswith("CODE_"):
            code_name = key[5:].lower().strip()
            parts = value.split(":")
            if len(parts) >= 3:
                banner    = parts[0].strip()
                theme     = parts[1].strip()
                exclusive = parts[2].strip().lower() == "true"
            elif len(parts) == 2:
                banner, theme = parts[0].strip(), parts[1].strip()
                exclusive = True
            elif len(parts) == 1:
                banner = theme = parts[0].strip()
                exclusive = True
            else:
                continue
            codes[code_name] = {"exclusive": exclusive, "banner": banner, "theme": theme}
    return codes


def read_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def write_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)


@app.route("/check", methods=["GET"])
def check():
    code = request.args.get("code", "").lower().strip()
    hwid = request.args.get("hwid", "").strip()
    if not code or not hwid:
        return jsonify({"ok": False, "reason": "missing_params"}), 400
    CODES = load_codes()
    if code not in CODES:
        return jsonify({"ok": False, "reason": "invalid_code"}), 200
    code_def = CODES[code]
    if not code_def["exclusive"]:
        return jsonify({"ok": True, "status": "guest", "banner": code_def["banner"], "theme": code_def["theme"]})
    db = read_db()
    locked = db.get(code)
    if locked is None:
        return jsonify({"ok": True, "status": "available", "banner": code_def["banner"], "theme": code_def["theme"]})
    elif locked == hwid:
        return jsonify({"ok": True, "status": "owner", "banner": code_def["banner"], "theme": code_def["theme"]})
    else:
        return jsonify({"ok": False, "reason": "taken"}), 200


@app.route("/claim", methods=["POST"])
def claim():
    data = request.get_json(force=True, silent=True) or {}
    code = str(data.get("code", "")).lower().strip()
    hwid = str(data.get("hwid", "")).strip()
    if not code or not hwid:
        return jsonify({"ok": False, "reason": "missing_params"}), 400
    CODES = load_codes()
    if code not in CODES:
        return jsonify({"ok": False, "reason": "invalid_code"}), 200
    code_def = CODES[code]
    if not code_def["exclusive"]:
        return jsonify({"ok": True, "status": "guest"})
    db = read_db()
    locked = db.get(code)
    if locked is None:
        db[code] = hwid
        write_db(db)
        return jsonify({"ok": True, "status": "claimed"})
    elif locked == hwid:
        return jsonify({"ok": True, "status": "already_owner"})
    else:
        return jsonify({"ok": False, "reason": "taken"})


@app.route("/status", methods=["GET"])
def status():
    secret = request.args.get("secret", "")
    if secret != ADMIN_SECRET:
        return jsonify({"ok": False, "reason": "unauthorized"}), 401
    CODES = load_codes()
    db = read_db()
    result = {}
    for code, info in CODES.items():
        locked = db.get(code)
        result[code] = {
            "exclusive": info["exclusive"],
            "locked_by": locked if locked else None,
            "available": locked is None or not info["exclusive"],
        }
    return jsonify({"ok": True, "codes": result})


@app.route("/reset", methods=["POST"])
def reset():
    data = request.get_json(force=True, silent=True) or {}
    secret = str(data.get("secret", ""))
    code   = str(data.get("code", "")).lower().strip()
    if secret != ADMIN_SECRET:
        return jsonify({"ok": False, "reason": "unauthorized"}), 401
    CODES = load_codes()
    if code not in CODES:
        return jsonify({"ok": False, "reason": "invalid_code"}), 200
    db = read_db()
    if code in db:
        del db[code]
        write_db(db)
        return jsonify({"ok": True, "msg": f"Code '{code}' reset."})
    else:
        return jsonify({"ok": True, "msg": f"Code '{code}' etait deja libre."})


@app.route("/admin", methods=["GET"])
def admin():
    secret = request.args.get("secret", "")
    if secret != ADMIN_SECRET:
        return Response("Acces refuse.", status=401, mimetype="text/plain")
    html = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FPSBN-AUTH — Admin</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  :root{--bg:#080b10;--surface:#0d1117;--border:#1a2332;--accent:#00e5ff;--accent2:#ff3c6e;--green:#00ff88;--yellow:#ffe000;--text:#c9d1d9;--dim:#4a5568;--glow:0 0 20px rgba(0,229,255,0.3)}
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;min-height:100vh;overflow-x:hidden}
  body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(0,229,255,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(0,229,255,0.03) 1px,transparent 1px);background-size:40px 40px;pointer-events:none;z-index:0}
  .container{position:relative;z-index:1;max-width:900px;margin:0 auto;padding:40px 20px}
  header{display:flex;align-items:center;gap:16px;margin-bottom:40px;padding-bottom:24px;border-bottom:1px solid var(--border)}
  .logo{width:48px;height:48px;border:2px solid var(--accent);display:flex;align-items:center;justify-content:center;font-family:'Share Tech Mono',monospace;font-size:18px;color:var(--accent);box-shadow:var(--glow);animation:pulse 3s ease-in-out infinite}
  @keyframes pulse{0%,100%{box-shadow:var(--glow)}50%{box-shadow:0 0 40px rgba(0,229,255,0.5)}}
  .header-text h1{font-size:28px;font-weight:700;letter-spacing:4px;color:#fff;text-transform:uppercase}
  .header-text p{font-family:'Share Tech Mono',monospace;font-size:11px;color:var(--dim);letter-spacing:2px;margin-top:2px}
  .status-dot{margin-left:auto;display:flex;align-items:center;gap:8px;font-family:'Share Tech Mono',monospace;font-size:11px}
  .dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);animation:blink 2s infinite}
  @keyframes blink{0%,100%{opacity:1}50%{opacity:0.4}}
  .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:32px}
  .stat-card{background:var(--surface);border:1px solid var(--border);padding:20px;text-align:center}
  .stat-value{font-family:'Share Tech Mono',monospace;font-size:32px;font-weight:700;line-height:1;margin-bottom:6px}
  .stat-label{font-size:11px;letter-spacing:2px;color:var(--dim);text-transform:uppercase}
  .stat-value.green{color:var(--green)}.stat-value.red{color:var(--accent2)}.stat-value.cyan{color:var(--accent)}
  .section-title{font-family:'Share Tech Mono',monospace;font-size:11px;letter-spacing:3px;color:var(--accent);text-transform:uppercase;margin-bottom:16px;display:flex;align-items:center;gap:12px}
  .section-title::after{content:'';flex:1;height:1px;background:var(--border)}
  .codes-grid{display:flex;flex-direction:column;gap:8px;margin-bottom:32px}
  .code-row{background:var(--surface);border:1px solid var(--border);padding:16px 20px;display:flex;align-items:center;gap:16px;transition:border-color 0.2s}
  .code-row:hover{border-color:var(--dim)}
  .code-row.taken{border-left:3px solid var(--accent2)}.code-row.free{border-left:3px solid var(--green)}.code-row.guest{border-left:3px solid var(--yellow)}
  .code-name{font-family:'Share Tech Mono',monospace;font-size:16px;color:#fff;min-width:100px;font-weight:700;letter-spacing:2px}
  .code-badge{font-family:'Share Tech Mono',monospace;font-size:10px;padding:3px 8px;letter-spacing:1px;border:1px solid}
  .badge-free{color:var(--green);border-color:var(--green)}.badge-taken{color:var(--accent2);border-color:var(--accent2)}.badge-guest{color:var(--yellow);border-color:var(--yellow)}
  .code-hwid{font-family:'Share Tech Mono',monospace;font-size:11px;color:var(--dim);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .code-hwid.taken{color:var(--text)}
  .btn{padding:8px 16px;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:12px;letter-spacing:2px;text-transform:uppercase;cursor:pointer;border:none;transition:all 0.2s}
  .btn-danger{background:transparent;color:var(--accent2);border:1px solid var(--accent2)}
  .btn-danger:hover{background:var(--accent2);color:#fff;box-shadow:0 0 16px rgba(255,60,110,0.4)}
  .btn-refresh{background:transparent;color:var(--accent);border:1px solid var(--accent);padding:10px 20px;font-size:13px}
  .btn-refresh:hover{box-shadow:var(--glow)}
  .toolbar{display:flex;gap:12px;margin-bottom:16px;align-items:center}
  .config-box{background:var(--surface);border:1px solid var(--border);padding:24px;margin-bottom:32px}
  .config-row{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:end}
  .input-group{display:flex;flex-direction:column;gap:8px}
  label{font-size:11px;letter-spacing:2px;color:var(--dim);text-transform:uppercase;font-family:'Share Tech Mono',monospace}
  input[type=text]{background:var(--bg);border:1px solid var(--border);color:var(--text);padding:12px 16px;font-family:'Share Tech Mono',monospace;font-size:13px;width:100%;outline:none;transition:border-color 0.2s}
  input:focus{border-color:var(--accent)}
  #notif{position:fixed;bottom:24px;right:24px;z-index:100;display:flex;flex-direction:column;gap:8px}
  .notif-item{padding:12px 20px;font-family:'Share Tech Mono',monospace;font-size:12px;letter-spacing:1px;animation:slideIn 0.3s ease;max-width:300px}
  @keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
  .notif-success{background:var(--green);color:#000}.notif-error{background:var(--accent2);color:#fff}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo">F</div>
    <div class="header-text">
      <h1>FPSBN-AUTH</h1>
      <p>// PANNEAU ADMINISTRATION</p>
    </div>
    <div class="status-dot">
      <div class="dot"></div>
      <span style="color:var(--green)">ONLINE</span>
    </div>
  </header>

  <div class="stats">
    <div class="stat-card"><div class="stat-value cyan" id="stat-total">—</div><div class="stat-label">Codes Total</div></div>
    <div class="stat-card"><div class="stat-value red" id="stat-taken">—</div><div class="stat-label">Utilisés</div></div>
    <div class="stat-card"><div class="stat-value green" id="stat-free">—</div><div class="stat-label">Disponibles</div></div>
  </div>

  <div class="section-title">Codes d'accès</div>
  <div class="toolbar">
    <button class="btn btn-refresh" onclick="loadCodes()">↻ ACTUALISER</button>
    <span id="last-update" style="font-family:'Share Tech Mono',monospace;font-size:11px;color:var(--dim);margin-left:auto;"></span>
  </div>
  <div class="codes-grid" id="codes-grid"></div>

  <div class="section-title">Reset manuel</div>
  <div class="config-box">
    <p style="font-size:13px;color:var(--dim);margin-bottom:16px;font-family:'Share Tech Mono',monospace;">Libère un code pour qu'une autre personne puisse l'utiliser.</p>
    <div class="config-row">
      <div class="input-group">
        <label>Nom du code</label>
        <input type="text" id="reset-code" placeholder="ex: freez1x">
      </div>
      <button class="btn btn-danger" onclick="resetCode()" style="padding:12px 24px;font-size:14px;">RESET</button>
    </div>
  </div>
</div>
<div id="notif"></div>

<script>
  const SECRET = new URLSearchParams(window.location.search).get('secret') || '';

  function notify(msg, type='success'){
    const n=document.createElement('div');
    n.className=`notif-item notif-${type}`;
    n.textContent=msg;
    document.getElementById('notif').appendChild(n);
    setTimeout(()=>n.remove(),3500);
  }

  function renderCodes(codes){
    const grid=document.getElementById('codes-grid');
    grid.innerHTML='';
    let total=0,taken=0,free=0;
    for(const [name,info] of Object.entries(codes)){
      total++;
      const isTaken=info.locked_by!==null&&info.exclusive;
      const isGuest=!info.exclusive;
      if(isTaken)taken++; else if(!isGuest)free++;
      const rowClass=isGuest?'guest':isTaken?'taken':'free';
      const badgeClass=isGuest?'badge-guest':isTaken?'badge-taken':'badge-free';
      const badgeText=isGuest?'INVITÉ':isTaken?'UTILISÉ':'LIBRE';
      const hwidText=isTaken?info.locked_by:isGuest?'Accès libre':'—';
      grid.innerHTML+=`
        <div class="code-row ${rowClass}">
          <div class="code-name">${name.toUpperCase()}</div>
          <div class="code-badge ${badgeClass}">${badgeText}</div>
          <div class="code-hwid ${isTaken?'taken':''}" title="${hwidText}">${hwidText}</div>
          ${!isGuest&&isTaken?`<button class="btn btn-danger" onclick="resetByName('${name}')">RESET</button>`:''}
        </div>`;
    }
    document.getElementById('stat-total').textContent=total;
    document.getElementById('stat-taken').textContent=taken;
    document.getElementById('stat-free').textContent=free;
    const now=new Date();
    document.getElementById('last-update').textContent='Mis à jour '+now.toLocaleTimeString('fr-FR');
  }

  async function loadCodes(){
    try{
      const res=await fetch(`/status?secret=${encodeURIComponent(SECRET)}`);
      const data=await res.json();
      if(data.ok){renderCodes(data.codes);notify('Actualisé !','success');}
      else notify('Erreur auth.','error');
    }catch(e){notify('Erreur connexion.','error');}
  }

  async function resetByName(code){
    if(!confirm(`Reset le code "${code}" ?`))return;
    await doReset(code);
  }

  async function resetCode(){
    const code=document.getElementById('reset-code').value.trim().toLowerCase();
    if(!code){notify('Entre un nom de code.','error');return;}
    if(!confirm(`Reset le code "${code}" ?`))return;
    await doReset(code);
    document.getElementById('reset-code').value='';
  }

  async function doReset(code){
    try{
      const res=await fetch('/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({secret:SECRET,code})});
      const data=await res.json();
      if(data.ok){notify(`Code "${code}" resetté !`,'success');await loadCodes();}
      else notify(`Erreur : ${data.reason}`,'error');
    }catch(e){notify('Erreur connexion.','error');}
  }

  loadCodes();
</script>
</body>
</html>"""
    return Response(html, mimetype="text/html")


@app.route("/", methods=["GET"])
def health():
    CODES = load_codes()
    return jsonify({"ok": True, "service": "FPSBN-AUTH", "version": "2.0", "codes_actifs": len(CODES)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
