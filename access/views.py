import json, logging
from django.conf import settings
from django.contrib.auth import login
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from . import tg
from .models import AccessToken, TgVisitor

log = logging.getLogger(__name__)
site_base = lambda request: getattr(settings, "SITE_URL", "") or request.build_absolute_uri("/")
SESSION_AGE = 60 * 60 * 24 * 365


def enter(request, key):
    """Botdan olingan kirish havolasi: foydalanuvchini oʻz profiliga kiritadi."""
    t = AccessToken.objects.filter(key=key, kind="login").select_related("visitor__user").first()
    if not t or not t.valid():
        return render(request, "access/gate.html", {"bot": tg.bot_link(), "expired": True}, status=410)
    AccessToken.objects.filter(pk=t.pk).update(uses=F("uses") + 1)
    TgVisitor.objects.filter(pk=t.visitor_id).update(last_seen=timezone.now())
    login(request, t.visitor.user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.set_expiry(SESSION_AGE)
    return redirect("panel")


@csrf_exempt
def webhook(request, secret):
    s = tg.secret()
    if request.method != "POST" or not tg.TOKEN() or secret != s or request.headers.get("X-Telegram-Bot-Api-Secret-Token") != s:
        return HttpResponse(status=403)
    try:
        update = json.loads(request.body)
        tg.handle(update, site_base(request))
    except Exception:
        log.exception("webhook xatosi")
    return JsonResponse({"ok": True})
