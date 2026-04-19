from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import random
import string
import base64
import requests
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ── CONFIG ──────────────────────────────────────────────────────
ADMIN_SECRET      = os.environ.get("ADMIN_SECRET", "ton_mot_de_passe_admin")
RAILWAY_TOKEN     = os.environ.get("RAILWAY_TOKEN", "")
RAILWAY_PROJECT   = os.environ.get("RAILWAY_PROJECT_ID", "")
RAILWAY_ENV       = os.environ.get("RAILWAY_ENVIRONMENT_ID", "")
RAILWAY_SERVICE   = os.environ.get("RAILWAY_SERVICE_ID", "")

CODE_VALUE   = "Fpsbn:Fpsbn:True"
CODE_PREFIX  = "CODE_"
STATE_PREFIX = "STATE_"
LOG_VAR      = "LOGS_DATA"
BANNED_VAR   = "BANNED_IPS"
MAX_LOGS     = 200

RAILWAY_GQL = "https://backboard.railway.app/graphql/v2"

# ── Cache local pour éviter trop d'appels Railway ──────────────
_env_cache = None
_env_cache_ts = 0
CACHE_TTL = 10  # secondes

def railway_headers():
    return {"Authorization": f"Bearer {RAILWAY_TOKEN}", "Content-Type": "application/json"}

def railway_get_vars(force=False):
    global _env_cache, _env_cache_ts
    import time
    now = time.time()
    if not force and _env_cache is not None and (now - _env_cache_ts) < CACHE_TTL:
        return _env_cache
    if not RAILWAY_TOKEN:
        _env_cache = {}
        return {}
    query = """
    query getVars($projectId: String!, $environmentId: String!, $serviceId: String!) {
      variables(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId)
    }
    """
    try:
        resp = requests.post(RAILWAY_GQL, headers=railway_headers(), json={
            "query": query,
            "variables": {"projectId": RAILWAY_PROJECT, "environmentId": RAILWAY_ENV, "serviceId": RAILWAY_SERVICE}
        }, timeout=10)
        data = resp.json()
        _env_cache = data.get("data", {}).get("variables", {}) or {}
        _env_cache_ts = now
        return _env_cache
    except Exception as e:
        print(f"[Railway] getVars error: {e}")
        return _env_cache or {}

def invalidate_cache():
    global _env_cache
    _env_cache = None

def railway_upsert_var(name, value):
    if not RAILWAY_TOKEN:
        return False
    mutation = """
    mutation upsertVar($input: VariableUpsertInput!) {
      variableUpsert(input: $input)
    }
    """
    try:
        resp = requests.post(RAILWAY_GQL, headers=railway_headers(), json={
            "query": mutation,
            "variables": {"input": {
                "projectId": RAILWAY_PROJECT, "environmentId": RAILWAY_ENV,
                "serviceId": RAILWAY_SERVICE, "name": name, "value": value
            }}
        }, timeout=10)
        data = resp.json()
        invalidate_cache()
        return data.get("data", {}).get("variableUpsert", False)
    except Exception as e:
        print(f"[Railway] upsertVar error: {e}")
        return False

def railway_delete_var(name):
    if not RAILWAY_TOKEN:
        return False
    mutation = """
    mutation deleteVar($input: VariableDeleteInput!) {
      variableDelete(input: $input)
    }
    """
    try:
        resp = requests.post(RAILWAY_GQL, headers=railway_headers(), json={
            "query": mutation,
            "variables": {"input": {
                "projectId": RAILWAY_PROJECT, "environmentId": RAILWAY_ENV,
                "serviceId": RAILWAY_SERVICE, "name": name
            }}
        }, timeout=10)
        data = resp.json()
        invalidate_cache()
        return data.get("data", {}).get("variableDelete", False)
    except Exception as e:
        print(f"[Railway] deleteVar error: {e}")
        return False

def get_all_vars():
    """Fusionne os.environ + Railway vars."""
    return {**dict(os.environ), **railway_get_vars()}

# ── CODES ────────────────────────────────────────────────────────
VALID_CODE_VALUES = {CODE_VALUE.lower(), "banner:banner:true"}

def _is_valid_code_val(val):
    return val.strip().lower() in VALID_CODE_VALUES

