from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import random
import string
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ── CONFIG ──────────────────────────────────────────────────────
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "ton_mot_de_passe_admin")
DATA_FILE    = "codes.json"
LOG_FILE     = "logs.json"
MAX_LOGS     = 500  # max logs stockés


# ── PERSISTANCE CODES ────────────────────────────────────────────
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"codes": {}, "banned_ips": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {"codes": {}, "banned_ips": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── PERSISTANCE LOGS ─────────────────────────────────────────────
def load_logs():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []

def save_logs(logs):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def add_log(action, details, ip=None, code=None, admin=False):
    logs = load_logs()
    entry = {
        "ts":      datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "action":  action,
        "details": details,
        "ip":      ip or "",
        "code":    code or "",
        "admin":   admin
    }
    logs.insert(0, entry)
    if len(logs) > MAX_LOGS:
        logs = logs[:MAX_LOGS]
    save_logs(logs)


# ── UTILS ────────────────────────────────────────────────────────
def is_expired(entry):
    if not entry.get("expires_at"):
        return False
    try:
        exp = datetime.fromisoformat(entry["expires_at"].replace("Z", "+00:00"))
        return exp < datetime.now(exp.tzinfo)
    except Exception:
        return False

def check_secret(body):
    return body.get("secret") == ADMIN_SECRET

def generate_fpsbn_code():
    """Génère un code au format FPSBN:FPSBN:XXXX (lettres+chiffres aléatoires)"""
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"FPSBN:FPSBN:{suffix}"


# ════════════════════════════════════════════════════════════════
# GET /status  — Panneau admin
# ════════════════════════════════════════════════════════════════
@app.route("/status", methods=["GET"])
def status():
    secret = request.args.get("secret", "")
    if secret != ADMIN_SECRET:
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    data = load_data()
    logs = load_logs()
    return jsonify({
        "ok":         True,
        "codes":      data.get("codes", {}),
        "banned_ips": data.get("banned_ips", []),
        "logs":       logs
    })


# ════════════════════════════════════════════════════════════════
# GET /check  — Menu Lua : vérifie code + IP
# ════════════════════════════════════════════════════════════════
@app.route("/check", methods=["GET"])
def check():
    code      = (request.args.get("code") or "").strip().lower()
    ip        = (request.args.get("ip")   or "").strip()

    if not code or not ip:
        return jsonify({"ok": False, "reason": "missing_fields"})

    data  = load_data()
    entry = data["codes"].get(code)

    if entry is None:
        add_log("CHECK_FAIL", f"Code invalide tenté", ip=ip, code=code)
        return jsonify({"ok": False, "reason": "invalid_code"})

    if is_expired(entry):
        add_log("CHECK_FAIL", f"Code expiré", ip=ip, code=code)
        return jsonify({"ok": False, "reason": "expired"})

    if ip in data.get("banned_ips", []):
        add_log("CHECK_FAIL", f"IP bannie bloquée", ip=ip, code=code)
        return jsonify({"ok": False, "reason": "ip_banned"})

    locked_ip = entry.get("locked_ip")
    if locked_ip and locked_ip != ip:
        add_log("CHECK_FAIL", f"IP mismatch — attendu {locked_ip}", ip=ip, code=code)
        return jsonify({"ok": False, "reason": "ip_mismatch"})

    return jsonify({
        "ok":     True,
        "banner": entry.get("banner", ""),
        "theme":  entry.get("theme",  "")
    })


# ════════════════════════════════════════════════════════════════
# POST /claim  — Verrouille code sur IP + stocke nom FiveM + Rockstar
# Body JSON: { code, ip, player_name, fivem_name? }
# ════════════════════════════════════════════════════════════════
@app.route("/claim", methods=["POST"])
def claim():
    body        = request.get_json(force=True) or {}
    code        = (body.get("code")        or "").strip().lower()
    ip          = (body.get("ip")          or "").strip()
    player_name = (body.get("player_name") or "").strip()
    fivem_name  = (body.get("fivem_name")  or "").strip()

    if not code or not ip:
        return jsonify({"ok": False, "reason": "missing_fields"})

    data  = load_data()
    entry = data["codes"].get(code)

    if entry is None:
        return jsonify({"ok": False, "reason": "invalid_code"})

    locked_ip = entry.get("locked_ip")
    if locked_ip and locked_ip != ip:
        return jsonify({"ok": False, "reason": "taken"})

    if ip in data.get("banned_ips", []):
        return jsonify({"ok": False, "reason": "ip_banned"})

    is_first_connection = not locked_ip

    # Verrouiller l'IP à la première connexion
    if not locked_ip:
        entry["locked_ip"] = ip
        entry["first_seen"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Toujours mettre à jour les infos joueur
    entry["last_seen"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    if player_name:
        entry["player_name"] = player_name  # Nom Rockstar

    if fivem_name:
        entry["fivem_name"] = fivem_name    # Nom FiveM (tag serveur)

    save_data(data)

    display_name = fivem_name or player_name or code
    if is_first_connection:
        add_log("FIRST_CONNECTION", f"1ère connexion — {display_name} ({ip})", ip=ip, code=code)
    else:
        add_log("CONNECTION", f"Reconnexion — {display_name} ({ip})", ip=ip, code=code)

    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /reset  — Libérer un code
# ════════════════════════════════════════════════════════════════
@app.route("/reset", methods=["POST"])
def reset():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    code  = (body.get("code") or "").strip().lower()
    data  = load_data()
    entry = data["codes"].get(code)

    if entry is None:
        return jsonify({"ok": False, "reason": "code_not_found"})

    old_ip   = entry.get("locked_ip") or "—"
    old_name = entry.get("fivem_name") or entry.get("player_name") or "—"
    entry["locked_ip"]   = None
    entry["locked_by"]   = None
    entry["player_name"] = None
    entry["fivem_name"]  = None
    entry["first_seen"]  = None
    entry["last_seen"]   = None

    save_data(data)
    add_log("ADMIN_RESET", f"Code libéré (était: {old_name} / {old_ip})", code=code, admin=True)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /reset-all  — Libérer tous les codes
# ════════════════════════════════════════════════════════════════
@app.route("/reset-all", methods=["POST"])
def reset_all():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    data = load_data()
    count = 0
    for entry in data["codes"].values():
        entry["locked_ip"]   = None
        entry["locked_by"]   = None
        entry["player_name"] = None
        entry["fivem_name"]  = None
        entry["first_seen"]  = None
        entry["last_seen"]   = None
        count += 1

    save_data(data)
    add_log("ADMIN_RESET_ALL", f"Reset global — {count} codes libérés", admin=True)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /add  — Créer un code manuellement
# ════════════════════════════════════════════════════════════════
@app.route("/add", methods=["POST"])
def add():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    code = (body.get("code") or "").strip().lower()
    if not code:
        return jsonify({"ok": False, "reason": "missing_code"})

    data = load_data()
    if code in data["codes"]:
        return jsonify({"ok": False, "reason": "code_exists"})

    data["codes"][code] = {
        "locked_ip":   None,
        "locked_by":   None,
        "player_name": None,
        "fivem_name":  None,
        "first_seen":  None,
        "last_seen":   None,
        "expires_at":  body.get("expires_at"),
        "banner":      body.get("banner", ""),
        "theme":       body.get("theme",  ""),
        "created_at":  datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    save_data(data)
    add_log("ADMIN_ADD_CODE", f"Code créé manuellement", code=code, admin=True)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /generate  — Générer un code automatique FPSBN:FPSBN:XXXX
# Body JSON: { secret, expires_at?, count? }
# ════════════════════════════════════════════════════════════════
@app.route("/generate", methods=["POST"])
def generate():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    count = min(int(body.get("count", 1)), 50)  # max 50 à la fois
    data  = load_data()
    generated = []

    for _ in range(count):
        # Éviter les doublons
        for attempt in range(20):
            code = generate_fpsbn_code()
            if code not in data["codes"]:
                break

        data["codes"][code] = {
            "locked_ip":   None,
            "locked_by":   None,
            "player_name": None,
            "fivem_name":  None,
            "first_seen":  None,
            "last_seen":   None,
            "expires_at":  body.get("expires_at"),
            "banner":      body.get("banner", ""),
            "theme":       body.get("theme",  ""),
            "created_at":  datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        generated.append(code)

    save_data(data)
    add_log("ADMIN_GENERATE", f"{count} code(s) généré(s): {', '.join(generated)}", admin=True)
    return jsonify({"ok": True, "codes": generated})


# ════════════════════════════════════════════════════════════════
# POST /delete  — Supprimer un code définitivement
# Body JSON: { secret, code }
# ════════════════════════════════════════════════════════════════
@app.route("/delete", methods=["POST"])
def delete():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    code = (body.get("code") or "").strip().lower()
    data = load_data()

    if code not in data["codes"]:
        return jsonify({"ok": False, "reason": "code_not_found"})

    del data["codes"][code]
    save_data(data)
    add_log("ADMIN_DELETE", f"Code supprimé définitivement", code=code, admin=True)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /edit  — Modifier un code existant
# ════════════════════════════════════════════════════════════════
@app.route("/edit", methods=["POST"])
def edit():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    code = (body.get("code") or "").strip().lower()
    data = load_data()

    if code not in data["codes"]:
        return jsonify({"ok": False, "reason": "code_not_found"})

    entry = data["codes"][code]

    new_key = (body.get("new_key") or "").strip().lower()
    if new_key and new_key != code:
        data["codes"][new_key] = entry
        del data["codes"][code]
        entry = data["codes"][new_key]

    if "expires_at" in body:
        entry["expires_at"] = body["expires_at"]
    if "banner" in body:
        entry["banner"] = body["banner"]
    if "theme" in body:
        entry["theme"] = body["theme"]

    save_data(data)
    add_log("ADMIN_EDIT", f"Code modifié{' → ' + new_key if new_key and new_key != code else ''}", code=new_key or code, admin=True)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /ban-ip  — Bannir une IP
# ════════════════════════════════════════════════════════════════
@app.route("/ban-ip", methods=["POST"])
def ban_ip():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    ip = (body.get("ip") or "").strip()
    if not ip:
        return jsonify({"ok": False, "reason": "missing_ip"})

    data = load_data()
    if "banned_ips" not in data:
        data["banned_ips"] = []

    if ip not in data["banned_ips"]:
        data["banned_ips"].append(ip)
        save_data(data)

    add_log("ADMIN_BAN_IP", f"IP bannie", ip=ip, admin=True)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /unban-ip  — Débannir une IP
# ════════════════════════════════════════════════════════════════
@app.route("/unban-ip", methods=["POST"])
def unban_ip():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    ip = (body.get("ip") or "").strip()
    if not ip:
        return jsonify({"ok": False, "reason": "missing_ip"})

    data = load_data()
    data["banned_ips"] = [x for x in data.get("banned_ips", []) if x != ip]
    save_data(data)

    add_log("ADMIN_UNBAN_IP", f"IP débannie", ip=ip, admin=True)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# GET /logs  — Récupérer les logs
# ════════════════════════════════════════════════════════════════
@app.route("/logs", methods=["GET"])
def get_logs():
    secret = request.args.get("secret", "")
    if secret != ADMIN_SECRET:
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    logs  = load_logs()
    limit = int(request.args.get("limit", 100))
    return jsonify({"ok": True, "logs": logs[:limit]})


# ── LANCEMENT ────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
