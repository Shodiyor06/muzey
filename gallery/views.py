import json
import mimetypes
import os

from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from django.core.exceptions import SuspiciousFileOperation
from django.db.models import Count, F, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils._os import safe_join
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from access import tg

from .access import (clear_share, current_museum, grant_share, media_allowed,
                     share_museum)
from .layouts import museum_map, slots
from .models import DailyVisit, GuestEntry, Photo, SiteSettings


def gate(request):
    """Kirish sahifasi: roʻyxatdan oʻtish saytda emas, faqat Telegram bot orqali."""
    r = render(request, "gallery/gate.html", {
        "bot": tg.bot_link(), "admin_url": "/admin/django/login/",
    })
    r["X-Robots-Tag"] = "noindex, nofollow"
    return r


def too_many(key, limit, ttl):
    n = cache.get(key, 0) + 1
    cache.set(key, n, ttl)
    return n > limit


@ensure_csrf_cookie
def index(request):
    s, is_owner = current_museum(request)
    if not s:
        return gate(request)
    if not is_owner:
        v, _ = DailyVisit.objects.get_or_create(owner=s.owner, date=timezone.localdate())
        DailyVisit.objects.filter(pk=v.pk).update(count=F("count") + 1)
    r = render(request, "gallery/index.html")
    r["X-Robots-Tag"] = "noindex, nofollow"
    return r


def share_entry(request, token):
    """Ulashish havolasi: cookie qoʻyib, manzil satridan kalitni olib tashlaydi."""
    s = SiteSettings.objects.filter(share_token=token).exclude(share_token="").select_related("owner").first()
    if not s or (s.owner and not s.owner.is_active):
        raise Http404
    return grant_share(request, redirect("/"), s.share_token)


def own_museum(request):
    """Ulashilgan muzeydan chiqib, oʻz muzeyiga qaytish."""
    if not request.user.is_authenticated:
        return redirect("/")
    return clear_share(redirect("/"))


def logout_view(request):
    logout(request)
    return clear_share(redirect("/"))


def config(request):
    s, _ = current_museum(request)
    if not s:
        return JsonResponse({"error": "forbidden"}, status=403)
    photos = Photo.objects.filter(owner=s.owner).annotate(
        h=Count("guestentry", filter=Q(guestentry__is_heart=True)))
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
    s, _ = current_museum(request)
    if not s:
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
    photo = (Photo.objects.filter(pk=d["photo"], owner=s.owner).first()
             if str(d.get("photo", "")).isdigit() else None)
    GuestEntry.objects.create(owner=s.owner, photo=photo, text=text, is_heart=heart)
    return JsonResponse({"ok": True})


def media(request, path):
    """Himoyalangan media: faqat shu muzeyning egasi yoki mehmoniga. Range (Safari audio) qoʻllanadi."""
    museums = []
    shared = share_museum(request)
    if shared:
        museums.append(shared)
    if request.user.is_authenticated:
        museums.append(SiteSettings.for_user(request.user))
    if not any(media_allowed(m, path) for m in museums):
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
