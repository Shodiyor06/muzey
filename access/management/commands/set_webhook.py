import os
from django.core.management.base import BaseCommand
from access import tg


class Command(BaseCommand):
    help = "Telegram webhookni oʻrnatadi: python manage.py set_webhook [https://sayt.onrender.com]"

    def add_arguments(self, p):
        p.add_argument("url", nargs="?")

    def handle(self, *a, url=None, **k):
        base = (url or os.environ.get("SITE_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
        if not base or not tg.TOKEN():
            self.stdout.write("TELEGRAM_BOT_TOKEN yoki sayt manzili yoʻq, oʻtkazib yuborildi.")
            return
        r = tg.api("setWebhook", url=f"{base}/tg/webhook/{tg.secret()}/", secret_token=tg.secret(),
                   allowed_updates=["message", "callback_query"], drop_pending_updates=True)
        self.stdout.write(str(r))
