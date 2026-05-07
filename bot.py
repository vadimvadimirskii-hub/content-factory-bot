#!/usr/bin/env python3
"""
Content Factory Bot — Hybrid Architecture
Railway: Telegram polling + Instagram parsing
Mac (via Extella API): Download + Transcribe + Send document
"""
import os, sys, re, json, time, threading
from datetime import datetime
from urllib.parse import unquote

try:
    import requests
except ImportError:
    import subprocess as _sp
    _sp.run([sys.executable, "-m", "pip", "install", "requests", "-q"], capture_output=True)
    import requests

BOT_TOKEN      = os.environ.get("BOT_TOKEN", '8671655293:AAFRhJ6cfydYBKD97tNQQs-BmnNrSruWCeg')
GROQ_KEY       = os.environ.get("GROQ_KEY", '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')
IG_COOKIES     = os.environ.get("IG_COOKIES", 'datr=BTUgaagiO2ZYRZFKmS6iwMl7;ig_did=E2AF752F-18F0-43C3-B430-F8D37B89AD7A;ig_nrcb=1;ps_l=1;ps_n=1;mid=aU92egAEAAHu6YFjq5dfWJ_3Pk7o;oo=v1;fbm_124024574287414=base_domain=.instagram.com;ds_user_id=74608160888;csrftoken=SuOX0LgUFFjSPr5yumif714rOKGp6HTJ;dpr=1.5;sessionid=74608160888%3AucgNMTr78DUAQG%3A6%3AAYhXdt07zKBQCZHL1bFzhkSEKmBFhNA7G;rur="LDC\\05474608160888\\0541809623011:01fee7cbed6cf5e952fe9d56a16eac01119132e8086c6ba206daa42ce6b51923a7da1a9d";wd=1248x977')
DEFAULT_VIEWS  = int(os.environ.get("DEFAULT_VIEWS", "150000"))
EXTELLA_TOKEN  = os.environ.get("EXTELLA_TOKEN", '6b3ebff3-ade2-4dff-85c8-3cea05b1bf55')
EXTELLA_URL    = os.environ.get("EXTELLA_URL", 'https://api.extella.ai')

TG = f"https://api.telegram.org/bot{BOT_TOKEN}"
active_jobs = {}

# ─── TELEGRAM ────────────────────────────────────────────────────────
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

# ─── EXTRACT USERNAME ────────────────────────────────────────────────
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

