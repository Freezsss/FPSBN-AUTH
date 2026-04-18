"""
FPSBN-AUTH Server - Railway
Les codes sont definis via les variables d'environnement Railway.

Format des variables a creer dans Railway :
  CODE_nomducode=banner:theme:exclusive
  
Exemples :
  CODE_freez1x=Freez1x:Freez1x:true
  CODE_pinpin=Pinpin:Pinpin:true
  CODE_zeub=Gengar:Gengar:false
"""

from flask import Flask, request, jsonify
import json, os

app = Flask(__name__)

DB_FILE = "auth_db.json"
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "change_moi_2024")


def load_codes():
    """Lit tous les codes depuis les variables d'environnement Railway."""
    codes = {}
    for key, value in os.environ.items():
        if key.startswith("CODE_"):
            code_name = key[5:].lower().strip()  # Enleve "CODE_" et met en minuscules
            parts = value.split(":")
            if len(parts) >= 3:
                banner    = parts[0].strip()
                theme     = parts[1].strip()
                exclusive = parts[2].strip().lower() == "true"
            elif len(parts) == 2:
                banner    = parts[0].strip()
                theme     = parts[1].strip()
                exclusive = True  # Par defaut : exclusif
            elif len(parts) == 1:
                banner    = parts[0].strip()
                theme     = parts[0].strip()
                exclusive = True
            else:
                continue
            codes[code_name] = {
                "exclusive": exclusive,
                "banner":    banner,
                "theme":     theme,
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


def write_db(db: dict):
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
    locked_hwid = db.get(code)

    if locked_hwid is None:
        return jsonify({"ok": True, "status": "available", "banner": code_def["banner"], "theme": code_def["theme"]})
    elif locked_hwid == hwid:
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
    locked_hwid = db.get(code)

    if locked_hwid is None:
        db[code] = hwid
        write_db(db)
        return jsonify({"ok": True, "status": "claimed"})
    elif locked_hwid == hwid:
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
        return jsonify({"ok": True, "msg": f"Code '{code}' reset. Disponible a nouveau."})
    else:
        return jsonify({"ok": True, "msg": f"Code '{code}' etait deja libre."})


@app.route("/", methods=["GET"])
def health():
    CODES = load_codes()
    return jsonify({"ok": True, "service": "FPSBN-AUTH", "version": "2.0", "codes_actifs": len(CODES)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
