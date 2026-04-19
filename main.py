"""
FPSBN-AUTH Server - Railway
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import json, os, datetime

app = Flask(__name__)

# ── CORS complet : gère aussi les preflight OPTIONS ──────────────────────────
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

@app.route("/<path:path>", methods=["OPTIONS"])
@app.route("/", methods=["OPTIONS"])
def handle_options(path=""):
    return Response(status=200, headers={
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization"
    })

# ─────────────────────────────────────────────────────────────────────────────

DB_FILE      = "auth_db.json"
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
            codes[code_name] = {
                "exclusive": exclusive,
                "banner":    banner,
                "theme":     theme
            }
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


# ── CHECK ────────────────────────────────────────────────────────────────────

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

    # Vérifier expiration
    db = read_db()
    entry = db.get(code)
    if isinstance(entry, dict) and entry.get("expires_at"):
        try:
            exp = datetime.datetime.fromisoformat(entry["expires_at"])
            if datetime.datetime.utcnow() > exp:
                return jsonify({"ok": False, "reason": "expired"}), 200
        except Exception:
            pass

    if not code_def["exclusive"]:
        return jsonify({"ok": True, "status": "guest",
                        "banner": code_def["banner"], "theme": code_def["theme"]})

    locked = entry.get("hwid") if isinstance(entry, dict) else entry

    if locked is None:
        return jsonify({"ok": True, "status": "available",
                        "banner": code_def["banner"], "theme": code_def["theme"]})
    elif locked == hwid:
        return jsonify({"ok": True, "status": "owner",
                        "banner": code_def["banner"], "theme": code_def["theme"]})
    else:
        return jsonify({"ok": False, "reason": "taken"}), 200


# ── CLAIM ────────────────────────────────────────────────────────────────────

@app.route("/claim", methods=["POST"])
def claim():
    data = request.get_json(force=True, silent=True) or {}
    code = str(data.get("code", "")).lower().strip()
    hwid = str(data.get("hwid", "")).strip()
    # player_name = nom avec lequel le joueur s'est identifié (le code lui-même)
    player_name = str(data.get("player_name", code)).strip()

    if not code or not hwid:
        return jsonify({"ok": False, "reason": "missing_params"}), 400

    CODES = load_codes()
    if code not in CODES:
        return jsonify({"ok": False, "reason": "invalid_code"}), 200

    code_def = CODES[code]
    if not code_def["exclusive"]:
        return jsonify({"ok": True, "status": "guest"})

    db    = read_db()
    entry = db.get(code)

    # Vérifier expiration
    if isinstance(entry, dict) and entry.get("expires_at"):
        try:
            exp = datetime.datetime.fromisoformat(entry["expires_at"])
            if datetime.datetime.utcnow() > exp:
                return jsonify({"ok": False, "reason": "expired"}), 200
        except Exception:
            pass

    locked = entry.get("hwid") if isinstance(entry, dict) else entry

    if locked is None:
        # Nouveau claim : sauvegarder hwid + nom du joueur + date de claim
        if isinstance(entry, dict):
            entry["hwid"]        = hwid
            entry["player_name"] = player_name
            entry["claimed_at"]  = datetime.datetime.utcnow().isoformat()
            db[code] = entry
        else:
            db[code] = {
                "hwid":        hwid,
                "player_name": player_name,
                "claimed_at":  datetime.datetime.utcnow().isoformat()
            }
        write_db(db)
        return jsonify({"ok": True, "status": "claimed"})
    elif locked == hwid:
        return jsonify({"ok": True, "status": "already_owner"})
    else:
        return jsonify({"ok": False, "reason": "taken"})


# ── STATUS (admin) ───────────────────────────────────────────────────────────

@app.route("/status", methods=["GET"])
def status():
    secret = request.args.get("secret", "")
    if secret != ADMIN_SECRET:
        return jsonify({"ok": False, "reason": "unauthorized"}), 401

    CODES  = load_codes()
    db     = read_db()
    now    = datetime.datetime.utcnow()
    result = {}

    for code, info in CODES.items():
        entry = db.get(code)

        # Compatibilité ancien format (string) et nouveau (dict)
        if isinstance(entry, dict):
            hwid        = entry.get("hwid")
            player_name = entry.get("player_name", code)
            claimed_at  = entry.get("claimed_at")
            expires_at  = entry.get("expires_at")
        elif isinstance(entry, str):
            hwid        = entry
            player_name = code
            claimed_at  = None
            expires_at  = None
        else:
            hwid = player_name = claimed_at = expires_at = None

        # Vérifier expiration
        is_expired = False
        if expires_at:
            try:
                is_expired = now > datetime.datetime.fromisoformat(expires_at)
            except Exception:
                pass

        result[code] = {
            "exclusive":   info["exclusive"],
            "locked_by":   hwid if hwid else None,
            "available":   hwid is None or not info["exclusive"],
            "player_name": player_name,
            "claimed_at":  claimed_at,
            "expires_at":  expires_at,
            "expired":     is_expired,
            "banner":      info.get("banner", ""),
            "theme":       info.get("theme", ""),
        }

    return jsonify({"ok": True, "codes": result})


# ── RESET individuel ─────────────────────────────────────────────────────────

@app.route("/reset", methods=["POST"])
def reset():
    data   = request.get_json(force=True, silent=True) or {}
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


# ── RESET GLOBAL ─────────────────────────────────────────────────────────────

@app.route("/reset-all", methods=["POST"])
def reset_all():
    data   = request.get_json(force=True, silent=True) or {}
    secret = str(data.get("secret", ""))

    if secret != ADMIN_SECRET:
        return jsonify({"ok": False, "reason": "unauthorized"}), 401

    write_db({})
    return jsonify({"ok": True, "msg": "Tous les codes ont ete reinitialises."})


# ── AJOUTER UN CODE (via variable d'env dynamique ou db) ─────────────────────

@app.route("/add", methods=["POST"])
def add_code():
    data   = request.get_json(force=True, silent=True) or {}
    secret = str(data.get("secret", ""))

    if secret != ADMIN_SECRET:
        return jsonify({"ok": False, "reason": "unauthorized"}), 401

    code       = str(data.get("code", "")).lower().strip()
    expires_at = data.get("expires_at", None)  # ISO string ou null

    if not code:
        return jsonify({"ok": False, "reason": "missing_code"}), 400

    # On stocke l'expiration dans la db (le code doit exister en variable d'env)
    CODES = load_codes()
    if code not in CODES:
        return jsonify({"ok": False, "reason": "code_not_in_env"}), 200

    db = read_db()
    if isinstance(db.get(code), dict):
        db[code]["expires_at"] = expires_at
    else:
        db[code] = {"hwid": None, "expires_at": expires_at, "player_name": None}

    write_db(db)
    return jsonify({"ok": True, "msg": f"Code '{code}' mis a jour."})


# ── MODIFIER UN CODE ──────────────────────────────────────────────────────────

@app.route("/edit", methods=["POST"])
def edit_code():
    data   = request.get_json(force=True, silent=True) or {}
    secret = str(data.get("secret", ""))

    if secret != ADMIN_SECRET:
        return jsonify({"ok": False, "reason": "unauthorized"}), 401

    code       = str(data.get("code", "")).lower().strip()
    expires_at = data.get("expires_at", None)  # None = jamais, string ISO = date limite

    if not code:
        return jsonify({"ok": False, "reason": "missing_code"}), 400

    CODES = load_codes()
    if code not in CODES:
        return jsonify({"ok": False, "reason": "code_not_found"}), 200

    db    = read_db()
    entry = db.get(code, {})

    if not isinstance(entry, dict):
        entry = {"hwid": entry}

    entry["expires_at"] = expires_at
    db[code] = entry
    write_db(db)

    return jsonify({"ok": True, "msg": f"Code '{code}' modifie."})


# ── HEALTH ───────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def health():
    CODES = load_codes()
    return jsonify({
        "ok":           True,
        "service":      "FPSBN-AUTH",
        "version":      "3.0",
        "codes_actifs": len(CODES)
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