# ─── GET INSTAGRAM VIDEOS (Railway) ──────────────────────────────────
def get_viral_videos(username, min_views):
    cookies = {}
    for p in IG_COOKIES.split(";"):
        p = p.strip()
        if "=" in p:
            k, v = p.split("=", 1)
            cookies[k.strip()] = unquote(v.strip())

    csrf = cookies.get("csrftoken", "")
    UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15"
    hdrs = {
        "User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9",
        "X-IG-App-ID": "936619743392459", "X-CSRFToken": csrf,
        "Referer": f"https://www.instagram.com/{username}/",
        "Origin": "https://www.instagram.com",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    # Get user_id — mobile API (no IP restriction)
    user_id = None
    try:
        r = requests.get(
            f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
            headers={"User-Agent": "Instagram 275.0.0.27.98 Android (33/13; 420dpi; 1080x2400; samsung; SM-G991B; o1s; exynos2100; en_US; 458229258)",
                     "X-IG-App-ID": "936619743392459"},
            timeout=15)
        if r.status_code == 200:
            u = r.json().get("data", {}).get("user") or r.json().get("user")
            if u: user_id = str(u.get("id") or u.get("pk") or "")
    except: pass

    if not user_id:
        try:
            r2 = requests.get(
                f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
                headers={**hdrs, "Content-Type": None}, cookies=cookies, timeout=15)
            if r2.status_code == 200:
                u = (r2.json().get("data", {}).get("user") or r2.json().get("user"))
                if u: user_id = str(u.get("id") or u.get("pk") or "")
        except: pass

    if not user_id:
        return None, "user_id not found"

    # Fetch reels
    all_videos = []; max_id = None
    for _ in range(30):
        if len(all_videos) >= 200: break
        try:
            data = {"target_user_id": user_id, "page_size": "50", "include_feed_video": "true"}
            if max_id: data["max_id"] = max_id
            r = requests.post("https://www.instagram.com/api/v1/clips/user/",
                headers=hdrs, cookies=cookies, data=data, timeout=30)
            if r.status_code != 200: break
            rd = r.json()
            for item in rd.get("items", []):
                mv = item.get("media", item)
                views = mv.get("play_count") or mv.get("view_count") or 0
                cap = (mv.get("caption") or {})
                cap = cap.get("text","") if isinstance(cap,dict) else str(cap)
                vv = mv.get("video_versions") or []
                all_videos.append({
                    "shortcode": mv.get("code",""),
                    "view_count": views,
                    "like_count": mv.get("like_count",0),
                    "comment_count": mv.get("comment_count",0),
                    "caption": cap[:300],
                    "video_url": vv[0].get("url","") if vv else ""
                })
            pi = rd.get("paging_info", {})
            if not (pi.get("more_available") or rd.get("more_available")): break
            nid = pi.get("max_id") or rd.get("next_max_id")
            if not nid: break
            max_id = nid; time.sleep(1.2)
        except Exception as e:
            print(f"[PARSE] err: {e}", flush=True); break

    viral = sorted([v for v in all_videos if v["view_count"] >= min_views],
                   key=lambda x: x["view_count"], reverse=True)
    return viral, None

# ─── CALL MAC WORKER VIA EXTELLA ─────────────────────────────────────
def call_mac_worker(chat_id, username, min_views, viral_videos, status_msg_id):
    try:
        r = requests.post(
            f"{EXTELLA_URL}/api/expert/run",
            headers={"X-Auth-Token": EXTELLA_TOKEN, "Content-Type": "application/json"},
            json={
                "expert_name": "mac_transcribe_worker",
                "params": {
                    "videos_json": json.dumps(viral_videos),
                    "bot_token": BOT_TOKEN,
                    "group_chat_id": str(chat_id),
                    "groq_api_key": GROQ_KEY,
                    "instagram_cookies": IG_COOKIES,
                    "target_account": username,
                    "min_views": min_views,
                    "status_chat_id": str(chat_id),
                    "status_msg_id": str(status_msg_id)
                }
            },
            timeout=7200)
        result = r.json()
        print(f"[MAC] response: {str(result)[:200]}", flush=True)
        return result
    except Exception as e:
        print(f"[MAC] call error: {e}", flush=True)
        return {"status": "error", "message": str(e)}

# ─── PIPELINE ────────────────────────────────────────────────────────
def run_pipeline(chat_id, username, min_views, status_msg_id):
    try:
        tg_edit(chat_id, status_msg_id, f"🔍 Загружаю профиль <b>@{username}</b>...")

        viral, err = get_viral_videos(username, min_views)

        if err or viral is None:
            tg_edit(chat_id, status_msg_id, f"❌ <b>@{username}</b> не найден")
            active_jobs[str(chat_id)] = False; return

        total = len(viral)
        if total == 0:
            tg_edit(chat_id, status_msg_id,
                f"❌ <b>@{username}</b>\nНет видео {min_views:,}+")
            active_jobs[str(chat_id)] = False; return

        top3 = "\n".join([f"  #{i+1} {v['shortcode']}: {v['view_count']:,} 👁"
                           for i,v in enumerate(viral[:3])])
        tg_edit(chat_id, status_msg_id,
            f"✅ <b>@{username}</b> — {total} видео {min_views:,}+\n"
            f"🏆 Топ-3:\n{top3}\n\n"
            f"🎤 Передаю на транскрипцию (Mac)...")

        # Send to Mac for download + transcription
        result = call_mac_worker(chat_id, username, min_views, viral, status_msg_id)

        if result.get("status") != "success":
            err_msg = result.get("message", str(result))[:200]
            tg_edit(chat_id, status_msg_id,
                f"❌ Ошибка транскрипции:\n{err_msg}")

    except Exception as e:
        print(f"[PIPELINE] {e}", flush=True)
        tg_send(chat_id, f"❌ Ошибка: {e}")
    finally:
        active_jobs[str(chat_id)] = False

def _start(chat_id, username, min_views, reply_to):
    if active_jobs.get(str(chat_id)):
        tg_send(chat_id, "⏳ Уже идёт анализ, подожди...", reply_to); return
    active_jobs[str(chat_id)] = True
    sid = tg_send(chat_id,
        f"🚀 <b>@{username}</b>\n📊 {min_views:,}+ просмотров\n⏳ Загружаю...", reply_to)
    threading.Thread(target=run_pipeline, args=(chat_id, username, min_views, sid), daemon=True).start()

# ─── HANDLE MESSAGE ──────────────────────────────────────────────────
def handle_message(msg):
    chat_id = msg.get("chat",{}).get("id")
    text = (msg.get("text","") or "").strip()
    msg_id = msg.get("message_id")
    if not chat_id or not text: return

    if text.startswith("/start") or text.startswith("/help"):
        tg_send(chat_id,
            "🤖 <b>Content Factory Bot</b>\n\n"
            "Отправь ссылку на Instagram профиль:\n\n"
            "<code>https://www.instagram.com/username</code>\n\n"
            "С кастомным фильтром:\n"
            "<code>https://www.instagram.com/username 500000</code>\n\n"
            f"📊 Дефолт: {DEFAULT_VIEWS:,}+ просмотров", msg_id)
        return

    if text.startswith("/status"):
        busy = active_jobs.get(str(chat_id), False)
        tg_send(chat_id, "⚙️ Идёт анализ..." if busy else "✅ Свободен")
        return

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

# ─── POLLING ─────────────────────────────────────────────────────────
print(f"[BOT] 🚀 Hybrid mode started | filter={DEFAULT_VIEWS:,}+", flush=True)
print(f"[BOT] Extella API: {EXTELLA_URL}", flush=True)
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
