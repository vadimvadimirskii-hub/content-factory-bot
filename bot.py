#!/usr/bin/env python3
"""Content Factory Bot — runs on server 24/7"""
import os, sys, json, time, tempfile, subprocess, threading, re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import requests

BOT_TOKEN     = os.environ.get("BOT_TOKEN", '8671655293:AAFRhJ6cfydYBKD97tNQQs-BmnNrSruWCeg')
GROQ_KEY      = os.environ.get("GROQ_KEY", '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')
IG_COOKIES    = os.environ.get("IG_COOKIES", 'datr=BTUgaagiO2ZYRZFKmS6iwMl7;ig_did=E2AF752F-18F0-43C3-B430-F8D37B89AD7A;ig_nrcb=1;ps_l=1;ps_n=1;mid=aU92egAEAAHu6YFjq5dfWJ_3Pk7o;oo=v1;fbm_124024574287414=base_domain=.instagram.com;ds_user_id=74608160888;csrftoken=SuOX0LgUFFjSPr5yumif714rOKGp6HTJ;dpr=1.5;sessionid=74608160888%3AucgNMTr78DUAQG%3A6%3AAYhXdt07zKBQCZHL1bFzhkSEKmBFhNA7G;rur="LDC\\05474608160888\\0541809623011:01fee7cbed6cf5e952fe9d56a16eac01119132e8086c6ba206daa42ce6b51923a7da1a9d";wd=1248x977')
DEFAULT_VIEWS = int(os.environ.get("DEFAULT_VIEWS", "150000"))
TG            = f"https://api.telegram.org/bot{BOT_TOKEN}"

active_jobs = {}

def tg_send(chat_id, text, reply_to=None):
    payload = {"chat_id": chat_id, "text": str(text)[:4096], "parse_mode": "HTML"}
    if reply_to: payload["reply_to_message_id"] = reply_to
    try:
        r = requests.post(f"{TG}/sendMessage", json=payload, timeout=15)
        return r.json().get("result", {}).get("message_id")
    except Exception as e:
        print(f"[TG] {e}", flush=True)

def tg_edit(chat_id, msg_id, text):
    try:
        requests.post(f"{TG}/editMessageText",
            json={"chat_id": chat_id, "message_id": msg_id,
                  "text": str(text)[:4096], "parse_mode": "HTML"}, timeout=15)
    except: pass

def tg_doc(chat_id, path, caption=""):
    try:
        with open(path, "rb") as f:
            r = requests.post(f"{TG}/sendDocument",
                data={"chat_id": chat_id, "caption": caption[:1024]},
                files={"document": (Path(path).name, f)}, timeout=300)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

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

