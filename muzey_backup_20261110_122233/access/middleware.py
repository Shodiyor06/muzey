from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from . import tg
from .models import AccessToken

EXEMPT = ("/enter/", "/tg/", "/static/", "/admin", "/django-admin", "/taklif", "/favicon", "/robots.txt")


def has_access(request):
    key = request.session.get("acc")
    if not key:
        return False
    ok = cache.get("acc:" + key)
    if ok is None:
        t = AccessToken.objects.filter(key=key).select_related("visitor").first()
        ok = bool(t and t.valid())
        cache.set("acc:" + key, ok, 30)
    return ok


class TelegramAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        p = request.path
        if (p.startswith(EXEMPT + tuple(getattr(settings, "ACCESS_EXEMPT", ())))
                or (request.user.is_authenticated and request.user.is_staff) or has_access(request)):
            return self.get_response(request)
        if p.startswith(("/api/", "/media/")) or "application/json" in request.headers.get("accept", ""):
            return JsonResponse({"error": "forbidden"}, status=403)
        r = render(request, "access/gate.html", {"bot": tg.bot_link(), "expired": False}, status=403)
        r["X-Robots-Tag"] = "noindex, nofollow"
        return r