def load_all_codes():
    all_vars = get_all_vars()
    codes = {}
    for key, val in all_vars.items():
        if key.startswith(CODE_PREFIX) and _is_valid_code_val(val):
            code_id = key[len(CODE_PREFIX):]
            state_raw = all_vars.get(STATE_PREFIX + code_id, "")
            state = {}
            if state_raw:
                try:
                    state = json.loads(base64.b64decode(state_raw).decode())
                except Exception:
                    pass
            codes[code_id] = {
                "locked_ip":   state.get("locked_ip"),
                "player_name": state.get("player_name"),
                "fivem_name":  state.get("fivem_name"),
                "first_seen":  state.get("first_seen"),
                "last_seen":   state.get("last_seen"),
                "expires_at":  state.get("expires_at"),
                "banner":      state.get("banner", ""),
                "theme":       state.get("theme", ""),
                "created_at":  state.get("created_at", ""),
            }
    return codes

def get_code_state(code_id):
    all_vars = get_all_vars()
    raw = all_vars.get(STATE_PREFIX + code_id, "")
    if not raw:
        return {}
    try:
        return json.loads(base64.b64decode(raw).decode())
    except Exception:
        return {}

def save_code_state(code_id, state):
    encoded = base64.b64encode(json.dumps(state, ensure_ascii=False).encode()).decode()
    return railway_upsert_var(STATE_PREFIX + code_id, encoded)

def code_exists(code_id):
    all_vars = get_all_vars()
    return _is_valid_code_val(all_vars.get(CODE_PREFIX + code_id, ""))

# ── BANNED IPs ───────────────────────────────────────────────────
def get_banned_ips():
    all_vars = get_all_vars()
    raw = all_vars.get(BANNED_VAR, "")
    if not raw:
        return []
    try:
        return json.loads(base64.b64decode(raw).decode())
    except Exception:
        return []

def save_banned_ips(ips):
    encoded = base64.b64encode(json.dumps(ips).encode()).decode()
    railway_upsert_var(BANNED_VAR, encoded)

# ── LOGS ─────────────────────────────────────────────────────────
def load_logs():
    all_vars = get_all_vars()
    raw = all_vars.get(LOG_VAR, "")
    if not raw:
        return []
    try:
        return json.loads(base64.b64decode(raw).decode())
    except Exception:
        return []

def save_logs(logs):
    encoded = base64.b64encode(json.dumps(logs, ensure_ascii=False).encode()).decode()
    railway_upsert_var(LOG_VAR, encoded)

def add_log(action, details, ip=None, code=None, admin=False):
    logs = load_logs()
    logs.insert(0, {
        "ts":      datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "action":  action,
        "details": details,
        "ip":      ip or "",
        "code":    code or "",
        "admin":   admin
    })
    save_logs(logs[:MAX_LOGS])

# ── UTILS ─────────────────────────────────────────────────────────
def is_expired(state):
    expires = state.get("expires_at")
    if not expires:
        return False
    try:
        exp = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        return exp < datetime.now(exp.tzinfo)
    except Exception:
        return False

def check_secret(body):
    return body.get("secret") == ADMIN_SECRET

