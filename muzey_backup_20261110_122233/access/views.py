import json, logging
from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from . import tg
from .models import AccessToken, TgVisitor

log = logging.getLogger(__name__)
site_base = lambda request: getattr(settings, "SITE_URL", "") or request.build_absolute_uri("/")


def enter(request, key):
    t = AccessToken.objects.filter(key=key).select_related("visitor").first()
    if not t or not t.valid():
        return render(request, "access/gate.html", {"bot": tg.bot_link(), "expired": True}, status=410)
    AccessToken.objects.filter(pk=t.pk).update(uses=F("uses") + 1)
    if t.visitor:
        TgVisitor.objects.filter(pk=t.visitor_id).update(last_seen=timezone.now())
    request.session["acc"] = key
    request.session.set_expiry(max(60, int((t.expires_at - timezone.now()).total_seconds())))
    return redirect("/")


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


def manage(request):
    u = request.user
    if not (u.is_authenticated and u.is_staff):
        return HttpResponse('Avval <a href="/admin/">/admin/</a> orqali kiring, soʻng bu sahifani qayta oching.', status=403)
    base = request.build_absolute_uri("/")
    if request.method == "POST":
        a, P = request.POST.get("a"), request.POST
        if a == "create":
            days = int(P.get("days") or 2) if (P.get("days") or "2").isdigit() else 2
            t = AccessToken.issue("invite", days=min(max(days, 1), 30), label=P.get("label", "").strip() or "Taklif")
            request.session["new_link"] = tg.enter_url(base, t)
        elif a == "revoke":
            t = AccessToken.objects.filter(pk=P.get("id")).first()
            if t:
                t.revoked = True
                t.save(update_fields=["revoked"])
                cache.delete("acc:" + t.key)
        elif a in ("block", "unblock"):
            v = TgVisitor.objects.filter(pk=P.get("id")).first()
            if v:
                v.blocked = a == "block"
                v.save(update_fields=["blocked"])
                cache.clear()
        elif a == "webhook":
            r = tg.api("setWebhook", url=f"{base}tg/webhook/{tg.secret()}/", secret_token=tg.secret(),
                       allowed_updates=["message", "callback_query"], drop_pending_updates=True)
            request.session["flash"] = "Webhook oʻrnatildi ✓" if r.get("ok") else "Xato: " + str(r.get("description"))
        return redirect("/taklif/")
    now = timezone.now()
    return render(request, "access/manage.html", {
        "new_link": request.session.pop("new_link", ""), "flash": request.session.pop("flash", ""),
        "invites": AccessToken.objects.filter(kind="invite", revoked=False, expires_at__gt=now),
        "visitors": TgVisitor.objects.all()[:200], "bot": tg.bot_link(), "has_token": bool(tg.TOKEN()),
        "base": base, "days": getattr(settings, "ACCESS_DAYS", 2),
    })
