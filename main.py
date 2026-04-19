from flask import Flask, request, jsonify
import json
import os
from datetime import datetime

app = Flask(__name__)

# ── CONFIG ──────────────────────────────────────────────────────
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "ton_mot_de_passe_admin")
DATA_FILE    = "codes.json"


# ── PERSISTANCE ─────────────────────────────────────────────────
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


# ════════════════════════════════════════════════════════════════
# GET /status  — Panneau admin : liste des codes + IPs bannies
# ════════════════════════════════════════════════════════════════
@app.route("/status", methods=["GET"])
def status():
    secret = request.args.get("secret", "")
    if secret != ADMIN_SECRET:
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    data = load_data()
    return jsonify({
        "ok":         True,
        "codes":      data.get("codes", {}),
        "banned_ips": data.get("banned_ips", [])
    })


# ════════════════════════════════════════════════════════════════
# GET /check  — Menu Lua : vérifie le code + l'IP du joueur
# Params: code, ip
# ════════════════════════════════════════════════════════════════
@app.route("/check", methods=["GET"])
def check():
    code = (request.args.get("code") or "").strip().lower()
    ip   = (request.args.get("ip")   or "").strip()

    if not code or not ip:
        return jsonify({"ok": False, "reason": "missing_fields"})

    data  = load_data()
    entry = data["codes"].get(code)

    # Code inexistant
    if entry is None:
        return jsonify({"ok": False, "reason": "invalid_code"})

    # Code expiré
    if is_expired(entry):
        return jsonify({"ok": False, "reason": "expired"})

    # IP bannie globalement
    if ip in data.get("banned_ips", []):
        return jsonify({"ok": False, "reason": "ip_banned"})

    # Code déjà verrouillé sur une autre IP → refus
    locked_ip = entry.get("locked_ip")
    if locked_ip and locked_ip != ip:
        return jsonify({"ok": False, "reason": "ip_mismatch"})

    # OK (code libre ou même IP)
    return jsonify({
        "ok":     True,
        "banner": entry.get("banner", ""),
        "theme":  entry.get("theme",  "")
    })


# ════════════════════════════════════════════════════════════════
# POST /claim  — Verrouille le code sur l'IP + stocke le nom
# Body JSON: { code, ip, player_name }
# player_name = affichage admin UNIQUEMENT (pas utilisé pour l'auth)
# ════════════════════════════════════════════════════════════════
@app.route("/claim", methods=["POST"])
def claim():
    body        = request.get_json(force=True) or {}
    code        = (body.get("code")        or "").strip().lower()
    ip          = (body.get("ip")          or "").strip()
    player_name = (body.get("player_name") or "").strip()

    if not code or not ip:
        return jsonify({"ok": False, "reason": "missing_fields"})

    data  = load_data()
    entry = data["codes"].get(code)

    if entry is None:
        return jsonify({"ok": False, "reason": "invalid_code"})

    # Vérification IP (double sécurité au moment du claim)
    locked_ip = entry.get("locked_ip")
    if locked_ip and locked_ip != ip:
        return jsonify({"ok": False, "reason": "taken"})

    # IP bannie
    if ip in data.get("banned_ips", []):
        return jsonify({"ok": False, "reason": "ip_banned"})

    # Première utilisation → verrouiller l'IP
    if not locked_ip:
        entry["locked_ip"] = ip

    # Stocker le nom du joueur (affichage admin seulement)
    if player_name:
        entry["player_name"] = player_name

    save_data(data)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /reset  — Libérer un code (efface IP + nom)
# Body JSON: { secret, code }
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

    entry["locked_ip"]   = None
    entry["locked_by"]   = None   # compatibilité ancienne version
    entry["player_name"] = None

    save_data(data)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /reset-all  — Libérer tous les codes
# Body JSON: { secret }
# ════════════════════════════════════════════════════════════════
@app.route("/reset-all", methods=["POST"])
def reset_all():
    body = request.get_json(force=True) or {}
    if not check_secret(body):
        return jsonify({"ok": False, "reason": "unauthorized"}), 403

    data = load_data()
    for entry in data["codes"].values():
        entry["locked_ip"]   = None
        entry["locked_by"]   = None
        entry["player_name"] = None

    save_data(data)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /add  — Créer un nouveau code d'accès
# Body JSON: { secret, code, expires_at? }
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
        "expires_at":  body.get("expires_at"),
        "banner":      body.get("banner", ""),
        "theme":       body.get("theme",  "")
    }
    save_data(data)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /edit  — Modifier un code existant
# Body JSON: { secret, code, new_key?, expires_at?, banner?, theme? }
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

    # Renommer le code
    new_key = (body.get("new_key") or "").strip().lower()
    if new_key and new_key != code:
        data["codes"][new_key] = entry
        del data["codes"][code]
        entry = data["codes"][new_key]

    # Mettre à jour les champs
    if "expires_at" in body:
        entry["expires_at"] = body["expires_at"]
    if "banner" in body:
        entry["banner"] = body["banner"]
    if "theme" in body:
        entry["theme"] = body["theme"]

    save_data(data)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /ban-ip  — Bannir une IP globalement
# Body JSON: { secret, ip }
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

    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════════
# POST /unban-ip  — Débannir une IP
# Body JSON: { secret, ip }
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

    return jsonify({"ok": True})


# ── LANCEMENT ────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