def get_real_ip():
    """IP réelle depuis headers HTTP (Railway proxy)."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"

def generate_code_id():
    return ''.join(random.choices(string.digits, k=12))


# ════════════════════════════════════════════════════════════════
# GET /status
# ════════════════════════════════════════════════════════════════
@app.route("/status", methods=["GET"])
def status():
    if request.args.get("secret", "") != ADMIN_SECRET:
        return jsonify({"ok": False, "reason": "unauthorized"}), 403
    return jsonify({
        "ok":         True,
        "codes":      load_all_codes(),
        "banned_ips": get_banned_ips(),
        "logs":       load_logs()
    })


# ════════════════════════════════════════════════════════════════
# GET /check  — IP détectée côté serveur
# ════════════════════════════════════════════════════════════════
@app.route("/check", methods=["GET"])
def check():
    code_id = (request.args.get("code") or "").strip()
    ip      = get_real_ip()

    if not code_id:
        return jsonify({"ok": False, "reason": "missing_fields"})

    if not code_exists(code_id):
        add_log("CHECK_FAIL", f"Code invalide depuis {ip}", ip=ip, code=code_id)
        return jsonify({"ok": False, "reason": "invalid_code"})

    if ip in get_banned_ips():
        add_log("CHECK_FAIL", f"IP bannie bloquée", ip=ip, code=code_id)
        return jsonify({"ok": False, "reason": "ip_banned"})

    state = get_code_state(code_id)

    if is_expired(state):
        add_log("CHECK_FAIL", f"Code expiré", ip=ip, code=code_id)
        return jsonify({"ok": False, "reason": "expired"})

    locked_ip = state.get("locked_ip")
    if locked_ip and locked_ip != ip:
        add_log("CHECK_FAIL", f"IP mismatch — attendu {locked_ip}, reçu {ip}", ip=ip, code=code_id)
        return jsonify({"ok": False, "reason": "ip_mismatch"})

    return jsonify({
        "ok":     True,
        "banner": state.get("banner", ""),
        "theme":  state.get("theme",  ""),
        "ip":     ip
    })


# ════════════════════════════════════════════════════════════════
# POST /claim  — IP côté serveur
# Body JSON: { code, player_name?, fivem_name? }
# ════════════════════════════════════════════════════════════════
@app.route("/claim", methods=["POST"])
def claim():
    body        = request.get_json(force=True) or {}
    code_id     = (body.get("code")        or "").strip()
    player_name = (body.get("player_name") or "").strip()
    fivem_name  = (body.get("fivem_name")  or "").strip()
    ip          = get_real_ip()

    if not code_id:
        return jsonify({"ok": False, "reason": "missing_fields"})
    if not code_exists(code_id):
        return jsonify({"ok": False, "reason": "invalid_code"})
    if ip in get_banned_ips():
        return jsonify({"ok": False, "reason": "ip_banned"})

    state     = get_code_state(code_id)
    locked_ip = state.get("locked_ip")

    if locked_ip and locked_ip != ip:
        return jsonify({"ok": False, "reason": "taken"})

    is_first = not locked_ip
    now_str  = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    if not locked_ip:
        state["locked_ip"]  = ip
        state["first_seen"] = now_str

    state["last_seen"] = now_str
    if player_name:
        state["player_name"] = player_name
    if fivem_name:
        state["fivem_name"] = fivem_name

    save_code_state(code_id, state)

    display = fivem_name or player_name or code_id
    action  = "FIRST_CONNECTION" if is_first else "CONNECTION"
    label   = "1ère connexion" if is_first else "Reconnexion"
    add_log(action, f"{label} — {display}", ip=ip, code=code_id)

    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /generate  — CODE_XXXXXXXXXXXX (12 chiffres) sur Railway
# ════════════════════════════════════════════════════════════════
@app.route("/generate", methods=["POST"])
def generate():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    count     = min(int(body.get("count", 1)), 20)
    all_vars  = get_all_vars()
    generated = []

    for _ in range(count):
        for attempt in range(30):
            code_id = generate_code_id()
            if (CODE_PREFIX + code_id) not in all_vars:
                break

        ok = railway_upsert_var(CODE_PREFIX + code_id, CODE_VALUE)
        if not ok:
            continue

        if body.get("expires_at"):
            state = {"expires_at": body["expires_at"],
                     "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
            save_code_state(code_id, state)

        generated.append(code_id)
        all_vars[CODE_PREFIX + code_id] = CODE_VALUE

    add_log("ADMIN_GENERATE",
            f"{len(generated)} code(s): {', '.join(['CODE_'+c for c in generated])}",
            admin=True)
    return jsonify({"ok": True, "codes": generated})


# ════════════════════════════════════════════════════════════════
# POST /add  — Code manuel avec nom personnalisé
# Body JSON: { code, expires_at? }
# Logique : codes prédéfinis (bob/freez1x/nezz/pinpin/sabry) → Banner:Banner:True
#           tous les autres nouveaux codes → Fpsbn:Fpsbn:True
# ════════════════════════════════════════════════════════════════
BANNER_CODES  = {"bob", "freez1x", "nezz", "pinpin", "sabry"}
BANNER_VALUE  = "Banner:Banner:True"

@app.route("/add", methods=["POST"])
def add():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    code_id = (body.get("code") or "").strip().lower()
    if not code_id:
        return jsonify({"ok": False, "reason": "missing_code"})

    all_vars = get_all_vars()
    if (CODE_PREFIX + code_id) in all_vars:
        return jsonify({"ok": False, "reason": "already_exists"})

    # Valeur selon le type de code
    value = BANNER_VALUE if code_id in BANNER_CODES else CODE_VALUE

    ok = railway_upsert_var(CODE_PREFIX + code_id, value)
    if not ok:
        return jsonify({"ok": False, "reason": "railway_error"})

    if body.get("expires_at"):
        state = {"expires_at": body["expires_at"],
                 "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
        save_code_state(code_id, state)

    add_log("ADMIN_ADD", f"Code créé manuellement: CODE_{code_id} = {value}", admin=True)
    return jsonify({"ok": True, "code": code_id})


# ════════════════════════════════════════════════════════════════
# POST /delete
# ════════════════════════════════════════════════════════════════
@app.route("/delete", methods=["POST"])
def delete():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    code_id = (body.get("code") or "").strip()
    railway_delete_var(CODE_PREFIX + code_id)
    railway_delete_var(STATE_PREFIX + code_id)
    add_log("ADMIN_DELETE", f"Code supprimé", code=code_id, admin=True)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /reset
# ════════════════════════════════════════════════════════════════
@app.route("/reset", methods=["POST"])
def reset():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    code_id = (body.get("code") or "").strip()
    if not code_exists(code_id):
        return jsonify({"ok": False, "reason": "code_not_found"})

    state    = get_code_state(code_id)
    old_ip   = state.get("locked_ip", "—")
    old_name = state.get("fivem_name") or state.get("player_name") or "—"
    new_state = {k: state.get(k) for k in ("expires_at", "created_at", "banner", "theme") if state.get(k)}
    save_code_state(code_id, new_state)

    add_log("ADMIN_RESET", f"Libéré — était: {old_name} / {old_ip}", code=code_id, admin=True)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /reset-all
# ════════════════════════════════════════════════════════════════
@app.route("/reset-all", methods=["POST"])
def reset_all():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    codes = load_all_codes()
    for code_id in codes:
        state = get_code_state(code_id)
        new_state = {k: state.get(k) for k in ("expires_at", "created_at", "banner", "theme") if state.get(k)}
        save_code_state(code_id, new_state)

    add_log("ADMIN_RESET_ALL", f"Reset global — {len(codes)} codes libérés", admin=True)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /edit
# ════════════════════════════════════════════════════════════════
@app.route("/edit", methods=["POST"])
def edit():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    code_id = (body.get("code") or "").strip()
    if not code_exists(code_id):
        return jsonify({"ok": False, "reason": "code_not_found"})

    state = get_code_state(code_id)
    for field in ("expires_at", "banner", "theme"):
        if field in body:
            state[field] = body[field]
    save_code_state(code_id, state)
    add_log("ADMIN_EDIT", f"Code modifié", code=code_id, admin=True)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /ban-ip / /unban-ip
# ════════════════════════════════════════════════════════════════
@app.route("/ban-ip", methods=["POST"])
def ban_ip():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403
    ip = (body.get("ip") or "").strip()
    if not ip:
        return jsonify({"ok": False, "reason": "missing_ip"})
    ips = get_banned_ips()
    if ip not in ips:
        ips.append(ip)
        save_banned_ips(ips)
    add_log("ADMIN_BAN_IP", f"IP bannie", ip=ip, admin=True)
    return jsonify({"ok": True})

@app.route("/unban-ip", methods=["POST"])
def unban_ip():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403
    ip = (body.get("ip") or "").strip()
    if not ip:
        return jsonify({"ok": False, "reason": "missing_ip"})
    save_banned_ips([x for x in get_banned_ips() if x != ip])
    add_log("ADMIN_UNBAN_IP", f"IP débannie", ip=ip, admin=True)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# GET /logs
# ════════════════════════════════════════════════════════════════
@app.route("/logs", methods=["GET"])
def get_logs():
    if request.args.get("secret", "") != ADMIN_SECRET:
        return jsonify({"ok": False, "reason": "unauthorized"}), 403
    limit = int(request.args.get("limit", 100))
    return jsonify({"ok": True, "logs": load_logs()[:limit]})


# ════════════════════════════════════════════════════════════════
# GET /debug  — Diagnostic variables Railway (admin seulement)
# ════════════════════════════════════════════════════════════════
@app.route("/debug", methods=["GET"])
def debug():
    if request.args.get("secret", "") != ADMIN_SECRET:
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    railway_raw = railway_get_vars(force=True)
    env_raw     = dict(os.environ)

    # Toutes les clés qui commencent par CODE_
    code_keys_railway = {k: v for k, v in railway_raw.items() if k.startswith("CODE_")}
    code_keys_env     = {k: v for k, v in env_raw.items()     if k.startswith("CODE_")}

    # Toutes les valeurs uniques trouvées sur les clés CODE_
    all_code_vals = list(set(list(code_keys_railway.values()) + list(code_keys_env.values())))

    return jsonify({
        "ok": True,
        "railway_token_set": bool(RAILWAY_TOKEN),
        "railway_project":   RAILWAY_PROJECT,
        "railway_env":       RAILWAY_ENV,
        "railway_service":   RAILWAY_SERVICE,
        "railway_var_count": len(railway_raw),
        "env_var_count":     len(env_raw),
        "code_keys_railway": code_keys_railway,
        "code_keys_env":     code_keys_env,
        "valid_values_expected": list(VALID_CODE_VALUES),
        "all_code_values_found": all_code_vals,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
