import os
import json
import hmac
import hashlib
import sqlite3
import secrets
import time
import threading
from datetime import datetime, timezone, date
from urllib.parse import parse_qsl

from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").strip()
PORT = int(os.getenv("PORT", "10000"))
AD_SECONDS = 15

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = BASE_DIR
DB_PATH = os.path.join(BASE_DIR, "meva_garden.db")


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN .env faylida berilmagan")
if not WEBAPP_URL:
    raise RuntimeError("WEBAPP_URL .env faylida berilmagan")


app = Flask(__name__)

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        return "", 204

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "*")
    response.headers["Access-Control-Allow-Origin"] = origin if origin else "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Telegram-Init-Data"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Vary"] = "Origin"
    return response

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        apples INTEGER NOT NULL DEFAULT 0,
        ads INTEGER NOT NULL DEFAULT 0,
        pending_ads INTEGER NOT NULL DEFAULT 0,
        water INTEGER NOT NULL DEFAULT 100,
        daily_claimed TEXT,
        channel_claimed INTEGER NOT NULL DEFAULT 0,
        invited_by INTEGER,
        active_referral_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS ad_sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        started_at INTEGER NOT NULL,
        completed INTEGER NOT NULL DEFAULT 0
    );
    """)
    conn.commit()
    conn.close()

def verify_init_data(init_data: str):
    if not init_data:
        return None

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(pairs.items())
    )

    # According to Telegram Web App auth docs the secret key is
    # the SHA256 of the bot token (not an HMAC with "WebAppData").
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()

    calculated = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated, received_hash):
        return None

    auth_date = int(pairs.get("auth_date", "0") or 0)
    if not auth_date or time.time() - auth_date > 86400:
        return None

    try:
        return json.loads(pairs["user"])
    except (KeyError, json.JSONDecodeError):
        return None

def current_user():
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user = verify_init_data(init_data)
    if not user:
        return None
    return user

def ensure_user(tg_user, start_param=None):
    user_id = int(tg_user["id"])
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    if row is None:
        inviter = None
        if start_param and start_param.startswith("ref_"):
            try:
                candidate = int(start_param[4:])
                if candidate != user_id:
                    inviter = candidate
            except ValueError:
                pass

        conn.execute("""
            INSERT INTO users
            (id, username, first_name, invited_by, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            tg_user.get("username"),
            tg_user.get("first_name", "Foydalanuvchi"),
            inviter,
            datetime.now(timezone.utc).isoformat()
        ))
        conn.commit()

    else:
        conn.execute("""
            UPDATE users SET username=?, first_name=? WHERE id=?
        """, (
            tg_user.get("username"),
            tg_user.get("first_name", "Foydalanuvchi"),
            user_id
        ))
        conn.commit()

    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return row

def user_json(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "first_name": row["first_name"],
        "apples": row["apples"],
        "ads": row["ads"],
        "pending_ads": row["pending_ads"],
        "water": row["water"],
        "daily_claimed": row["daily_claimed"],
        "channel_claimed": bool(row["channel_claimed"]),
        "referrals": row["active_referral_count"],
        "level": row["apples"] // 100,
    }

def auth_row():
    tg_user = current_user()
    if not tg_user:
        return None, None
    start_param = request.args.get("start_param", "")
    row = ensure_user(tg_user, start_param)
    return tg_user, row

@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")

@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(STATIC_DIR, path)

@app.get("/api/me")
def api_me():
    tg_user, row = auth_row()
    if not row:
        return jsonify({"ok": False, "error": "Telegram autentifikatsiyasi noto'g'ri"}), 401

    conn = db()
    leaderboard = conn.execute("""
        SELECT first_name, username, active_referral_count AS count
        FROM users
        ORDER BY active_referral_count DESC, id ASC
        LIMIT 5
    """).fetchall()
    conn.close()

    data = user_json(row)
    data["leaderboard"] = [
        {
            "name": x["first_name"] or x["username"] or "Foydalanuvchi",
            "count": x["count"]
        } for x in leaderboard
    ]
    data["ref_link"] = f"https://t.me/{os.getenv('BOT_USERNAME', 'YOUR_BOT')}?start=ref_{row['id']}"
    return jsonify({"ok": True, "user": data})

@app.post("/api/ad/start")
def ad_start():
    _, row = auth_row()
    if not row:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    if row["pending_ads"] >= 3:
        return jsonify({"ok": False, "error": "Avval daraxtni sug'oring"}), 400

    token = secrets.token_urlsafe(24)
    conn = db()
    conn.execute(
        "INSERT INTO ad_sessions(token,user_id,started_at) VALUES(?,?,?)",
        (token, row["id"], int(time.time()))
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "session": token, "seconds": AD_SECONDS})

