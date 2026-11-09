"""مانیتور وضعیت سیستم‌ها — روی GitHub Actions اجرا می‌شه و اگه چیزی قطع/وصل شد ایمیل می‌ده.

همون بررسی‌های صفحه‌ی index.html رو انجام می‌ده. وضعیت قبلی توی state.json نگه داشته می‌شه
تا فقط موقع «تغییر» ایمیل بیاد (قطع شد / دوباره وصل شد)، نه هر بار.
برای جلوگیری از هشدار الکی، یه مورد فقط بعد از ۲ بار پشت‌سرهم خطا «قطع» حساب می‌شه.
"""
import json, os, re, smtplib, ssl, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.header import Header

RAW = "https://raw.githubusercontent.com/azkicenter/{repo}/main/config.js"
PAGES = "https://azkicenter.github.io"
SUPABASE_URL = "https://paokcjakxxjqtulibegi.supabase.co"
SUPABASE_KEY = "sb_publishable_Us07X7VRGQ4q3jSIPzeT0g_8-qkLTeO"
STATE_FILE = "state.json"
FAILS_BEFORE_ALERT = 2
TEHRAN = timezone(timedelta(hours=3, minutes=30))
LIMIT_OPS_MIN = 45       # وضعیت پنل کارشناسان (هر ۱۵ دقیقه)

# ساعت‌های سکوت به وقت تهران، مثلا "23-8" یعنی از ۱۱ شب تا ۸ صبح ایمیل نفرست (خالی = همیشه)
QUIET_HOURS = os.environ.get("QUIET_HOURS", "").strip()


def http(url, method="GET", headers=None, body=None, timeout=20):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "azki-status-monitor", **(headers or {})},
                                 data=body.encode() if body else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # تایم‌اوت، DNS، قطعی تونل
        return None, str(e)


def probe(url):
    """هر جوابی از خود سرور (حتی ۴۰۱/۴۰۵) یعنی زنده‌ست. ۵۰۲/۵۰۳/۵۰۴ یا بی‌جوابی یعنی قطع."""
    code, _ = http(url)
    if code is None:
        return False, "جواب نداد"
    if code in (502, 503, 504):
        return False, f"سرویس بالا نیست ({code})"
    if code == 404:
        return False, "مسیر پیدا نشد (404) — احتمالاً تونل عوض شده یا قطعه"
    return True, f"OK ({code})"


def tunnel(repo):
    code, txt = http(RAW.format(repo=repo) + f"?t={int(time.time())}")
    m = re.search(r"API_BASE\s*:\s*[\"']([^\"']+)[\"']", txt or "") if code == 200 else None
    return m.group(1).rstrip("/") if m else None


