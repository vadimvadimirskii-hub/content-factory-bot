#!/usr/bin/env python3
"""
Content Factory Bot v3 — Railway ONLY handles Telegram
All Instagram work done on Mac via Extella API
"""
import os, re, json, time, threading
from datetime import datetime

try:
    import requests
except ImportError:
    import subprocess as _sp, sys
    _sp.run([sys.executable, "-m", "pip", "install", "requests", "-q"], capture_output=True)
    import requests

BOT_TOKEN     = os.environ.get("BOT_TOKEN", '8671655293:AAFRhJ6cfydYBKD97tNQQs-BmnNrSruWCeg')
GROQ_KEY      = os.environ.get("GROQ_KEY", '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')
IG_COOKIES    = os.environ.get("IG_COOKIES", 'datr=BTUgaagiO2ZYRZFKmS6iwMl7;ig_did=E2AF752F-18F0-43C3-B430-F8D37B89AD7A;ig_nrcb=1;ps_l=1;ps_n=1;mid=aU92egAEAAHu6YFjq5dfWJ_3Pk7o;oo=v1;fbm_124024574287414=base_domain=.instagram.com;ds_user_id=74608160888;csrftoken=SuOX0LgUFFjSPr5yumif714rOKGp6HTJ;dpr=1.5;sessionid=74608160888%3AucgNMTr78DUAQG%3A6%3AAYhXdt07zKBQCZHL1bFzhkSEKmBFhNA7G;rur="LDC\\05474608160888\\0541809623011:01fee7cbed6cf5e952fe9d56a16eac01119132e8086c6ba206daa42ce6b51923a7da1a9d";wd=1248x977')
DEFAULT_VIEWS = int(os.environ.get("DEFAULT_VIEWS", "150000"))
EXTELLA_TOKEN = os.environ.get("EXTELLA_TOKEN", '6b3ebff3-ade2-4dff-85c8-3cea05b1bf55')
EXTELLA_URL   = os.environ.get("EXTELLA_URL", 'https://api.extella.ai')

TG = f"https://api.telegram.org/bot{BOT_TOKEN}"
active_jobs = {}

def tg_send(chat_id, text, reply_to=None):
    payload = {"chat_id": chat_id, "text": str(text)[:4096], "parse_mode": "HTML"}
    if reply_to: payload["reply_to_message_id"] = reply_to
    try:
        r = requests.post(f"{TG}/sendMessage", json=payload, timeout=15)
        return r.json().get("result", {}).get("message_id")
    except: pass

def tg_edit(chat_id, msg_id, text):
    try:
        requests.post(f"{TG}/editMessageText",
            json={"chat_id": chat_id, "message_id": msg_id,
                  "text": str(text)[:4096], "parse_mode": "HTML"}, timeout=15)
    except: pass

def extract_ig_username(text):
    text = text.strip()
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", text)
    if m:
        u = m.group(1)
        if u.lower() not in ["p","reel","reels","stories","explore","accounts"]:
            return u
    m = re.match(r"@([A-Za-z0-9_.]+)", text)
    if m: return m.group(1)
    if re.match(r"^[A-Za-z0-9_.]+$", text) and len(text) > 2:
        return text
    return None

def run_on_mac(chat_id, username, min_views, status_msg_id):
    """Send task to Mac via Extella API — Mac does ALL Instagram work"""
    try:
        print(f"[BOT] Sending to Mac: @{username} {min_views:,}+", flush=True)
        r = requests.post(
            f"{EXTELLA_URL}/api/expert/run",
            headers={"X-Auth-Token": EXTELLA_TOKEN, "Content-Type": "application/json"},
            json={
                "expert_name": "mac_transcribe_worker",
                "params": {
                    "username": username,
                    "min_views": min_views,
                    "bot_token": BOT_TOKEN,
                    "group_chat_id": str(chat_id),
                    "groq_api_key": GROQ_KEY,
                    "instagram_cookies": IG_COOKIES,
                    "status_chat_id": str(chat_id),
                    "status_msg_id": str(status_msg_id)
                }
            },
            timeout=7200)
        result = r.json()
        print(f"[BOT] Mac result: {str(result)[:150]}", flush=True)

        if r.status_code != 200 or result.get("status") == "error":
            err = result.get("message", str(result))[:200]
            tg_edit(chat_id, status_msg_id, f"❌ Ошибка на Mac:\n{err}")

    except Exception as e:
        print(f"[BOT] Mac call error: {e}", flush=True)
        tg_edit(chat_id, status_msg_id, f"❌ Mac недоступен: {e}")
    finally:
        active_jobs[str(chat_id)] = False

def _start(chat_id, username, min_views, reply_to):
    if active_jobs.get(str(chat_id)):
        tg_send(chat_id, "⏳ Уже идёт анализ, подожди...", reply_to); return
    active_jobs[str(chat_id)] = True
    sid = tg_send(chat_id,
        f"🚀 <b>@{username}</b>\n📊 {min_views:,}+ просмотров\n⏳ Передаю на Mac...",
        reply_to)
    threading.Thread(target=run_on_mac,
        args=(chat_id, username, min_views, sid), daemon=True).start()

def handle_message(msg):
    chat_id = msg.get("chat",{}).get("id")
    text = (msg.get("text","") or "").strip()
    msg_id = msg.get("message_id")
    if not chat_id or not text: return

    if text.startswith("/start") or text.startswith("/help"):
        tg_send(chat_id,
            "🤖 <b>Content Factory Bot</b>\n\n"
            "Отправь ссылку на Instagram профиль:\n"
            "<code>https://www.instagram.com/username</code>\n\n"
            "С кастомным фильтром:\n"
            "<code>https://www.instagram.com/username 500000</code>\n\n"
            f"📊 Дефолт: {DEFAULT_VIEWS:,}+ просмотров", msg_id)
        return

    if text.startswith("/status"):
        busy = active_jobs.get(str(chat_id), False)
        tg_send(chat_id, "⚙️ Идёт анализ..." if busy else "✅ Свободен"); return

    if text.startswith("/analyze"):
        args = text.replace("/analyze","").strip().split()
        if not args: tg_send(chat_id, "❌ <code>/analyze username</code>", msg_id); return
        username = extract_ig_username(args[0])
        min_views = DEFAULT_VIEWS
        if len(args) > 1:
            try:
                raw = args[1].upper().replace("K","000").replace("M","000000")
                min_views = int(raw)
            except: pass
        if not username: tg_send(chat_id, "❌ Не распознал аккаунт", msg_id); return
        _start(chat_id, username, min_views, msg_id); return

    if "instagram.com/" in text:
        username = extract_ig_username(text)
        if username:
            min_views = DEFAULT_VIEWS
            for part in text.split():
                try:
                    raw = part.upper().replace("K","000").replace("M","000000")
                    v = int(raw)
                    if 1000 <= v <= 100_000_000: min_views = v; break
                except: pass
            _start(chat_id, username, min_views, msg_id)

print(f"[BOT] 🚀 v3 started | Mac worker mode | filter={DEFAULT_VIEWS:,}+", flush=True)
print(f"[BOT] Extella: {EXTELLA_URL}", flush=True)

offset = 0
while True:
    try:
        r = requests.get(f"{TG}/getUpdates",
            params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
            timeout=35)
        if r.status_code == 200:
            for upd in r.json().get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if msg:
                    try: handle_message(msg)
                    except Exception as e: print(f"[ERR] {e}", flush=True)
    except Exception as e:
        print(f"[POLL] {e}", flush=True); time.sleep(5)