@app.post("/api/ad/complete")
def ad_complete():
    _, row = auth_row()
    if not row:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    token = payload.get("session", "")
    conn = db()
    session = conn.execute(
        "SELECT * FROM ad_sessions WHERE token=? AND user_id=?",
        (token, row["id"])
    ).fetchone()

    if not session:
        conn.close()
        return jsonify({"ok": False, "error": "Reklama sessiyasi topilmadi"}), 400

    if session["completed"]:
        conn.close()
        return jsonify({"ok": False, "error": "Bu reklama allaqachon hisoblangan"}), 400

    if int(time.time()) - session["started_at"] < AD_SECONDS:
        conn.close()
        return jsonify({"ok": False, "error": "Reklama vaqti hali tugamagan"}), 400

    conn.execute("UPDATE ad_sessions SET completed=1 WHERE token=?", (token,))
    conn.execute("""
        UPDATE users
        SET ads=ads+1, pending_ads=pending_ads+1
        WHERE id=?
    """, (row["id"],))
    conn.commit()

    new_row = conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()

    # Taklif qilgan foydalanuvchi: taklif qilingan odam 3 ta reklama tugatgach 1 marta faol referral bo'ladi.
    if new_row["pending_ads"] == 3:
        inviter = new_row["invited_by"]
        if inviter:
            already = conn.execute("""
                SELECT COUNT(*) AS c FROM users
                WHERE invited_by=? AND pending_ads>=3
            """, (inviter,)).fetchone()["c"]
            conn.execute("""
                UPDATE users SET active_referral_count=?
                WHERE id=?
            """, (already, inviter))
            conn.commit()

    conn.close()
    return jsonify({"ok": True, "user": user_json(new_row)})

@app.post("/api/water")
def water():
    _, row = auth_row()
    if not row:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    conn = db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()

    if row["pending_ads"] < 3:
        conn.close()
        return jsonify({"ok": False, "error": "Avval 3 ta reklama ko'ring"}), 400
    if row["water"] < 20:
        conn.close()
        return jsonify({"ok": False, "error": "Suv zaxirasi yetarli emas"}), 400

    conn.execute("""
        UPDATE users
        SET apples=apples+5, pending_ads=0, water=water-20
        WHERE id=?
    """, (row["id"],))
    conn.commit()
    new_row = conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
    conn.close()
    return jsonify({"ok": True, "reward": 5, "user": user_json(new_row)})

@app.post("/api/daily")
def daily():
    _, row = auth_row()
    if not row:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    today = date.today().isoformat()
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()

    if row["daily_claimed"] == today:
        conn.close()
        return jsonify({"ok": False, "error": "Bugungi bonus olingan"}), 400

    conn.execute(
        "UPDATE users SET apples=apples+2, daily_claimed=? WHERE id=?",
        (today, row["id"])
    )
    conn.commit()
    new_row = conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
    conn.close()
    return jsonify({"ok": True, "reward": 2, "user": user_json(new_row)})


@app.post("/api/channel/claim")
def channel_claim():
    tg_user, row = auth_row()
    if not row:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    if row["channel_claimed"]:
        return jsonify({"ok": False, "error": "Vazifa allaqachon bajarilgan"}), 400

    if not CHANNEL_USERNAME:
        return jsonify({"ok": False, "error": "CHANNEL_USERNAME sozlanmagan"}), 500

    # Bot kanal admini bo'lishi kerak, aks holda membership tekshiruvi ishlamasligi mumkin.
    import asyncio
    async def check():
        from telegram import Bot
        async with Bot(BOT_TOKEN) as bot:
            return await bot.get_chat_member(CHANNEL_USERNAME, int(tg_user["id"]))

    try:
        member = asyncio.run(check())
        if member.status not in ("member", "administrator", "creator"):
            return jsonify({"ok": False, "error": "Avval kanalga a'zo bo'ling"}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": "Kanal a'zoligini tekshirib bo'lmadi", "detail": str(exc)}), 400

    conn = db()
    conn.execute("""
        UPDATE users SET apples=apples+5, channel_claimed=1 WHERE id=?
    """, (row["id"],))
    conn.commit()
    new_row = conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
    conn.close()
    return jsonify({"ok": True, "reward": 5, "user": user_json(new_row)})

async def bot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    start = context.args[0] if context.args else ""

    # Referralni bot /start bosilganda ham saqlaymiz.
    conn = db()
    existing = conn.execute("SELECT id FROM users WHERE id=?", (user.id,)).fetchone()
    inviter = None
    if not existing and start.startswith("ref_"):
        try:
            candidate = int(start[4:])
            if candidate != user.id:
                inviter = candidate
        except ValueError:
            pass

    conn.execute("""
        INSERT INTO users(id,username,first_name,invited_by,created_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name
    """, (
        user.id, user.username, user.first_name or "Foydalanuvchi",
        inviter, datetime.now(timezone.utc).isoformat()
    ))
    conn.commit()
    conn.close()

    keyboard = [[
        InlineKeyboardButton(
            "🍎 Meva Gardenni ochish",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
    ]]
    await update.message.reply_text(
        f"Salom, {user.first_name or 'do‘stim'}! 🍎\n\n"
        "Meva Gardenni ochish uchun pastdagi tugmani bosing.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def bot_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍎 Meva Garden\n\n/start — Mini Appni ochish"
    )

def run_bot():
    async def runner():
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", bot_start))
        application.add_handler(CommandHandler("help", bot_help))
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        while True:
            await __import__("asyncio").sleep(3600)

    import asyncio
    asyncio.run(runner())

def start_bot_thread():
    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()

init_db()

# Simple health/status endpoint (avoid duplicate root handler)
@app.get('/status')
def status():
    return "Mini App ishlayapti!"


if __name__ == "__main__":
    start_bot_thread()
    app.run(host="0.0.0.0", port=PORT)

