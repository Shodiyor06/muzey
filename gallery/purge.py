"""Yuklangan rasmlarni belgilangan muddatdan keyin bazadan VA diskdan oʻchiradi.

Muddat: PHOTO_TTL_HOURS muhit oʻzgaruvchisi (standart 3 soat, 0 = oʻchirmaslik).
Ishlashi: 1) har soʻrovda (daqiqada bir marta) eskirganlarni tozalaydi,
          2) qoʻlda/cron:  python manage.py purge_photos
"""
import logging, os
from datetime import timedelta
from django.apps import apps
from django.core.cache import cache
from django.db import models
from django.utils import timezone

log = logging.getLogger(__name__)
CANDIDATES = ("created", "created_at", "uploaded_at", "uploaded", "added", "date_added", "timestamp")


def ttl_hours():
    try:
        return float(os.environ.get("PHOTO_TTL_HOURS", "3") or 0)
    except ValueError:
        return 3.0


def purge_expired(hours=None, dry=False):
    """Eskirgan rasmlar sonini qaytaradi (dry=True boʻlsa, oʻchirmaydi)."""
    hours = ttl_hours() if hours is None else hours
    if hours <= 0:
        return 0
    Photo = apps.get_model("gallery", "Photo")
    cutoff = timezone.now() - timedelta(hours=hours)
    fields = {f.name: f for f in Photo._meta.get_fields() if getattr(f, "concrete", False)}
    imgf = next((n for n, f in fields.items() if isinstance(f, models.FileField)), None)
    tsf = next((c for c in CANDIDATES if isinstance(fields.get(c), models.DateTimeField)), None)
    if tsf:
        expired = list(Photo.objects.filter(**{tsf + "__lt": cutoff}))
    else:  # vaqt maydoni yoʻq boʻlsa, fayl yuklangan vaqtiga qaraymiz
        expired = []
        for p in Photo.objects.all():
            try:
                if os.path.getmtime(getattr(p, imgf).path) < cutoff.timestamp():
                    expired.append(p)
            except Exception:
                continue
    if dry:
        return len(expired)
    for p in expired:
        try:
            if imgf and getattr(p, imgf):
                getattr(p, imgf).delete(save=False)  # diskdagi fayl
        except Exception:
            log.exception("fayl oʻchmadi: %s", p.pk)
        p.delete()  # bazadagi qator
    return len(expired)


class PurgeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if cache.add("purge:last", 1, 60):  # daqiqada bir marta
            try:
                purge_expired()
            except Exception:
                log.exception("tozalashda xato")
        return self.get_response(request)
