import hashlib, json, logging, os, urllib.request
from django.contrib.auth import get_user_model
from .models import AccessToken, TgVisitor

log = logging.getLogger(__name__)
TOKEN = lambda: os.environ.get("TELEGRAM_BOT_TOKEN", "")
OWNERS = lambda: {int(x) for x in os.environ.get("TELEGRAM_OWNER_IDS", "").replace(" ", "").split(",") if x.isdigit()}


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


def welcome(chat, name):
    api("sendMessage", chat_id=chat, text=f"Salom, {name}! 👋\nShaxsiy muzeyingizga kirish uchun pastdagi tugmani bosing.",
        reply_markup={"inline_keyboard": [[{"text": "🖼 Muzey", "callback_data": "enter"}]]})


def register(frm):
    """Telegram foydalanuvchisini roʻyxatdan oʻtkazadi: TgVisitor + Django profili."""
    User = get_user_model()
    name = (frm.get("first_name") or "")[:120]
    v, created = TgVisitor.objects.update_or_create(tg_id=frm["id"], defaults={
        "first_name": name, "username": (frm.get("username") or "")[:80]})
    if not v.user_id:
        user = None
        if frm["id"] in OWNERS():  # sayt egasi: mavjud superuser (eski muzeyi) bilan bogʻlanadi
            user = User.objects.filter(is_superuser=True, is_active=True, tg__isnull=True).order_by("id").first()
        if not user:
            user = User.objects.create_user(username=f"tg{frm['id']}", first_name=name[:150])
        v.user = user
        v.save(update_fields=["user"])
    return v, created


def login_token(v, renew=False):
    """Foydalanuvchining doimiy kirish kaliti. ``renew`` — eskisini bekor qilib, yangisini beradi."""
    if renew:
        v.tokens.filter(kind="login", revoked=False).update(revoked=True)
    return v.tokens.filter(kind="login", revoked=False).first() or AccessToken.issue("login", visitor=v, label=str(v))


def send_link(chat, v, base, created, renewed=False):
    tok = login_token(v, renew=renewed)
    url = enter_url(base, tok)
    head = ("Havolangiz yangilandi 🔄 (eskisi endi ishlamaydi)" if renewed else
            "Roʻyxatdan oʻtdingiz ✨" if created else "Xush kelibsiz! ✨")
    api("sendMessage", chat_id=chat, disable_web_page_preview=True,
        text=(f"{head}\n\nSizning shaxsiy kirish havolangiz:\n{url}\n\n"
              "Unga kirsangiz, toʻgʻri oʻz profilingizga tushasiz. Havolaning muddati yoʻq, "
              "shuning uchun uni hech kimga bermang.\n\n"
              "Sevgilingizga muzeyni koʻrsatish uchun profilingizdagi Sozlamalar → "
              "“Sevgilingiz uchun havola” boʻlimidan alohida havola yarating."),
        reply_markup={"inline_keyboard": [[{"text": "🖼 Profilimga kirish", "url": url}],
                                          [{"text": "🔄 Yangi havola olish", "callback_data": "renew"}]]})


def on_callback(cb, base):
    frm = cb["from"]
    api("answerCallbackQuery", callback_query_id=cb["id"])
    if cb.get("data") not in ("enter", "renew"):
        return
    v, created = register(frm)
    if v.blocked or not v.user.is_active:
        return api("sendMessage", chat_id=frm["id"], text="Kechirasiz, sizga kirish cheklangan.")
    send_link(frm["id"], v, base, created, renewed=cb["data"] == "renew")


def handle(u, base):
    if u.get("callback_query"):
        return on_callback(u["callback_query"], base)
    m = u.get("message") or {}
    frm = m.get("from") or {}
    if not frm or frm.get("is_bot") or (m.get("chat") or {}).get("type") != "private":
        return
    welcome(frm["id"], frm.get("first_name", "doʻst"))
