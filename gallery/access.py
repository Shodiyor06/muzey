"""Muzeyni koʻrish huquqi.

Har bir foydalanuvchining oʻz muzeyi bor. Muzeyni quyidagilar koʻra oladi:
  * egasi — Telegram bot bergan kirish havolasi orqali kirgan foydalanuvchi;
  * mehmon — egasi profilida yaratgan ulashish havolasini ochgan odam (cookie orqali).
"""
from django.conf import settings
from django.core import signing

from .models import Photo, SiteSettings

SHARE_COOKIE = "muzey_kalit"
SHARE_SALT = "gallery.share.v1"
SHARE_MAX_AGE = 60 * 60 * 24 * 365


def share_museum(request):
    """Ulashish havolasi cookie si koʻrsatgan muzey (yaroqli boʻlsa), aks holda None."""
    raw = request.COOKIES.get(SHARE_COOKIE, "")
    if not raw:
        return None
    try:
        data = signing.loads(raw, salt=SHARE_SALT, max_age=SHARE_MAX_AGE)
    except signing.BadSignature:
        return None
    token = str(data.get("t", ""))
    if not token:
        return None
    s = SiteSettings.objects.filter(share_token=token).select_related("owner").first()
    if s and (s.owner is None or s.owner.is_active):
        return s
    return None


def current_museum(request):
    """(muzey, egasimi). Kirish huquqi yoʻq boʻlsa (None, False).

    Ulashish havolasi ochilgan boʻlsa, oʻsha muzey birinchi navbatda koʻrsatiladi
    (roʻyxatdan oʻtgan sevgilisi ham oʻz muzeyiga emas, unga yuborilganini koʻrishi uchun).
    Oʻz muzeyiga qaytish: /ozim/.
    """
    s = share_museum(request)
    if s:
        return s, bool(request.user.is_authenticated and s.owner_id == request.user.pk)
    if request.user.is_authenticated:
        return SiteSettings.for_user(request.user), True
    return None, False


def media_allowed(s, path):
    """Fayl shu muzeyga tegishlimi (boshqa foydalanuvchi fayllari berilmaydi)."""
    if not s or not path:
        return False
    if path in (s.music.name, s.video.name):
        return True
    return Photo.objects.filter(owner=s.owner, image=path).exists()


def grant_share(request, response, token):
    response.set_cookie(
        SHARE_COOKIE,
        signing.dumps({"t": token}, salt=SHARE_SALT, compress=True),
        max_age=SHARE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure(),
    )
    return response


def clear_share(response):
    response.delete_cookie(SHARE_COOKIE)
    return response
