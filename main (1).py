"""
FPSBN-AUTH Server - Railway
Les codes sont definis directement dans CODES ci-dessous.
Pour ajouter un code : ajoute une ligne dans CODES et redeploi.
"""

from flask import Flask, request, jsonify
import json, os

app = Flask(__name__)

DB_FILE = "auth_db.json"

# ─── TES CODES ──────────────────────────────────────────────────────────────
# exclusive=True  → un seul HWID peut l'utiliser (code personnel)
# exclusive=False → tout le monde peut l'utiliser (code invité)
CODES = {
    "freez1x": {"exclusive": True,  "banner": "Freez1x", "theme": "Freez1x"},
    "pinpin":  {"exclusive": True,  "banner": "Pinpin",  "theme": "Pinpin"},
    "bob":     {"exclusive": True,  "banner": "Bob",     "theme": "Bob"},
    "nezz":    {"exclusive": True,  "banner": "Nezz",    "theme": "Nezz"},
    "sabry":   {"exclusive": True,  "banner": "Sabry",   "theme": "Sabry"},
    "zeub":    {"exclusive": False, "banner": "Gengar",  "theme": "Gengar"},
}

ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "change_moi_2024")


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

    if code not in CODES:
        return jsonify({"ok": False, "reason": "invalid_code"}), 200

    db = read_db()
    if code in db:
        del db[code]
        write_db(db)
        return jsonify({"ok": True, "msg": f"Code '{code}' reset."})
    else:
        return jsonify({"ok": True, "msg": f"Code '{code}' etait deja libre."})


@app.route("/", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "FPSBN-AUTH", "version": "1.0"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