def run_pipeline(chat_id, username, min_views, status_msg_id):
    try:
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

        tg_edit(chat_id, status_msg_id, f"🔍 Ищу профиль <b>@{username}</b>...")
        user_id = None

        # Method 1: Instagram mobile API (works from any IP, no cookies needed)
        try:
            r0 = requests.get(
                f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
                headers={
                    "User-Agent": "Instagram 275.0.0.27.98 Android (33/13; 420dpi; 1080x2400; samsung; SM-G991B; o1s; exynos2100; en_US; 458229258)",
                    "X-IG-App-ID": "936619743392459",
                    "Accept": "*/*",
                    "Accept-Language": "en-US",
                },
                timeout=15)
            if r0.status_code == 200:
                rj0 = r0.json()
                u0 = rj0.get("data", {}).get("user") or rj0.get("user")
                if u0: user_id = str(u0.get("id") or u0.get("pk") or "")
        except: pass

        # Method 2: web_profile_info with browser cookies
        if not user_id:
            try:
                r = requests.get(
                    f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
                    headers={**hdrs, "Content-Type": None}, cookies=cookies, timeout=20)
                if r.status_code == 200:
                    rj = r.json()
                    u = (rj.get("data", {}).get("user") or rj.get("user") or rj.get("graphql", {}).get("user"))
                    if u: user_id = str(u.get("id") or u.get("pk") or "")
            except: pass

        # Method 3: HTML scrape
        if not user_id:
            try:
                r2 = requests.get(f"https://www.instagram.com/{username}/",
                    headers={**hdrs, "Content-Type": None, "Accept": "text/html"},
                    cookies=cookies, timeout=20)
                m = re.search(r'"user_id"\s*:\s*"(\d+)"', r2.text)
                if m: user_id = m.group(1)
            except: pass

        if not user_id:
            tg_edit(chat_id, status_msg_id, f"❌ @{username} не найден")
            active_jobs[str(chat_id)] = False; return

        tg_edit(chat_id, status_msg_id, f"📋 <b>@{username}</b>\n⏳ Загружаю Reels...")
        all_videos = []; max_id = None

        for page in range(30):
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
                    all_videos.append({"shortcode": mv.get("code",""), "view_count": views,
                        "like_count": mv.get("like_count",0), "caption": cap[:300],
                        "video_url": vv[0].get("url","") if vv else ""})
                pi = rd.get("paging_info", {})
                if not (pi.get("more_available") or rd.get("more_available")): break
                nid = pi.get("max_id") or rd.get("next_max_id")
                if not nid: break
                max_id = nid; time.sleep(1.2)
            except Exception as e:
                print(f"    page err: {e}", flush=True); break

        viral = sorted([v for v in all_videos if v["view_count"] >= min_views],
                       key=lambda x: x["view_count"], reverse=True)
        total = len(viral)

        if total == 0:
            tg_edit(chat_id, status_msg_id,
                f"❌ <b>@{username}</b>\nНет видео {min_views:,}+ (проверено {len(all_videos)})")
            active_jobs[str(chat_id)] = False; return

        top3 = "\n".join([f"  #{i+1} {v['shortcode']}: {v['view_count']:,} 👁"
                           for i,v in enumerate(viral[:3])])
        tg_edit(chat_id, status_msg_id,
            f"✅ <b>@{username}</b> — {total} видео {min_views:,}+\n🏆 Топ-3:\n{top3}\n\n🎤 Транскрибирую...")

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        out_path = Path("/tmp") / f"{username}_RU_{ts}.txt"
        adapted = 0; failed = 0; transcribed = 0

        with open(str(out_path), "w", encoding="utf-8") as out:
            out.write(f"============================================================\n📊 ВИРУСНЫЙ КОНТЕНТ @{username}\n")
            out.write(f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
            out.write(f"🎬 {total} видео | {min_views:,}+\n============================================================\n\n")

            for i, v in enumerate(viral, 1):
                sc, views, likes = v["shortcode"], v["view_count"], v["like_count"]
                cap, vurl = v["caption"], v["video_url"]
                if i % 5 == 1:
                    tg_edit(chat_id, status_msg_id,
                        f"🎤 <b>@{username}</b>\n⏳ {i}/{total} | ✅ {adapted} | ❌ {failed}")

                out.write(f"{'-'*60}\n#{i}  👁 {views:,}  ❤️ {likes:,}\n")
                out.write(f"🔗 https://www.instagram.com/reel/{sc}/\n")
                if cap: out.write(f"📌 {cap[:150]}\n")
                out.write("\n")

                transcript = ""
                tmp_path = None; audio_path = None
                if vurl:
                    try:
                        vr = requests.get(vurl, headers={"User-Agent": UA}, timeout=120, stream=True)
                        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                        for chunk in vr.iter_content(65536): tmp.write(chunk)
                        tmp.flush(); tmp.close(); tmp_path = tmp.name
                        fsize = os.path.getsize(tmp_path)
                        if fsize > 24*1024*1024:
                            atmp = tempfile.NamedTemporaryFile(suffix=".m4a", delete=False)
                            atmp.close()
                            subprocess.run(["ffmpeg","-i",tmp_path,"-acodec","aac","-ab","64k","-y",atmp.name],
                                capture_output=True, timeout=120)
                            os.unlink(tmp_path); tmp_path=None; audio_path=atmp.name
                        else:
                            audio_path=tmp_path; tmp_path=None
                        with open(audio_path,"rb") as af:
                            ext = Path(audio_path).suffix[1:]
                            mime = "audio/mp4" if ext=="m4a" else "video/mp4"
                            tr = requests.post("https://api.groq.com/openai/v1/audio/transcriptions",
                                headers={"Authorization":f"Bearer {GROQ_KEY}"},
                                files={"file":(f"a.{ext}",af,mime)},
                                data={"model":"whisper-large-v3-turbo","response_format":"text"}, timeout=180)
                        os.unlink(audio_path); audio_path=None
                        if tr.status_code == 200: transcript=tr.text.strip(); transcribed+=1
                    except Exception as e:
                        print(f"    err: {e}", flush=True)
                        for p in [tmp_path,audio_path]:
                            if p:
                                try: os.unlink(p)
                                except: pass

                if transcript:
                    out.write("📝 ОРИГИНАЛ:\n" + transcript + "\n\n")
                    try:
                        ar = requests.post("https://api.groq.com/openai/v1/chat/completions",
                            headers={"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},
                            json={"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":
                                f"Адаптируй для русского вирального видео-скрипта ~47 секунд (~117 слов). Правила: переведи на русский, сохрани hook в начале, разговорный стиль, только готовый скрипт.\nОригинал:\n{transcript}"
                            }]}, timeout=60)
                        if ar.status_code==200:
                            ru=ar.json()["choices"][0]["message"]["content"].strip()
                            out.write(f"🇷🇺 RU (~47с, {len(ru.split())} слов):\n{ru}\n\n"); adapted+=1
                        else: out.write(f"⚠️ Groq {ar.status_code}\n\n"); failed+=1
                    except Exception as e: out.write(f"⚠️ {e}\n\n"); failed+=1
                else: out.write("⚠️ Транскрипция недоступна\n\n"); failed+=1
                out.flush(); time.sleep(0.3)
            out.write(f"\n============================================================\n✅ {transcribed}/{total} транскрибировано\n✅ {adapted}/{total} адаптировано\n❌ {failed} ошибок\n")

        tg_edit(chat_id, status_msg_id,
            f"✅ <b>@{username}</b> готово!\n🇷🇺 {adapted}/{total} RU скриптов\n📤 Отправляю...")
        caption = (f"📊 @{username}\n🎬 {total} видео ({min_views:,}+ 👁)\n"
                   f"📝 {transcribed} транскрипций | 🇷🇺 {adapted} RU скриптов\n"
                   f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        res = tg_doc(chat_id, str(out_path), caption)
        if res.get("ok"):
            tg_edit(chat_id, status_msg_id, f"✅ <b>@{username}</b> — готово! 🇷🇺 {adapted}/{total} ⬆️")
        else:
            tg_edit(chat_id, status_msg_id, f"⚠️ {res.get('description', str(res))}")
        try: os.unlink(str(out_path))
        except: pass

    except Exception as e:
        print(f"[ERR] {e}", flush=True)
        tg_send(chat_id, f"❌ Ошибка: {e}")
    finally:
        active_jobs[str(chat_id)] = False

def handle_message(msg):
    chat_id = msg.get("chat",{}).get("id")
    text = (msg.get("text","") or "").strip()
    msg_id = msg.get("message_id")
    if not chat_id or not text: return

    if text.startswith("/start") or text.startswith("/help"):
        tg_send(chat_id,
            "🤖 <b>Content Factory Bot</b>\n\n"
            "Отправь ссылку на Instagram профиль — получи RU скрипты:\n\n"
            "<code>https://www.instagram.com/username</code>\n\n"
            "С фильтром просмотров:\n"
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
        if not username: tg_send(chat_id, "❌ Не удалось распознать аккаунт", msg_id); return
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

def _start(chat_id, username, min_views, reply_to):
    if active_jobs.get(str(chat_id)):
        tg_send(chat_id, "⏳ Уже идёт анализ...", reply_to); return
    active_jobs[str(chat_id)] = True
    sid = tg_send(chat_id,
        f"🚀 <b>@{username}</b>\n📊 {min_views:,}+ просмотров\n⏳ Загружаю...", reply_to)
    threading.Thread(target=run_pipeline, args=(chat_id, username, min_views, sid), daemon=True).start()

print(f"[BOT] 🚀 Content Factory Bot started | filter={DEFAULT_VIEWS:,}+", flush=True)
offset = 0
while True:
    try:
        r = requests.get(f"{TG}/getUpdates",
            params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]}, timeout=35)
        if r.status_code == 200:
            for upd in r.json().get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if msg:
                    try: handle_message(msg)
                    except Exception as e: print(f"[ERR] {e}", flush=True)
    except Exception as e:
        print(f"[POLL] {e}", flush=True); time.sleep(5)
