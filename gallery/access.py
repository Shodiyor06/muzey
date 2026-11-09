"""Muzeyga kirish: egasining Telegram akkaunti va shaxsiy havola."""
import hashlib
import hmac
import time

from django.conf import settings
from django.core import signing
from django.utils.crypto import constant_time_compare

from .models import SiteSettings

SHARE_COOKIE = "muzey_kalit"
SHARE_SALT = "gallery.share.v1"
SHARE_MAX_AGE = 60 * 60 * 24 * 365
TELEGRAM_MAX_AGE = 60 * 60 * 24
TELEGRAM_FIELDS = ("id", "first_name", "last_name", "username", "photo_url", "auth_date")


def bot_token(s=None):
    s = s or SiteSettings.load()
    return (s.telegram_token or getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip()


def owner_id(s=None):
    s = s or SiteSettings.load()
    return s.telegram_id or getattr(settings, "TELEGRAM_OWNER_ID", None)


def telegram_verify(params, token):
    """Telegram Login Widget maʼlumotlarini bot tokeni bilan tekshiradi.

    Muvaffaqiyatli boʻlsa Telegram foydalanuvchi ID sini, aks holda None qaytaradi.
    """
    if not token:
        return None
    data = {k: str(params.get(k, "")) for k in TELEGRAM_FIELDS if k in params}
    given = str(params.get("hash", ""))
    if not given or not data.get("id") or not data.get("auth_date"):
        return None
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = hashlib.sha256(token.encode("utf-8")).digest()
    expected = hmac.new(secret, check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, given):
        return None
    try:
        auth_date = int(data["auth_date"])
        user_id = int(data["id"])
    except (TypeError, ValueError):
        return None
    if user_id <= 0 or abs(time.time() - auth_date) > TELEGRAM_MAX_AGE:
        return None
    return user_id


def share_ok(request, s=None):
    s = s or SiteSettings.load()
    if not s.share_token:
        return False
    raw = request.COOKIES.get(SHARE_COOKIE, "")
    if not raw:
        return False
    try:
        data = signing.loads(raw, salt=SHARE_SALT, max_age=SHARE_MAX_AGE)
    except signing.BadSignature:
        return False
    return constant_time_compare(str(data.get("t", "")), s.share_token)


def has_access(request, s=None):
    """Egasi (staff) yoki toʻgʻri havola orqali kirgan mehmon."""
    return bool(request.user.is_staff or share_ok(request, s))


def grant_share(request, response, token):
    response.set_cookie(
        SHARE_COOKIE,
        signing.dumps({"t": token}, salt=SHARE_SALT, compress=True),
        max_age=SHARE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure,
    )
    return response
