import hmac
import json
import mimetypes
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import SuspiciousFileOperation
from django.db.models import Count, F, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils._os import safe_join
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .access import (SHARE_MAX_AGE, bot_token, grant_share, has_access, owner_id,
                     telegram_verify)
from .layouts import museum_map, slots
from .models import DailyVisit, GuestEntry, Photo, SiteSettings


def gate(request, s=None, err="", status=200):
    s = s or SiteSettings.load()
    bot = (s.telegram_bot or "").strip().lstrip("@")
    ready = bool(bot_token(s))
    r = render(request, "gallery/gate.html", {
        "title": s.title, "err": err, "bot": bot, "ready": ready,
        "owner_ready": bool(owner_id(s)),
        "admin_url": "/admin/django/login/",
    }, status=status)
    r["X-Robots-Tag"] = "noindex, nofollow"
    return r


def too_many(key, limit, ttl):
    n = cache.get(key, 0) + 1
    cache.set(key, n, ttl)
    return n > limit


@ensure_csrf_cookie
def index(request):
    s = SiteSettings.load()
    if not has_access(request, s):
        return gate(request, s)
    if not request.user.is_staff:
        v, _ = DailyVisit.objects.get_or_create(date=timezone.localdate())
        DailyVisit.objects.filter(pk=v.pk).update(count=F("count") + 1)
    r = render(request, "gallery/index.html")
    r["X-Robots-Tag"] = "noindex, nofollow"
    return r


def share_entry(request, token):
    """Shaxsiy havola: cookie qoʻyib, manzil satridan kalitni olib tashlaydi."""
    s = SiteSettings.load()
    if not s.share_token or not hmac.compare_digest(str(token), s.share_token):
        raise Http404
    return grant_share(request, redirect("/"), s.share_token)


def telegram_enter(request, dest="/", bind=False):
    s = SiteSettings.load()
    if bind and not request.user.is_staff:
        return redirect("/admin/django/login/")
    if bind:
        state = request.GET.get("state", "")
        want = request.session.pop("tg_bind", "")
        if not want or not hmac.compare_digest(str(state), str(want)):
            messages.error(request, "Telegram bogʻlash muddati tugagan. Qayta urinib koʻring.")
            return redirect("panel_settings")
    uid = telegram_verify(request.GET, bot_token(s))
    if uid is None:
        if bind:
            messages.error(request, "Telegram tasdiqlanmadi. Qayta urinib koʻring.")
            return redirect("panel_settings")
        return gate(request, s, "Telegram tasdiqlanmadi. Qayta urinib koʻring.", 400)
    if bind:
        SiteSettings.objects.filter(pk=1).update(telegram_id=uid)
        messages.success(request, "Telegram akkaunt bogʻlandi. Endi shu akkaunt orqali kirasiz.")
        return redirect("panel_settings")
    owner = owner_id(s)
    if not owner:
        return gate(request, s, "Egasi Telegram ID si hali sozlanmagan. Admin panelda kiriting.", 403)
    if uid != owner:
        return gate(request, s, "Bu Telegram akkaunt muzey egasi emas.", 403)
    user = User.objects.filter(is_staff=True, is_active=True).order_by("id").first()
    if not user:
        return gate(request, s, "Admin foydalanuvchi topilmadi.", 500)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.set_expiry(SHARE_MAX_AGE)
    return redirect(dest)


def telegram_admin(request):
    return telegram_enter(request, "/admin/")


def sudo_enter(request):
    return telegram_enter(request, "/", bind=True)


def config(request):
    if not has_access(request):
        return JsonResponse({"error": "forbidden"}, status=403)
    s = SiteSettings.load()
    photos = Photo.objects.annotate(h=Count("guestentry", filter=Q(guestentry__is_heart=True)))
    m = museum_map(s, len(photos), bool(s.video))
    return JsonResponse({
        "title": s.title, "sub": s.subtitle, "layout": s.layout, "pal": s.palette,
        "music": s.music.url if s.music else "",
        "video": s.video.url if s.video else "",
        "map": m, "slots": len(slots(m)),
        "letter": {"title": s.letter_title, "text": s.letter_text,
                   "since": s.together_since.isoformat() if s.together_since else "",
                   "pos": s.letter_pos},
        "video_pos": s.video_pos,
        "photos": [{"id": p.id, "src": p.image.url, "title": p.title, "story": p.story,
                    "date": p.date.isoformat() if p.date else "", "hearts": p.h} for p in photos],
    })


@require_POST
def guest(request):
    if not has_access(request):
        return JsonResponse({"ok": False}, status=403)
    if too_many("guest:" + request.META.get("REMOTE_ADDR", ""), 40, 3600):
        return JsonResponse({"ok": False}, status=429)
    try:
        d = json.loads(request.body)
    except ValueError:
        return JsonResponse({"ok": False}, status=400)
    text, heart = str(d.get("text", "")).strip()[:300], bool(d.get("heart"))
    if not text and not heart:
        return JsonResponse({"ok": False}, status=400)
    photo = Photo.objects.filter(pk=d["photo"]).first() if str(d.get("photo", "")).isdigit() else None
    GuestEntry.objects.create(photo=photo, text=text, is_heart=heart)
    return JsonResponse({"ok": True})


def media(request, path):
    """Himoyalangan media: faqat egasi yoki havola egasiga. Range (Safari audio) qoʻllanadi."""
    if not has_access(request):
        raise Http404
    try:
        full = safe_join(settings.MEDIA_ROOT, path)
    except SuspiciousFileOperation:
        raise Http404
    if not os.path.isfile(full):
        raise Http404
    size, ctype = os.path.getsize(full), mimetypes.guess_type(full)[0] or "application/octet-stream"
    start, end, status = 0, size - 1, 200
    rng = request.headers.get("Range", "")
    if rng.startswith("bytes="):
        a, _, b = rng[6:].partition("-")
        try:
            start = int(a) if a else max(0, size - int(b))
            end = int(b) if (a and b) else size - 1
            end, status = min(end, size - 1), 206
        except ValueError:
            start, end, status = 0, size - 1, 200
    with open(full, "rb") as f:
        f.seek(start)
        data = f.read(end - start + 1)
    r = HttpResponse(data, status=status, content_type=ctype)
    r["Accept-Ranges"] = "bytes"
    r["Cache-Control"] = "private, max-age=3600"
    if status == 206:
        r["Content-Range"] = f"bytes {start}-{end}/{size}"
    return r