def j2g(jy, jm, jd):
    jy += 1595
    days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd + ((jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186)
    gy = 400 * (days // 146097); days %= 146097
    if days > 36524:
        days -= 1; gy += 100 * (days // 36524); days %= 36524
        if days >= 365: days += 1
    gy += 4 * (days // 1461); days %= 1461
    if days > 365:
        gy += (days - 1) // 365; days = (days - 1) % 365
    gd = days + 1
    ml = [0, 31, 29 if (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > ml[gm]:
        gd -= ml[gm]; gm += 1
    return gy, gm, gd


def jalali_tehran(date, time_):
    d = re.search(r"(\d{4})\D(\d{1,2})\D(\d{1,2})", date or ""); t = re.search(r"(\d{1,2}):(\d{2})", time_ or "")
    if not d or not t:
        return None
    gy, gm, gd = j2g(int(d[1]), int(d[2]), int(d[3]))
    return datetime(gy, gm, gd, int(t[1]), int(t[2]), tzinfo=TEHRAN)


MAINT = {}  # برنامه‌هایی که از صفحه‌ی وضعیت خاموش (حالت تعمیر) شدن

# هر چک مال کدوم برنامه‌ست (برای نادیده گرفتن برنامه‌ی خاموش)
KEY_APP = {"page_dashboard": "dashboard", "dash_server": "dashboard", "endorsement": "dashboard", "stats": "dashboard",
           "tarikhche": "tarikhche", "page_sanhab": "sanhab", "sanhab_server": "sanhab",
           "page_hub": "hub", "page_wallboard": "wallboard"}


def is_off(key):
    app = KEY_APP.get(key)
    if not app:
        return False
    if MAINT.get(app, {}).get("on"):
        return True
    return app == "tarikhche" and MAINT.get("dashboard", {}).get("on", False)


def run_checks():
    res = {}  # key -> (ok, name, detail)

    def add(key, name, ok, detail):
        res[key] = (ok, name, detail)

    # صفحه‌ها
    for repo, name in [("dashboard", "صفحه‌ی داشبورد"), ("sanhab", "صفحه‌ی سنهاب"), ("hub", "صفحه‌ی هاب"), ("wallboard", "صفحه‌ی وال برد")]:
        code, _ = http(f"{PAGES}/{repo}/")
        add(f"page_{repo}", name, code == 200, f"HTTP {code}" if code else "باز نشد")

    # داشبورد عملیات
    api = tunnel("dashboard")
    if not api:
        add("dash_server", "سرور داشبورد (cmd)", False, "آدرس تونل توی config.js پیدا نشد")
    else:
        code, _ = http(api + "/auth/health")
        gw_ok = code == 200
        add("dash_server", "سرور داشبورد + لاگین (cmd)", gw_ok, f"HTTP {code}" if code else "جواب نداد — سیستم یا cmd خاموشه؟")
        if gw_ok:  # اگه سرور اصلی قطعه، زیرسرویس‌ها رو جدا گزارش نکن (یه ایمیل شلوغ نشه)
            for key, name, path in [("tarikhche", "تاریخچه‌خوان", "/tarikhche/api/ping"),
                                    ("endorsement", "الحاقیه ایران", "/endorsement/api/endorsement/search"),
                                    ("stats", "آمار درخواست‌ها", "/stats/api/summary?days=1")]:
                add(key, name, *probe(api + path))

    # سنهاب
    api = tunnel("sanhab")
    if not api:
        add("sanhab_server", "سرور سنهاب (cmd)", False, "آدرس تونل توی config.js پیدا نشد")
    else:
        ok, d = probe(api + "/api/me")
        add("sanhab_server", "سرور سنهاب (cmd)", ok, d if ok else d + " — سیستم یا cmd خاموشه؟")

    # Supabase + n8n
    code, txt = http(SUPABASE_URL + "/rest/v1/rpc/status_heartbeat", "POST",
                     {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}, "{}")
    if code != 200:
        add("supabase", "Supabase", False, f"HTTP {code}" if code else "جواب نداد")
    else:
        add("supabase", "Supabase", True, "OK")
        hb = json.loads(txt)
        MAINT.update(hb.get("maintenance") or {})
        now = datetime.fromisoformat(hb["now"].replace("Z", "+00:00"))

        def fresh(key, name, at, limit):
            if not at:
                return add(key, name, False, "زمان آپدیت پیدا نشد")
            mins = int((now - at).total_seconds() // 60)
            add(key, name, mins <= limit, f"آخرین آپدیت {mins} دقیقه پیش" + ("" if mins <= limit else " — n8n یا سیستم رو چک کن"))

        # آپدیت ساعتی هاب هشدار نمی‌ده (فقط توی صفحه زمان آخرین اجرا نشون داده می‌شه)
        ops = hb.get("ops_updated_at")
        fresh("n8n_ops", "وضعیت پنل کارشناسان (n8n)",
              datetime.fromisoformat(ops.replace("Z", "+00:00")) if ops else None, LIMIT_OPS_MIN)
    return res


def in_quiet_hours():
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", QUIET_HOURS)
    if not m:
        return False
    a, b, h = int(m[1]), int(m[2]), datetime.now(TEHRAN).hour
    return a <= h < b if a < b else (h >= a or h < b)


def send_mail(subject, lines):
    # فاصله/خط اضافه‌ای که موقع کپی توی Secretها میاد رو پاک می‌کنه
    user = os.environ["GMAIL_USER"].strip()
    pw = "".join(os.environ["GMAIL_APP_PASSWORD"].split())   # App Password با یا بدون فاصله
    to = [a.strip() for a in os.environ["ALERT_TO"].split(",") if a.strip()]
    html = ('<div dir="rtl" style="font-family:Tahoma,sans-serif;font-size:14px;line-height:1.8">'
            + "<br>".join(lines)
            + f'<br><br><a href="{PAGES}/status/">باز کردن صفحه‌ی وضعیت</a></div>')
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = user
    msg["To"] = ", ".join(to)
    ctx = ssl.create_default_context()
    last = None
    for attempt in ("ssl465", "tls587"):
        try:
            if attempt == "ssl465":
                s = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=30); s.ehlo()
            else:
                s = smtplib.SMTP("smtp.gmail.com", 587, timeout=30); s.ehlo(); s.starttls(context=ctx); s.ehlo()
            with s:
                s.user, s.password = user, pw
                try:
                    code, resp = s.auth("LOGIN", s.auth_login, initial_response_ok=False)
                except smtplib.SMTPServerDisconnected:
                    raise
                if code not in (235, 503):
                    raise smtplib.SMTPAuthenticationError(code, resp)
                s.sendmail(user, to, msg.as_string())
            return
        except smtplib.SMTPAuthenticationError as e:
            raise RuntimeError(f"جیمیل نام کاربری/App Password رو قبول نکرد: {e.smtp_code} {e.smtp_error!r}")
        except Exception as e:
            last = e
            print(f"send via {attempt} failed: {type(e).__name__}: {e}")
    raise RuntimeError(f"ارسال ایمیل نشد: {last}")


def main():
    try:
        state = json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:
        state = {}
    res = run_checks()
    prev_down = {k: v.get("down", False) for k, v in state.items()}
    went_down, came_back = [], []

    off = [k for k in res if is_off(k)]
    if off:
        print("maintenance (skipped):", off)
    for k in off:  # برنامه‌ی خاموش: نه هشدار قطعی، نه «وصل شد»؛ وضعیتش صفر می‌شه
        res.pop(k)
        state[k] = {"fails": 0, "down": False}
    for key, (ok, name, detail) in res.items():
        st = state.get(key, {"fails": 0, "down": False})
        if ok:
            if st["down"]:
                came_back.append(f"🟢 {name} دوباره وصل شد")
            st = {"fails": 0, "down": False}
        else:
            st["fails"] += 1
            if st["fails"] >= FAILS_BEFORE_ALERT and not st["down"]:
                st["down"] = True
                went_down.append(f"🔴 {name}: {detail}")
        state[key] = st

    # موردی که دیگه چک نمی‌شه (مثلا زیرسرویس‌ها وقتی سرور اصلی قطعه) وضعیت قبلیش دست نمی‌خوره
    still_down = [res[k][1] for k, st in state.items() if st.get("down") and k in res and not res[k][0]]
    print(json.dumps({k: v[0] for k, v in res.items()}, ensure_ascii=False))

    if os.environ.get("TEST_EMAIL") == "true":  # اجرای دستی با گزینه‌ی «ایمیل تست»
        ok_n = sum(1 for v in res.values() if v[0])
        lines = ["✅ این یه ایمیل تستیه — هشدارهای مانیتور از این به بعد همین‌طوری می‌رسن.", "",
                 f"وضعیت الان: {ok_n} از {len(res)} مورد سالم"]
        lines += [f"🔴 {n}: {d}" for ok, n, d in res.values() if not ok]
        lines += ["", "زمان: " + datetime.now(TEHRAN).strftime("%H:%M  %Y-%m-%d")]
        send_mail("✅ تست هشدار سیستم‌ها", lines)
        print("test email sent")

    if (went_down or came_back) and not in_quiet_hours():
        if went_down:
            subject = f"🔴 قطعی: {len(went_down)} مورد" + (f" (+{len(came_back)} وصل شد)" if came_back else "")
        else:
            subject = f"🟢 وصل شد: {len(came_back)} مورد"
        lines = went_down + came_back
        others = [n for n in still_down if not any(n in l for l in went_down)]
        if others:
            lines += ["", "هنوز قطعه: " + "، ".join(others)]
        lines += ["", "زمان: " + datetime.now(TEHRAN).strftime("%H:%M  %Y-%m-%d")]
        send_mail(subject, lines)
        print("email sent:", subject)
    elif went_down or came_back:
        # ساعت سکوت: وضعیت «قطع/وصل» قبلی رو نگه دار تا بعد از ساعت سکوت، اگه هنوز قطع بود، ایمیلش بیاد
        for key in res:
            if key in prev_down:
                state[key]["down"] = prev_down[key]
        print("quiet hours — email postponed")

    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
