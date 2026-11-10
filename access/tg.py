import hashlib, json, logging, os, urllib.request
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from .models import AccessToken, TgVisitor

log = logging.getLogger(__name__)
TOKEN = lambda: os.environ.get("TELEGRAM_BOT_TOKEN", "")
OWNERS = lambda: {int(x) for x in os.environ.get("TELEGRAM_OWNER_IDS", "").replace(" ", "").split(",") if x.isdigit()}
DAYS = lambda: getattr(settings, "ACCESS_DAYS", 2)


def secret():
    return hashlib.sha256(("muzey:" + TOKEN()).encode()).hexdigest()[:48]


def bot_link():
    u = os.environ.get("TELEGRAM_BOT_USERNAME", "").lstrip("@")
    return f"https://t.me/{u}" if u else ""


def api(method, **data):
    if not TOKEN():
        return {"ok": False, "description": "TELEGRAM_BOT_TOKEN berilmagan"}
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN()}/{method}", json.dumps(data).encode(),
                                 {"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=10))
    except Exception as e:  # tarmoq yoki Telegram xatosi
        log.warning("telegram %s: %s", method, e)
        return {"ok": False, "description": str(e)}


def enter_url(base, tok):
    return f"{base.rstrip('/')}/enter/{tok.key}/"


def until_text(tok):
    return timezone.localtime(tok.expires_at).strftime("%d.%m.%Y %H:%M")


def welcome(chat, name):
    api("sendMessage", chat_id=chat, text=f"Salom, {name}! 👋\nMuzeyga kirish uchun pastdagi tugmani bosing.",
        reply_markup={"inline_keyboard": [[{"text": "🖼 Muzey", "callback_data": "enter"}]]})


def on_callback(cb, base):
    frm = cb["from"]
    api("answerCallbackQuery", callback_query_id=cb["id"])
    if cb.get("data") != "enter":
        return
    v, _ = TgVisitor.objects.update_or_create(tg_id=frm["id"], defaults={
        "first_name": frm.get("first_name", "")[:120], "username": frm.get("username", "")[:80]})
    if v.blocked:
        return api("sendMessage", chat_id=frm["id"], text="Kechirasiz, sizga kirish cheklangan.")
    if v.tokens.filter(created__gt=timezone.now() - timedelta(hours=1)).count() >= 5:
        return api("sendMessage", chat_id=frm["id"], text="Juda koʻp soʻrov. Birozdan keyin qayta urinib koʻring.")
    tok = AccessToken.issue("visitor", visitor=v, label=str(v))
    api("sendMessage", chat_id=frm["id"],
        text=f"Havolangiz tayyor ✨\nU {until_text(tok)} gacha ({DAYS()} kun) ishlaydi. Muddati tugasa, shu yerdan yangisini olasiz.",
        reply_markup={"inline_keyboard": [[{"text": "🖼 Muzeyga kirish", "url": enter_url(base, tok)}]]})


def handle(u, base):
    if u.get("callback_query"):
        return on_callback(u["callback_query"], base)
    m = u.get("message") or {}
    frm, text = m.get("from") or {}, (m.get("text") or "").strip()
    if not frm or frm.get("is_bot") or (m.get("chat") or {}).get("type") != "private":
        return
    if text.startswith("/taklif") and frm["id"] in OWNERS():
        tok = AccessToken.issue("invite", label=text[7:].strip() or "Taklif")
        return api("sendMessage", chat_id=frm["id"],
                   text=f"Taklif havolasi ({until_text(tok)} gacha):\n{enter_url(base, tok)}")
    welcome(frm["id"], frm.get("first_name", "doʻst"))
